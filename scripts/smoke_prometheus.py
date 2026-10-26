"""Validate the actual managed Prometheus source through the running AtlasOps API."""

import httpx
from atlasops.config import settings


def main():
    config = settings()
    if config.mode != "development" or not config.dev_auth_enabled:
        raise SystemExit("This local smoke check is development-only")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20) as client:
        response = client.post(
            "/api/v1/auth/dev-token",
            json={
                "email": "administrator@atlasops.local",
                "secret": config.dev_auth_secret,
            },
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        envs = client.get("/api/v1/environments").json()["items"]
        env = next(e for e in envs if e["name"] == "Local Linux connector smoke")
        integrations = client.get("/api/v1/integrations").json()["items"]
        integration = next(
            (i for i in integrations if i["name"] == "Managed local Prometheus"), None
        )
        if not integration:
            response = client.post(
                "/api/v1/integrations",
                json={
                    "name": "Managed local Prometheus",
                    "environment_id": env["id"],
                    "provider": "prometheus",
                    "config": {
                        "url": "http://127.0.0.1:9090",
                        "query": 'up{job="atlasops"}',
                    },
                },
            )
            response.raise_for_status()
            integration = response.json()
        response = client.post(f"/api/v1/integrations/{integration['id']}/test")
        response.raise_for_status()
        result = response.json()
        if result["status"] != "CONNECTED" or result["observations"] < 1:
            raise SystemExit(
                "Managed Prometheus did not provide fresh AtlasOps scrape evidence"
            )
        print(
            "Managed Prometheus CONNECTED; actual AtlasOps scrape observations persisted"
        )


if __name__ == "__main__":
    main()
