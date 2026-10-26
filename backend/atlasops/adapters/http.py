import json
import os
import re
import time
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


def validate_url(url: str, *, allowed_hosts: frozenset[str] | None = None) -> str:
    parsed = urlsplit(url)
    config = settings()
    allowed = {x.strip() for x in config.integration_hosts.split(",") if x.strip()}
    if allowed_hosts is not None:
        allowed = allowed | allowed_hosts
    if parsed.hostname not in allowed:
        raise AdapterError("destination_not_allowed")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AdapterError("invalid_integration_url")
    if parsed.scheme != "https" and not (config.allow_insecure_integrations and parsed.scheme == "http"):
        raise AdapterError("tls_required")
    return url.rstrip("/")


class SafeHTTP:
    def __init__(self, url: str, *, headers=None, auth=None, allowed_hosts=None, transport=None):
        self.url = validate_url(url, allowed_hosts=allowed_hosts)
        self.headers = headers or {}
        self.auth = auth
        self.transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        params=None,
        payload=None,
        timeout=15,
        max_response_bytes=1024 * 1024,
        deadline=None,
    ):
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise AdapterError("invalid_request_path")
        try:
            if deadline is not None:
                timeout = min(timeout, deadline - time.monotonic())
            if timeout <= 0:
                raise AdapterError("provider_timeout", retryable=True)
            with httpx.Client(
                timeout=httpx.Timeout(timeout, connect=min(5, timeout)),
                follow_redirects=False,
                headers=self.headers,
                auth=self.auth,
                transport=self.transport,
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
                        if deadline is not None and time.monotonic() >= deadline:
                            raise AdapterError("provider_timeout", retryable=True)
                        data.extend(chunk)
                        if len(data) > max_response_bytes:
                            raise AdapterError("response_too_large")
                    return json.loads(data)
        except httpx.TimeoutException:
            raise AdapterError("provider_timeout", retryable=True)
        except (httpx.NetworkError, httpx.ProxyError):
            raise AdapterError("provider_unreachable", retryable=True)
        except (ValueError, TypeError, RecursionError):
            raise AdapterError("invalid_provider_response")
