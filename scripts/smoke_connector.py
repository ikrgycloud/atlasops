"""Exercise a real local Linux connector against the development API without printing credentials."""

import os
import subprocess
from pathlib import Path

import httpx
from atlasops.config import settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = settings()
    if config.mode != "development" or not config.dev_auth_enabled:
        raise SystemExit("This local smoke check is development-only")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15) as client:
        login = client.post(
            "/api/v1/auth/dev-token",
            json={
                "email": "administrator@atlasops.local",
                "secret": config.dev_auth_secret,
            },
        )
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        envs = client.get("/api/v1/environments").json()["items"]
        env = next(
            (e for e in envs if e["name"] == "Local Linux connector smoke"), None
        )
        if not env:
            response = client.post(
                "/api/v1/environments",
                json={
                    "name": "Local Linux connector smoke",
                    "provider": "onprem",
                    "resource_scope": ["local-cloud-linux"],
                    "description": "Actual local development Linux diagnostics",
                },
            )
            response.raise_for_status()
            env = response.json()
        enrolled = client.post(
            "/api/v1/connectors",
            json={
                "name": "Local smoke connector",
                "environment_id": env["id"],
                "resource": "local-cloud-linux",
            },
        )
        enrolled.raise_for_status()
        credential = enrolled.json()
        process_env = {
            **os.environ,
            "ATLAS_CONNECTOR_URL": "http://127.0.0.1:8000",
            "ATLAS_CONNECTOR_TOKEN": credential["enrollment_token"],
            "ATLAS_CONNECTOR_RESOURCE": "local-cloud-linux",
            "ATLAS_CONNECTOR_LOCAL_DEVELOPMENT": "true",
            "ATLAS_CONNECTOR_STATE": str(ROOT / ".local/connector-smoke-state.json"),
        }
        subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "connectors/linux/connector.py"),
                "--once",
            ],
            cwd=ROOT,
            env=process_env,
            check=True,
        )
        observations = client.get(f"/api/v1/environments/{env['id']}/resources")
        observations.raise_for_status()
        rows = observations.json()["items"]
        if (
            not rows
            or rows[0]["source"] != "linux-connector"
            or "cpu_load" not in rows[0]["data"]
        ):
            raise SystemExit("Expected Linux observations are missing")
        revoked = client.post(f"/api/v1/connectors/{credential['id']}/revoke")
        revoked.raise_for_status()
        print(
            "Actual Linux diagnostics delivered, scoped resource read verified, smoke credential revoked"
        )


if __name__ == "__main__":
    main()
