"""Deployment configuration tests (Slice B).

Required proof 19: the OpenCode service publishes no host port. Also asserts the
pinned runtime, the private network, and server-side-only credentials.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
COMPOSE_DEV = REPO_ROOT / "docker-compose.dev.yml"
DOCKERFILE = REPO_ROOT / "assistant-runtime" / "Dockerfile"


def _service_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.rstrip() == "services:":
            start = index
            break
    if start is None:
        return ""
    block: list[str] = []
    active = False
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        if re.match(rf"^  {re.escape(name)}:\s*$", line):
            active = True
            continue
        if active:
            if re.match(r"^  \S", line):
                break
            block.append(line)
    return "\n".join(block)


def test_opencode_service_publishes_no_host_port() -> None:
    block = _service_block(COMPOSE.read_text(encoding="utf-8"), "opencode")
    assert block, "opencode service is missing from docker-compose.yml"
    assert re.search(r"^\s+expose:", block, re.M), "opencode must expose a port internally"
    assert not re.search(r"^\s+ports:", block, re.M), "opencode must not publish a host port"


def test_dev_overlay_does_not_publish_opencode_port() -> None:
    dev = COMPOSE_DEV.read_text(encoding="utf-8")
    # The dev overlay must not add an opencode service with a host port.
    assert not re.search(r"^\s*opencode:", dev, re.M)


def test_opencode_is_isolated_on_the_assistant_network() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    block = _service_block(text, "opencode")
    assert "- assistant" in block
    assert "- default" not in block
    assert "assistant:" in text  # network declared


def test_credentials_are_server_side_only() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    opencode = _service_block(text, "opencode")
    api = _service_block(text, "api")
    web = _service_block(text, "web")

    assert "OPENCODE_PASSWORD" in opencode
    assert "ASSISTANT_OPENCODE_PASSWORD" in api
    assert "OPENCODE_PASSWORD" not in web
    assert "ASSISTANT_" not in web


def test_opencode_data_directory_is_a_bounded_volume() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "opencode_data:/data" in text
    assert re.search(r"^volumes:\n(?:.*\n)*?\s+opencode_data:", text, re.M)


def test_runtime_is_pinned_to_v2_0_30() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG OPENCODE_VERSION=2.0.30" in dockerfile
    assert "@opencode/cli@${OPENCODE_VERSION}" in dockerfile
    # The build asserts the installed version, so drift cannot ship.
    assert "opencode v${OPENCODE_VERSION}" in dockerfile


def test_restricted_profile_is_deny_all_with_no_ask_rules() -> None:
    import json

    profile = json.loads((REPO_ROOT / "assistant-runtime" / "opencode.json").read_text())
    assert {"action": "*", "resource": "*", "effect": "deny"} in profile["permissions"]
    assert '"ask"' not in json.dumps(profile)
