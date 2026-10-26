"""Start/stop only AtlasOps development processes belonging to this checkout."""

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local"
COMMANDS = {
    "api": [
        str(ROOT / ".venv/bin/uvicorn"),
        "atlasops.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
    "worker": [
        str(ROOT / ".venv/bin/celery"),
        "-A",
        "atlasops.worker:celery",
        "worker",
        "--concurrency=2",
        "--loglevel=INFO",
    ],
    "scheduler": [
        str(ROOT / ".venv/bin/celery"),
        "-A",
        "atlasops.worker:celery",
        "beat",
        "--schedule",
        str(STATE / "celerybeat-schedule"),
        "--loglevel=INFO",
    ],
    "web": [
        "node",
        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
        str(ROOT / "frontend"),
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
        "--strictPort",
    ],
}


def belongs(pid, role):
    try:
        proc = Path("/proc") / str(pid)
        if proc.stat().st_uid != os.getuid():
            return False
        args = proc.joinpath("cmdline").read_bytes().decode().split("\0")
        # Absolute executable/package paths bind process identity to this checkout. /proc/PID/cwd may
        # be unreadable across cloud sandbox namespaces, so do not depend on that symlink.
        if role == "web":
            return str(ROOT / "frontend/node_modules/vite/bin/vite.js") in args
        marker = "atlasops.main:app" if role == "api" else "atlasops.worker:celery"
        return (
            marker in args
            and any(str(ROOT / ".venv/bin") in a for a in args)
            and (role == "api" or ("worker" if role == "worker" else "beat") in args)
        )
    except (OSError, ValueError):
        return False


def find_pid(role):
    file = STATE / f"{role}.pid"
    if file.exists():
        pid = int(file.read_text())
        if belongs(pid, role):
            return pid
    # Adopt a matching process from the initial interactive setup, never an unrelated service.
    for proc in sorted(
        Path("/proc").iterdir(),
        key=lambda p: int(p.name) if p.name.isdigit() else 10**9,
    ):
        if proc.name.isdigit() and belongs(int(proc.name), role):
            return int(proc.name)
    return None


def manage(action):
    STATE.mkdir(exist_ok=True)
    for role, command in COMMANDS.items():
        pid = find_pid(role)
        if action in {"stop", "restart"} and pid:
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 8
            while belongs(pid, role) and time.monotonic() < deadline:
                time.sleep(0.1)
            if belongs(pid, role):
                raise SystemExit(
                    f"{role} has not stopped; inspect its log before restarting"
                )
            pid = None
        if action in {"start", "restart"} and not pid:
            with open(STATE / f"{role}.log", "ab") as log:
                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            pid = process.pid
        if pid:
            (STATE / f"{role}.pid").write_text(str(pid) + "\n")
        elif action == "stop":
            (STATE / f"{role}.pid").unlink(missing_ok=True)
        print(f"{role}: {'running' if pid else 'stopped'}")

    if action in {"start", "restart"}:
        import urllib.request

        for name, url in [
            ("api", "http://127.0.0.1:8000/health/ready"),
            ("web", "http://127.0.0.1:5173/"),
        ]:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline:
                        raise SystemExit(
                            f"{name} readiness failed; inspect .local/{name}.log"
                        )
                    time.sleep(0.25)
        print("API readiness and frontend HTTP request passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "restart"])
    args = parser.parse_args()
    manage(args.action)
