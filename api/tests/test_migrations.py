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
EXPECTED_HEAD = "0028_current_baseline"
BASE_0016 = "0016_traceability"
EXPECTED_0017 = "0017_integration_integrity"
EXPECTED_0018 = "0018_demo_workspaces"
EXPECTED_0019 = "0019_helper_actions"
EXPECTED_0020 = "0020_helper_apply_undo"
EXPECTED_0021 = "0021_assistant_open_code"
EXPECTED_0022 = "0022_assistant_proposal_review"
EXPECTED_0023 = "0023_assistant_model_settings"
EXPECTED_0024 = "0024_architecture_facts"
EXPECTED_0025 = "0025_contract_mediator"
EXPECTED_0026 = "0026_architecture_evidence"
EXPECTED_0027 = "0027_solution_integrations"


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
        EXPECTED_0023,
        EXPECTED_0024,
        EXPECTED_0025,
        EXPECTED_0026,
        EXPECTED_0027,
        EXPECTED_HEAD,
    ]


def test_current_development_revision_is_head_and_compatible():
    script = _script()
    head = script.get_revision(EXPECTED_HEAD)
    assert head is not None
    # The development database is stamped at this head, so it must remain the head.
    assert head.revision == EXPECTED_HEAD
    assert head.down_revision == EXPECTED_0027


def test_offline_upgrade_creates_architecture_evidence():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE architecture_evidence" in sql
    for column in (
        "architecture_object_id",
        "architecture_relationship_id",
        "integration_id",
        "integration_dependency_id",
        "solution_member_id",
        "evidence_classification",
        "source_type",
        "source_title",
        "source_reference",
        "source_locator",
        "summary",
        "confidence",
        "verification_status",
        "recorded_by",
        "recorded_at",
        "created_in_state_id",
    ):
        assert column in sql, column
    assert "ck_architecture_evidence_single_target" in sql
    assert "ck_architecture_evidence_classification" in sql
    assert "ck_architecture_evidence_source_type" in sql
    assert "ck_architecture_evidence_confidence" in sql
    assert "ck_architecture_evidence_verification_status" in sql
    assert "fk_architecture_evidence_object_tenant" in sql
    assert "fk_architecture_evidence_relationship_tenant" in sql
    assert "fk_architecture_evidence_integration_tenant" in sql
    assert "fk_architecture_evidence_dependency_tenant" in sql
    assert "fk_architecture_evidence_solution_member_tenant" in sql
    assert "ix_architecture_evidence_tenant" in sql
    assert "ix_architecture_evidence_state" in sql
    assert "ix_architecture_evidence_object" in sql
    assert "ix_architecture_evidence_relationship" in sql
    assert "ix_architecture_evidence_integration" in sql
    assert "ix_architecture_evidence_dependency" in sql
    assert "ix_architecture_evidence_solution_member" in sql
    # The composite foreign keys need the (id, tenant_id) uniques.
    assert "uq_architecture_relationships_id_tenant" in sql
    assert "uq_integration_dependencies_id_tenant" in sql
    assert "uq_solution_members_id_tenant" in sql
    # Evidence must be ON DELETE RESTRICT, never CASCADE.
    assert "ON DELETE RESTRICT" in sql


def test_offline_upgrade_creates_solution_integrations():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE solution_integrations" in sql
    for column in (
        "solution_object_id",
        "integration_id",
        "role",
        "description",
        "created_in_state_id",
        "created_at",
        "updated_at",
    ):
        assert column in sql, column
    assert "ck_solution_integrations_role" in sql
    assert "fk_solution_integrations_solution_tenant" in sql
    assert "fk_solution_integrations_integration_tenant" in sql
    assert "uq_solution_integrations_canonical" in sql
    assert "uq_solution_integrations_state" in sql
    assert "ix_solution_integrations_solution" in sql
    assert "ix_solution_integrations_integration" in sql
    assert "ON DELETE RESTRICT" in sql


def test_offline_downgrade_removes_only_the_solution_integration_additions():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.downgrade(
            _config(), "0027_solution_integrations:0026_architecture_evidence", sql=True
        )
    sql = buffer.getvalue()
    assert "DROP TABLE solution_integrations" in sql
    assert "DROP INDEX uq_solution_integrations_canonical" in sql
    assert "DROP INDEX ix_solution_integrations_integration" in sql
    # Nothing unrelated is removed.
    assert "DROP TABLE architecture_evidence" not in sql
    assert "DROP TABLE integrations" not in sql
    assert "DROP TABLE solution_members" not in sql
    assert "DROP COLUMN mediator_system_id" not in sql


def test_offline_downgrade_removes_only_the_evidence_additions():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.downgrade(
            _config(), "0026_architecture_evidence:0025_contract_mediator", sql=True
        )
    sql = buffer.getvalue()
    assert "DROP TABLE architecture_evidence" in sql
    assert "DROP CONSTRAINT uq_architecture_relationships_id_tenant" in sql
    assert "DROP CONSTRAINT uq_integration_dependencies_id_tenant" in sql
    assert "DROP CONSTRAINT uq_solution_members_id_tenant" in sql
    # Nothing unrelated is removed.
    assert "DROP TABLE integrations" not in sql
    assert "DROP TABLE architecture_objects" not in sql
    assert "DROP COLUMN mediator_system_id" not in sql
    assert "DROP COLUMN lifecycle_stage" not in sql


def test_offline_upgrade_adds_mediator_columns_to_integrations():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE integrations ADD COLUMN mediator_system_id" in sql
    assert "ALTER TABLE integrations ADD COLUMN mediator_responsibility" in sql
    assert "fk_integrations_mediator_system" in sql
    assert "ck_integrations_mediator_distinct" in sql
    assert "ix_integrations_mediator_system" in sql


def test_offline_downgrade_removes_only_the_mediator_additions():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.downgrade(_config(), "0025_contract_mediator:0024_architecture_facts", sql=True)
    sql = buffer.getvalue()
    assert "DROP INDEX ix_integrations_mediator_system" in sql
    assert "DROP CONSTRAINT ck_integrations_mediator_distinct" in sql
    assert "DROP CONSTRAINT fk_integrations_mediator_system" in sql
    assert "DROP COLUMN mediator_responsibility" in sql
    assert "DROP COLUMN mediator_system_id" in sql
    # The downgrade must not touch any pre-existing column or table.
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN lifecycle_stage" not in sql
    assert "DROP COLUMN environment_scope" not in sql
    assert "DROP COLUMN source_system_id" not in sql


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
    assert "ADD COLUMN lifecycle_stage" in sql
    assert "ADD COLUMN operational_status" in sql
    assert "ADD COLUMN environment_scope" in sql
    assert "CREATE TABLE integration_state_overrides" in sql
