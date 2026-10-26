import httpx

from atlasops.adapters.contracts import AdapterError, Capabilities
from atlasops.adapters.http import EnvironmentSecrets, SafeHTTP


class GitHubActions:
    capabilities = Capabilities(frozenset({"runs.list"}))

    def __init__(self, config, secret_ref=None):
        self.repository = config["repository"]
        if not self.repository:
            raise AdapterError("repository_required")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if secret_ref:
            headers["Authorization"] = f"Bearer {EnvironmentSecrets().get(secret_ref)}"
        self.http = SafeHTTP(config["url"] or "https://api.github.com", headers=headers)

    def runs(self):
        result = self.http.request("GET", f"/repos/{self.repository}/actions/runs", params={"per_page": 100})
        return [
            {
                "external_id": f"github:{r['id']}",
                "workflow": r["name"],
                "revision": r["head_sha"],
                "branch": r["head_branch"],
                "repository": self.repository,
                "status": r["conclusion"] or r["status"],
                "run_url": r["html_url"],
                "observed_at": r["updated_at"],
            }
            for r in result["workflow_runs"]
        ]


class Jenkins:
    capabilities = Capabilities(frozenset({"runs.list"}))

    def __init__(self, config, secret_ref=None):
        auth = (
            httpx.BasicAuth(config["username"], EnvironmentSecrets().get(secret_ref)) if secret_ref else None
        )
        self.http = SafeHTTP(config["url"], auth=auth)

    def runs(self):
        result = self.http.request(
            "GET",
            "/api/json",
            params={"tree": "jobs[name,url,lastBuild[number,result,timestamp,url,building]]"},
        )
        runs = []
        for job in result.get("jobs", [])[:100]:
            build = job.get("lastBuild")
            if build:
                from datetime import UTC, datetime

                runs.append(
                    {
                        "external_id": f"jenkins:{job['name']}:{build['number']}",
                        "workflow": job["name"],
                        "status": "running" if build["building"] else build["result"],
                        "run_url": build["url"],
                        "observed_at": datetime.fromtimestamp(build["timestamp"] / 1000, UTC).isoformat(),
                    }
                )
        return runs
