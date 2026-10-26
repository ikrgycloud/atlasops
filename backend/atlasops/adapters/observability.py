from datetime import datetime

from atlasops.adapters.contracts import AdapterError, Capabilities
from atlasops.adapters.http import EnvironmentSecrets, SafeHTTP


class Prometheus:
    capabilities = Capabilities(frozenset({"metrics.query"}))

    def __init__(self, config: dict, secret_ref=None):
        headers = {"Authorization": f"Bearer {EnvironmentSecrets().get(secret_ref)}"} if secret_ref else {}
        self.http = SafeHTTP(config["url"], headers=headers)

    def query(self, expression: str, at: datetime) -> dict:
        if not expression or len(expression) > 1024 or at.tzinfo is None:
            raise AdapterError("invalid_metric_query")
        result = self.http.request(
            "GET", "/api/v1/query", params={"query": expression, "time": at.timestamp(), "timeout": "5s"}
        )
        if result.get("status") != "success" or not isinstance(result.get("data", {}).get("result"), list):
            raise AdapterError("invalid_metric_response")
        return result["data"]


class Grafana:
    capabilities = Capabilities(frozenset({"dashboards.list", "health.read"}))

    def __init__(self, config: dict, secret_ref=None):
        headers = {"Authorization": f"Bearer {EnvironmentSecrets().get(secret_ref)}"} if secret_ref else {}
        self.http = SafeHTTP(config["url"], headers=headers)

    def health(self):
        return self.http.request("GET", "/api/health")

    def dashboards(self):
        return self.http.request("GET", "/api/search", params={"type": "dash-db", "limit": 100})
