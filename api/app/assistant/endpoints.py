"""Hardcoded OpenCode endpoint allowlist for the Architecture Assistant runtime.

The runtime adapter must never accept an arbitrary OpenCode path. Every request
goes through :func:`resolve_endpoint`, which rejects anything that is not one of
the explicitly permitted operations *before* any network access happens.

The allowlist matches ``implementation_plan_opencode_agent.md`` section 5.3. Two
probe-only endpoints are additionally permitted for the startup capability probe
(``GET /api/info`` and ``GET /openapi.json``); neither is part of the assistant
runtime lifecycle, and neither is a secret-bearing route.

Secret-bearing and dangerous route families (``/api/config``, credential,
filesystem, shell, PTY, VCS, worktree, RPC, plugin-management, MCP, integration,
generic fetch) are never permitted and are reported with a distinct
``denied_route`` reason so they can be audited separately from typos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"
    DELETE = "DELETE"


class EnvelopePolicy(str, Enum):
    """How an OpenCode response payload is wrapped."""

    DATA = "data"
    """The payload is ``{"data": ...}`` (possibly with a ``location`` sibling)."""

    BARE = "bare"
    """The payload is the object itself (``/api/info``, ``/openapi.json``)."""

    STREAM = "stream"
    """A server-sent event stream (``/api/event``); read line by line."""


@dataclass(frozen=True)
class Endpoint:
    method: HttpMethod
    template: str
    envelope: EnvelopePolicy = EnvelopePolicy.DATA
    probe_only: bool = False

    def path(self, **params: str) -> str:
        return self.template.format(**params)


class EndpointNotAllowed(Exception):
    """Raised when a method/path pair is not on the hardcoded allowlist."""

    def __init__(self, reason: str, method: str, path: str) -> None:
        self.reason = reason
        self.method = method
        self.path = path
        super().__init__(f"OpenCode endpoint not allowed ({reason}): {method} {path}")


# -- permitted runtime lifecycle endpoints --------------------------------

CREATE_SESSION = Endpoint(HttpMethod.POST, "/api/session")
GET_SESSION = Endpoint(HttpMethod.GET, "/api/session/{sessionID}")
PATCH_SESSION = Endpoint(HttpMethod.PATCH, "/api/session/{sessionID}")
DELETE_SESSION = Endpoint(HttpMethod.DELETE, "/api/session/{sessionID}")
PROMPT = Endpoint(HttpMethod.POST, "/api/session/{sessionID}/prompt")
SYNTHETIC = Endpoint(HttpMethod.POST, "/api/session/{sessionID}/synthetic")
SWITCH_MODEL = Endpoint(HttpMethod.POST, "/api/session/{sessionID}/model")
INTERRUPT = Endpoint(HttpMethod.POST, "/api/session/{sessionID}/interrupt")
MESSAGES = Endpoint(HttpMethod.GET, "/api/session/{sessionID}/message")
PERMISSIONS = Endpoint(HttpMethod.GET, "/api/session/{sessionID}/permission")
PERMISSION_REPLY = Endpoint(
    HttpMethod.POST, "/api/session/{sessionID}/permission/{requestID}/reply"
)
WAIT = Endpoint(HttpMethod.POST, "/api/experimental/session/{sessionID}/wait")
EVENT = Endpoint(HttpMethod.GET, "/api/event", EnvelopePolicy.STREAM)
PROVIDERS = Endpoint(HttpMethod.GET, "/api/provider")
MODELS = Endpoint(HttpMethod.GET, "/api/model")

ALLOWED_ENDPOINTS: tuple[Endpoint, ...] = (
    CREATE_SESSION,
    GET_SESSION,
    PATCH_SESSION,
    DELETE_SESSION,
    PROMPT,
    SYNTHETIC,
    SWITCH_MODEL,
    INTERRUPT,
    MESSAGES,
    PERMISSIONS,
    PERMISSION_REPLY,
    WAIT,
    EVENT,
    PROVIDERS,
    MODELS,
)

# -- probe-only endpoints -------------------------------------------------

INFO = Endpoint(HttpMethod.GET, "/api/info", EnvelopePolicy.BARE, probe_only=True)
OPENAPI = Endpoint(HttpMethod.GET, "/openapi.json", EnvelopePolicy.BARE, probe_only=True)

PROBE_ENDPOINTS: tuple[Endpoint, ...] = (INFO, OPENAPI)

#: Contract paths the startup probe requires the live OpenAPI document to expose.
REQUIRED_CONTRACT_PATHS: frozenset[str] = frozenset(
    endpoint.template for endpoint in ALLOWED_ENDPOINTS
)

# -- denied route families ------------------------------------------------

# These are never permitted, even if a future allowlist edit would otherwise
# match them. They are reported as ``denied_route`` (audited) rather than
# ``unknown_route`` (a likely typo).
DENIED_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"^/api/config(/.*)?$",
        r"^/api/experimental/config(/.*)?$",
        r"^/api/credential(/.*)?$",
        r"^/api/fs(/.*)?$",
        r"^/api/experimental/fs(/.*)?$",
        r"^/api/shell(/.*)?$",
        r"^/api/pty(/.*)?$",
        r"^/api/experimental/persistent-pty(/.*)?$",
        r"^/api/vcs(/.*)?$",
        r"^/api/worktree(/.*)?$",
        r"^/api/rpc(/.*)?$",
        r"^/api/plugin(/.*)?$",
        r"^/api/mcp(/.*)?$",
        r"^/api/experimental/mcp(/.*)?$",
        r"^/api/integration(/.*)?$",
        r"^/api/experimental/integration(/.*)?$",
        r"^/api/websearch(/.*)?$",
        r"^/api/pair(/.*)?$",
        r"^/api/debug(/.*)?$",
        r"^/api/permission(/.*)?$",
        r"^/api/session/[^/]+/(shell|command|form)(/.*)?$",
        r"^/api/session/[^/]+/environment$",
        r"^/api/session/[^/]+/terminal(/.*)?$",
        r"^/api/experimental/session/[^/]+/terminal(/.*)?$",
    )
)

_TEMPLATE_CACHE: dict[str, re.Pattern[str]] = {}


def _compile_template(template: str) -> re.Pattern[str]:
    cached = _TEMPLATE_CACHE.get(template)
    if cached is not None:
        return cached
    segments = []
    for segment in template.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            segments.append("[^/]+")
        else:
            segments.append(re.escape(segment))
    compiled = re.compile("^" + "/".join(segments) + "$")
    _TEMPLATE_CACHE[template] = compiled
    return compiled


def _matches(template: str, path: str) -> bool:
    return bool(_compile_template(template).match(path))


def is_denied_route(path: str) -> bool:
    return any(pattern.match(path) for pattern in DENIED_ROUTE_PATTERNS)


def resolve_endpoint(method: str, path: str) -> Endpoint:
    """Resolve a concrete method/path pair to its :class:`Endpoint`.

    Raises :class:`EndpointNotAllowed` for anything that is not explicitly
    permitted, including query strings, traversal, and denied route families.
    This is called before any network access.
    """
    method_upper = str(method).upper()

    if not isinstance(path, str) or not path.startswith("/"):
        raise EndpointNotAllowed("malformed_path", method_upper, str(path))
    if path != "/openapi.json" and not path.startswith("/api/"):
        raise EndpointNotAllowed("unknown_route", method_upper, path)
    if "?" in path or "#" in path:
        raise EndpointNotAllowed("query_not_allowed", method_upper, path)
    if ".." in path or "//" in path:
        raise EndpointNotAllowed("malformed_path", method_upper, path)

    for endpoint in (*PROBE_ENDPOINTS, *ALLOWED_ENDPOINTS):
        if endpoint.method.value == method_upper and _matches(endpoint.template, path):
            return endpoint

    reason = "denied_route" if is_denied_route(path) else "unknown_route"
    raise EndpointNotAllowed(reason, method_upper, path)


def allowed_templates() -> frozenset[tuple[str, str]]:
    """``(method, template)`` pairs for the runtime lifecycle allowlist."""
    return frozenset((endpoint.method.value, endpoint.template) for endpoint in ALLOWED_ENDPOINTS)


def probe_templates() -> frozenset[tuple[str, str]]:
    return frozenset((endpoint.method.value, endpoint.template) for endpoint in PROBE_ENDPOINTS)
