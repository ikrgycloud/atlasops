"""Bound and redact data before it is sent to a model or retained as investigation evidence."""

import re
from urllib.parse import urlsplit, urlunsplit

from atlasops.config import settings

SENSITIVE_FIELD = re.compile(
    r"password|passwd|secret|token|authorization|cookie|api[_-]?key|credential", re.I
)
KEY_PATTERN = re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})\b")
HEADER_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+")
VALUE_PATTERN = re.compile(r"(?i)((?:password|api[_-]?key|secret|access_token)\s*[:=]\s*)[^\s,;]+")


def redact(value, *, known_secrets=(), depth=0, bounded=True):
    if depth > (8 if bounded else 32):
        return "[depth limit]"
    if isinstance(value, dict):
        return {
            str(k)[:100]: "[redacted]"
            if SENSITIVE_FIELD.search(str(k))
            else redact(v, known_secrets=known_secrets, depth=depth + 1, bounded=bounded)
            for k, v in (list(value.items())[:40] if bounded else value.items())
        }
    if isinstance(value, list):
        return [
            redact(v, known_secrets=known_secrets, depth=depth + 1, bounded=bounded)
            for v in (value[:50] if bounded else value)
        ]
    if isinstance(value, str):
        for secret in known_secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        value = KEY_PATTERN.sub("[redacted]", value)
        value = HEADER_PATTERN.sub(r"\1[redacted]", value)
        value = VALUE_PATTERN.sub(r"\1[redacted]", value)
        if value.startswith(("https://", "http://")):
            try:
                parsed = urlsplit(value)
                hostname = parsed.hostname or ""
                if ":" in hostname:
                    hostname = "[" + hostname + "]"
                netloc = hostname + (":" + str(parsed.port) if parsed.port else "")
                value = urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
            except ValueError:
                value = "[invalid reference]"
        return value[:2000] if bounded else value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return "[unsupported value]"


def redact_evidence(value):
    # Mask a configured key even if copied into a telemetry string with no recognizable key prefix.
    # The value is never returned by this function or placed in diagnostic arguments.
    return redact(value, known_secrets=(settings().openai_api_key.get_secret_value(),))
