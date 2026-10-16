"""Redaction helpers for the Architecture Assistant runtime.

The gateway never forwards an OpenCode payload to the browser, and it never logs
a credential. This module centralises the scrubbing rules used by the runtime
adapter, the capability probe, and the status endpoint so an upstream error can
be turned into a safe, structured value.

Rules:
* known secret values are replaced verbatim;
* ``Authorization: Basic/Bearer`` material is masked;
* secret-looking query parameters are masked;
* mapping keys that look sensitive are replaced recursively.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable, Mapping
from typing import Any

REDACTED = "[redacted]"

SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "authorization",
    "credential",
    "cookie",
    "private_key",
    "private-key",
    "access_key",
    "access-key",
    "session_key",
    "session-key",
)

_AUTH_HEADER = re.compile(r"(?i)\b(basic|bearer)\s+[A-Za-z0-9._~+/=\-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|key|token|password|passwd|secret|credential)=)[^&\s]+"
)
_MIN_SECRET_LENGTH = 4


def correlation_id() -> str:
    """A short, non-sensitive identifier used to correlate logs and responses."""
    return "cor_" + secrets.token_hex(8)


def scrub(text: Any, secrets_: Iterable[str] = ()) -> str:
    """Return ``text`` with every known secret and credential pattern removed."""
    if text is None:
        return ""
    out = str(text)
    for secret in secrets_:
        if secret and len(secret) >= _MIN_SECRET_LENGTH:
            out = out.replace(secret, REDACTED)
    out = _AUTH_HEADER.sub(lambda match: f"{match.group(1)} {REDACTED}", out)
    out = _QUERY_SECRET.sub(lambda match: f"{match.group(1)}{REDACTED}", out)
    return out


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_mapping(value: Any, secrets_: Iterable[str] = ()) -> Any:
    """Recursively redact sensitive keys and known secret values."""
    secrets_list = tuple(secrets_)
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(key):
                result[key] = REDACTED
            else:
                result[key] = redact_mapping(item, secrets_list)
        return result
    if isinstance(value, list | tuple):
        return [redact_mapping(item, secrets_list) for item in value]
    if isinstance(value, str):
        return scrub(value, secrets_list)
    return value


def redact_url(url: str) -> str:
    """Strip userinfo and query/fragment from a URL, keeping scheme/host/path."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except (ValueError, AttributeError):
        return REDACTED
