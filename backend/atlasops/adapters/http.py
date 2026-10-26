import json
import os
import re
from urllib.parse import urlsplit

import httpx

from atlasops.adapters.contracts import AdapterError
from atlasops.config import settings


class EnvironmentSecrets:
    def get(self, reference: str) -> str:
        if not re.fullmatch(r"ATLAS_SECRET_[A-Z0-9_]{1,80}", reference):
            raise AdapterError("invalid_secret_reference")
        value = os.environ.get(reference)
        if not value:
            raise AdapterError("credential_unavailable")
        return value


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    config = settings()
    allowed = {x.strip() for x in config.integration_hosts.split(",") if x.strip()}
    if parsed.hostname not in allowed:
        raise AdapterError("destination_not_allowed")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AdapterError("invalid_integration_url")
    if parsed.scheme != "https" and not (config.allow_insecure_integrations and parsed.scheme == "http"):
        raise AdapterError("tls_required")
    return url.rstrip("/")


class SafeHTTP:
    def __init__(self, url: str, *, headers=None, auth=None):
        self.url = validate_url(url)
        self.headers = headers or {}
        self.auth = auth

    def request(self, method: str, path: str, *, params=None, payload=None):
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise AdapterError("invalid_request_path")
        try:
            with httpx.Client(
                timeout=httpx.Timeout(15, connect=5),
                follow_redirects=False,
                headers=self.headers,
                auth=self.auth,
            ) as client:
                with client.stream(method, self.url + path, params=params, json=payload) as response:
                    if response.status_code in (401, 403):
                        raise AdapterError("permission_denied")
                    if response.status_code == 429:
                        raise AdapterError("rate_limited", retryable=True)
                    if response.status_code >= 500:
                        raise AdapterError("provider_unavailable", retryable=True)
                    if response.status_code >= 300:
                        raise AdapterError("provider_request_rejected")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 1024 * 1024:
                            raise AdapterError("response_too_large")
                    return json.loads(data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProxyError):
            raise AdapterError("provider_unreachable", retryable=True)
        except (ValueError, TypeError):
            raise AdapterError("invalid_provider_response")
