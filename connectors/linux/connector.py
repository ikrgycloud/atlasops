"""Outbound, read-only Linux diagnostics. No remote command or job execution capability."""

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

VERSION = "0.1.0"


def diagnostics():
    disk = shutil.disk_usage(os.environ.get("ATLAS_CONNECTOR_DISK", "/"))
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, value = line.split(":", 1)
        if name in {"MemTotal", "MemAvailable"}:
            memory[name] = int(value.strip().split()[0])
    services = {}
    for name in filter(None, os.environ.get("ATLAS_CONNECTOR_SERVICES", "").split(",")):
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}\.service", name):
            raise ValueError("Invalid locally configured systemd unit")
        result = subprocess.run(
            ["systemctl", "is-active", "--", name],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
        services[name] = result.stdout.strip()[:100]
    # Logs stay on the source host. Only administrator-configured references are transmitted.
    references = [
        str(Path(p).resolve())
        for p in filter(
            None, os.environ.get("ATLAS_CONNECTOR_LOG_PATHS", "").split(",")
        )
    ]
    return {
        "hostname": socket.gethostname(),
        "cpu_load": list(os.getloadavg()),
        "memory_total_kib": memory["MemTotal"],
        "memory_available_kib": memory["MemAvailable"],
        "disk_total": disk.total,
        "disk_free": disk.free,
        "services": services,
        "log_references": references,
        "uptime_seconds": float(Path("/proc/uptime").read_text().split()[0]),
    }


def run(once=False):
    url = os.environ["ATLAS_CONNECTOR_URL"].rstrip("/")
    if urlsplit(url).scheme != "https" and not (
        os.environ.get("ATLAS_CONNECTOR_LOCAL_DEVELOPMENT") == "true"
        and urlsplit(url).hostname in {"localhost", "127.0.0.1"}
    ):
        raise SystemExit(
            "Connector requires HTTPS (loopback-only development override available)"
        )
    token = os.environ["ATLAS_CONNECTOR_TOKEN"]
    if len(token) < 40:
        raise SystemExit("Connector token is not a high-entropy enrollment credential")
    state = Path(
        os.environ.get(
            "ATLAS_CONNECTOR_STATE", "/var/lib/atlasops-connector/state.json"
        )
    )
    if not state.parent.is_dir():
        raise SystemExit("Create a private writable connector state directory")
    identity = hashlib.sha256(token.encode()).hexdigest()
    sequence = 0
    if state.exists():
        saved = json.loads(state.read_text())
        if saved["identity"] == identity:
            sequence = saved["sequence"]
    with httpx.Client(
        timeout=10, follow_redirects=False, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        while True:
            sequence += 1
            # Persist before send to prevent replay after a crash. Gaps are safe.
            temporary = state.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"identity": identity, "sequence": sequence})
            )
            temporary.chmod(0o600)
            temporary.replace(state)
            try:
                result = client.post(
                    url + "/api/v1/connectors/observations",
                    json={
                        "sequence": sequence,
                        "observed_at": datetime.now(UTC).isoformat(),
                        "version": VERSION,
                        "resource": os.environ["ATLAS_CONNECTOR_RESOURCE"],
                        "diagnostics": diagnostics(),
                    },
                )
                if result.status_code in {401, 403}:
                    raise SystemExit(
                        "Connector credential rejected; enroll or rotate through an administrator"
                    )
                result.raise_for_status()
                print(
                    json.dumps(
                        {"event": "observation_delivered", "sequence": sequence}
                    ),
                    flush=True,
                )
            except (httpx.HTTPError, OSError, subprocess.TimeoutExpired):
                print(json.dumps({"event": "observation_failed"}), flush=True)
                if once:
                    raise SystemExit(1)
            if once:
                return
            time.sleep(30)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    run(parser.parse_args().once)
