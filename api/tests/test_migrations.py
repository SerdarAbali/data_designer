"""Focused migration-chain regression tests.

Alembic stores the applied revision in ``alembic_version.version_num`` which is
``VARCHAR(32)`` by default, so every revision identifier in the chain must fit.
These tests guard the chain statically and exercise every upgrade path in
Alembic's offline SQL mode (no database required, so they run in CI).
"""

from __future__ import annotations

import contextlib
import io
from itertools import pairwise
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_URL = "postgresql+psycopg://unused:unused@localhost/unused"

# Alembic's default version_num column width.
VERSION_COLUMN_LENGTH = 32
EXPECTED_HEAD = "0023_assistant_model_settings"
BASE_0016 = "0016_traceability"
EXPECTED_0017 = "0017_integration_integrity"
EXPECTED_0018 = "0018_demo_workspaces"
EXPECTED_0019 = "0019_helper_actions"
EXPECTED_0020 = "0020_helper_apply_undo"
EXPECTED_0021 = "0021_assistant_open_code"
EXPECTED_0022 = "0022_assistant_proposal_review"


def _config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", POSTGRES_URL)
    return config


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(_config())


def _linear_chain() -> list[str]:
    """Revisions ordered base -> head by walking down_revision from the head."""
    script = _script()
    chain: list[str] = []
    revision = script.get_revision(EXPECTED_HEAD)
    while revision is not None:
        chain.append(revision.revision)
        down = revision.down_revision
        revision = script.get_revision(down) if down else None
    return list(reversed(chain))


def test_every_revision_id_fits_the_version_column():
    script = _script()
    for revision in script.walk_revisions():
        assert len(revision.revision) <= VERSION_COLUMN_LENGTH, (
            f"revision id {revision.revision!r} exceeds VARCHAR({VERSION_COLUMN_LENGTH})"
        )
        if revision.down_revision is not None:
            # down_revision may be a tuple for merge revisions; this chain is linear.
            down = revision.down_revision
            if isinstance(down, str):
                assert len(down) <= VERSION_COLUMN_LENGTH
                assert script.get_revision(down) is not None, f"missing parent {down!r}"


def test_fresh_base_to_head_chain_is_linear_and_reaches_expected_head():
    script = _script()
    assert script.get_heads() == [EXPECTED_HEAD]
    chain = _linear_chain()
    assert chain[0] == "0001_auth"
    assert chain[-1] == EXPECTED_HEAD
    assert len(chain) == len(set(chain))
    for older, newer in pairwise(chain):
        assert script.get_revision(newer).down_revision == older


def test_upgrade_from_0016_to_head_includes_new_revisions():
    chain = _linear_chain()
    assert BASE_0016 in chain
    assert chain[chain.index(BASE_0016) + 1 :] == [
        EXPECTED_0017,
        EXPECTED_0018,
        EXPECTED_0019,
        EXPECTED_0020,
        EXPECTED_0021,
        EXPECTED_0022,
        EXPECTED_HEAD,
    ]


def test_current_development_revision_is_head_and_compatible():
    script = _script()
    head = script.get_revision(EXPECTED_HEAD)
    assert head is not None
    # The development database is stamped at this head, so it must remain the head.
    assert head.revision == EXPECTED_HEAD
    assert head.down_revision == EXPECTED_0022


def test_offline_upgrade_from_base_to_head_generates_demo_columns():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    sql = buffer.getvalue()
    assert f"UPDATE alembic_version SET version_num='{EXPECTED_HEAD}'" in sql
    assert "ALTER TABLE workspaces ADD COLUMN demo_preset" in sql
    assert "ALTER TABLE workspaces ADD COLUMN demo_assets" in sql
    assert "CREATE TABLE helper_change_sets" in sql
    assert "CREATE TABLE helper_change_operations" in sql
    assert "CREATE TABLE helper_audit_events" in sql
    assert "ADD COLUMN apply_summary" in sql
    assert "ADD COLUMN ownership" in sql
    assert "ADD COLUMN post_fingerprint" in sql
