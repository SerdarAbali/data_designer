"""Shared fixtures for the OpenCode feasibility verification suite.

The suite drives a real, fully isolated OpenCode server against a local scripted
mock provider. It never touches the developer's live OpenCode service, the
application database, or any application endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(HARNESS_DIR))

import harness  # noqa: E402

RESTRICTED_PORT = 4701
VARIANT_PORT = 4702
VARIANT_PORT_B = 4703


@pytest.fixture(scope="session")
def mock():
    provider = harness.MockProvider()
    provider.start()
    yield provider
    provider.stop()


@pytest.fixture(scope="session")
def restricted(mock):  # noqa: ARG001 - ordering only
    """Server running the shipped restricted profile, unmodified."""
    server = harness.spawn_server(harness.SCRATCH_ROOT / "restricted", RESTRICTED_PORT)
    yield server
    server.stop()


@pytest.fixture()
def variant_server(mock):  # noqa: ARG001 - ordering only
    """Factory for short-lived servers with a modified permission profile."""
    started: list[harness.OpenCodeServer] = []

    def factory(config: dict, *, name: str, port: int = VARIANT_PORT):
        server = harness.spawn_server(
            harness.SCRATCH_ROOT / name, port, name="sandbox", config=config
        )
        started.append(server)
        return server

    yield factory
    for server in started:
        server.stop()
