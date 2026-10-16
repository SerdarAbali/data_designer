"""Hardcoded OpenCode endpoint allowlist tests (Slice B).

Covers required proofs 8-11: unknown endpoints, `/api/config`, credential
routes, and filesystem/shell/PTY/VCS/worktree/MCP/RPC routes are all rejected
before any network access.
"""

from __future__ import annotations

import pytest

from app.assistant import endpoints as ep

DENIED_ROUTES = [
    ("GET", "/api/config"),
    ("PATCH", "/api/experimental/config"),
    ("GET", "/api/credential"),
    ("POST", "/api/credential"),
    ("DELETE", "/api/credential/cred_1"),
    ("POST", "/api/credential/cred_1/activate"),
    ("GET", "/api/fs/read/etc/passwd"),
    ("GET", "/api/fs/list"),
    ("POST", "/api/experimental/fs/write"),
    ("GET", "/api/shell"),
    ("POST", "/api/shell"),
    ("GET", "/api/shell/sh_1/output"),
    ("GET", "/api/pty"),
    ("DELETE", "/api/pty/pty_1"),
    ("POST", "/api/experimental/persistent-pty/handoff"),
    ("GET", "/api/vcs/status"),
    ("POST", "/api/vcs/init"),
    ("GET", "/api/worktree"),
    ("POST", "/api/worktree/refresh"),
    ("POST", "/api/rpc/rpc_1/method"),
    ("GET", "/api/plugin"),
    ("POST", "/api/plugin/update"),
    ("GET", "/api/mcp"),
    ("GET", "/api/mcp/resource"),
    ("DELETE", "/api/experimental/mcp/server"),
    ("GET", "/api/integration"),
    ("POST", "/api/integration/int_1/connect/key"),
    ("POST", "/api/experimental/integration/wellknown"),
    ("GET", "/api/websearch/provider"),
    ("POST", "/api/websearch"),
    ("POST", "/api/pair"),
    ("GET", "/api/debug/location"),
    ("GET", "/api/permission/request"),
    ("GET", "/api/permission/saved"),
    ("POST", "/api/session/ses_1/shell"),
    ("POST", "/api/session/ses_1/command"),
    ("GET", "/api/session/ses_1/form"),
    ("PUT", "/api/session/ses_1/environment"),
    ("GET", "/api/session/ses_1/terminal"),
]


def _concrete(endpoint: ep.Endpoint) -> str:
    return endpoint.template.replace("{sessionID}", "ses_1").replace("{requestID}", "req_1")


@pytest.mark.parametrize("endpoint", ep.ALLOWED_ENDPOINTS)
def test_lifecycle_endpoints_resolve(endpoint: ep.Endpoint) -> None:
    assert ep.resolve_endpoint(endpoint.method.value, _concrete(endpoint)) is endpoint


@pytest.mark.parametrize("endpoint", ep.PROBE_ENDPOINTS)
def test_probe_endpoints_resolve(endpoint: ep.Endpoint) -> None:
    assert ep.resolve_endpoint(endpoint.method.value, _concrete(endpoint)) is endpoint


@pytest.mark.parametrize(("method", "path"), DENIED_ROUTES)
def test_denied_routes_are_rejected(method: str, path: str) -> None:
    with pytest.raises(ep.EndpointNotAllowed) as raised:
        ep.resolve_endpoint(method, path)
    assert raised.value.reason == "denied_route"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/session/ses_1/diff"),
        ("POST", "/api/session/ses_1/compact"),
        ("GET", "/api/agent"),
        ("POST", "/api/experimental/session/import"),
        ("GET", "/api/project"),
    ],
)
def test_unknown_routes_are_rejected(method: str, path: str) -> None:
    with pytest.raises(ep.EndpointNotAllowed) as raised:
        ep.resolve_endpoint(method, path)
    assert raised.value.reason == "unknown_route"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/info?token=abc"),
        ("GET", "/api/session/../config"),
        ("GET", "/api//config"),
        ("GET", "api/info"),
        ("GET", "/etc/passwd"),
    ],
)
def test_malformed_and_query_paths_are_rejected(method: str, path: str) -> None:
    with pytest.raises(ep.EndpointNotAllowed):
        ep.resolve_endpoint(method, path)


def test_method_must_match_the_allowlist() -> None:
    # The path is allowed, but not with this method.
    with pytest.raises(ep.EndpointNotAllowed):
        ep.resolve_endpoint("DELETE", "/api/info")
    with pytest.raises(ep.EndpointNotAllowed):
        ep.resolve_endpoint("GET", "/api/session")


def test_allowlist_has_no_denied_family() -> None:
    for endpoint in ep.ALLOWED_ENDPOINTS:
        assert not ep.is_denied_route(endpoint.template)
