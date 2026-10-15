"""Guided architecture import tests: matching, commit, provenance, and undo."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureObject,
    CatalogSystem,
    ImportBatch,
    ImportRowResult,
    InformationObject,
    SolutionMember,
    Tenant,
    User,
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("app.config.settings.cookie_secure", False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with testing_sessions() as db:
            yield db

    main.app.dependency_overrides[get_session] = override_session
    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"imports-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="imports@example.test",
                password_hash=hash_password("imports-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "imports@example.test", "password": "imports-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def create_workspace(test_client, name="Import Workspace", disciplines=None) -> str:
    body: dict = {"name": name}
    if disciplines is not None:
        body["disciplines"] = disciplines
    response = test_client.post(
        "/api/workspaces", json=body, headers=csrf_headers(test_client)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_system(test_client, **payload) -> dict:
    response = test_client.post(
        "/api/catalog/systems", json=payload, headers=csrf_headers(test_client)
    )
    assert response.status_code == 201, response.text
    return response.json()


def payload(
    import_type: str,
    headers: list[str],
    rows: list[list[str]],
    mapping: dict[str, str],
    *,
    filename: str = "sample.xlsx",
    sheet: str = "Sheet1",
    decisions: list[dict] | None = None,
) -> dict:
    body = {
        "import_type": import_type,
        "headers": headers,
        "rows": rows,
        "column_mapping": mapping,
        "source_filename": filename,
        "sheet_name": sheet,
    }
    if decisions is not None:
        body["decisions"] = decisions
    return body


def preview(test_client, workspace_id: str, body: dict):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/imports/preview",
        json=body,
        headers=csrf_headers(test_client),
    )


def commit(test_client, workspace_id: str, body: dict):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/imports/commit",
        json=body,
        headers=csrf_headers(test_client),
    )


SYSTEM_HEADERS = ["Name", "Description", "Owner", "Domain", "Lifecycle", "External ID", "Aliases"]
SYSTEM_MAPPING = {
    "name": "Name",
    "description": "Description",
    "owner": "Owner",
    "business_domain": "Domain",
    "lifecycle": "Lifecycle",
    "external_id": "External ID",
    "aliases": "Aliases",
}


def test_system_import_matches_creates_updates_and_skips(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(
        test_client,
        name="Payment Gateway",
        external_identifier="SYS-001",
        metadata={"aliases": ["PayGW"]},
    )
    create_system(test_client, name="Billing Platform", description="Legacy billing")

    rows = [
        ["Payment Gateway", "", "", "", "", "SYS-001", ""],
        ["New CRM", "Customer records", "Sales", "CRM", "active", "SYS-002", ""],
        ["Billing Platform", "Updated billing", "Finance", "Billing", "", "", ""],
        ["Skip Me", "", "", "", "", "", ""],
    ]
    body = payload("system", SYSTEM_HEADERS, rows, SYSTEM_MAPPING)
    preview_response = preview(test_client, workspace_id, body)
    assert preview_response.status_code == 200, preview_response.text
    previewed = preview_response.json()
    assert previewed["blocked_count"] == 0
    assert previewed["rows"][0]["matches"][0]["method"] == "external_id"
    assert previewed["rows"][1]["matches"] == []
    assert previewed["rows"][2]["matches"][0]["method"] == "exact_name"

    commit_body = payload(
        "system",
        SYSTEM_HEADERS,
        rows,
        SYSTEM_MAPPING,
        decisions=[
            {"row_number": 1, "decision": "use_existing"},
            {"row_number": 2, "decision": "create"},
            {"row_number": 3, "decision": "update"},
            {"row_number": 4, "decision": "skip"},
        ],
    )
    response = commit(test_client, workspace_id, commit_body)
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["counts"]["created"] == 1
    assert batch["counts"]["updated"] == 1
    assert batch["counts"]["matched"] == 1
    assert batch["counts"]["skipped"] == 1
    assert batch["source_filename"] == "sample.xlsx"
    assert batch["sheet_name"] == "Sheet1"
    assert batch["rows"][0]["external_id"] == "SYS-001"

    with sessions() as db:
        systems = list(db.scalars(select(CatalogSystem).where(CatalogSystem.deleted_at.is_(None))))
        names = {system.name for system in systems}
        assert "New CRM" in names
        billing = next(system for system in systems if system.name == "Billing Platform")
        assert billing.description == "Updated billing"
        assert billing.extra_metadata["owner"] == "Finance"
        assert billing.extra_metadata["business_domain"] == "Billing"
        assert "lifecycle" not in billing.extra_metadata
        new_crm = next(system for system in systems if system.name == "New CRM")
        assert new_crm.external_identifier == "SYS-002"
        registry = db.scalar(
            select(ArchitectureObject).where(ArchitectureObject.id == new_crm.id)
        )
        assert registry is not None and registry.kind == "system"
        stored = db.scalar(select(ImportBatch).where(ImportBatch.id == UUID(batch["id"])))
        assert stored is not None and stored.counts["created"] == 1
        row_results = list(
            db.scalars(
                select(ImportRowResult)
                .where(ImportRowResult.batch_id == stored.id)
                .order_by(ImportRowResult.row_number)
            )
        )
        assert [result.status for result in row_results] == [
            "matched",
            "created",
            "updated",
            "skipped",
        ]
        assert row_results[0].external_id == "SYS-001"
        assert row_results[2].before["description"] == "Legacy billing"


def test_reimport_matches_existing_and_creates_no_duplicates(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(test_client, name="Ledger", external_identifier="SYS-LED")

    rows = [
        ["Ledger", "Core ledger", "Finance", "", "", "SYS-LED", ""],
        ["Warehouse", "Storage", "Ops", "", "", "SYS-WH", ""],
    ]
    first = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            rows,
            SYSTEM_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "update"},
                {"row_number": 2, "decision": "create"},
            ],
        ),
    )
    assert first.status_code == 201, first.text
    assert first.json()["counts"]["created"] == 1
    assert first.json()["counts"]["updated"] == 1

    second = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            rows,
            SYSTEM_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "use_existing"},
                {"row_number": 2, "decision": "use_existing"},
            ],
        ),
    )
    assert second.status_code == 201, second.text
    counts = second.json()["counts"]
    assert counts["created"] == 0
    assert counts["matched"] == 2

    with sessions() as db:
        names = list(
            db.scalars(
                select(CatalogSystem.name).where(CatalogSystem.deleted_at.is_(None))
            )
        )
        assert sorted(names) == ["Ledger", "Warehouse"]
        assert len(list(db.scalars(select(ImportBatch)))) == 2


def test_alias_matching_and_similar_name_never_auto_merges(client) -> None:
    test_client, _ = client
    workspace_id = create_workspace(test_client)
    create_system(test_client, name="Payments Hub", metadata={"aliases": ["Pay Hub"]})

    rows = [
        ["Pay Hub", "", "", "", "", "", ""],
        ["Payments Hub!", "", "", "", "", "", ""],
    ]
    response = preview(
        test_client, workspace_id, payload("system", SYSTEM_HEADERS, rows, SYSTEM_MAPPING)
    )
    assert response.status_code == 200, response.text
    previewed = response.json()
    alias_row = previewed["rows"][0]
    assert alias_row["matches"][0]["method"] == "alias"
    assert alias_row["suggested_decision"] == "use_existing"

    similar_row = previewed["rows"][1]
    assert similar_row["matches"][0]["method"] == "similar_name"
    assert similar_row["matches"][0]["score"] >= 0.9
    assert similar_row["warnings"][0]["row"] == 2
    assert similar_row["suggested_decision"] == "create"

    # Creating a row whose name only resembles an existing one must not merge it.
    committed = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            rows,
            SYSTEM_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "use_existing"},
                {"row_number": 2, "decision": "create"},
            ],
        ),
    )
    assert committed.status_code == 201, committed.text
    assert committed.json()["counts"]["created"] == 1


INFO_HEADERS = [
    "Name",
    "Description",
    "Owner",
    "Authoritative System",
    "Classification",
    "External ID",
]
INFO_MAPPING = {
    "name": "Name",
    "description": "Description",
    "owner": "Owner",
    "authoritative_system": "Authoritative System",
    "classification": "Classification",
    "external_id": "External ID",
}


def create_object(test_client, system_id: str, name: str) -> dict:
    response = test_client.post(
        f"/api/catalog/systems/{system_id}/objects",
        json={"name": name, "label": name},
        headers=csrf_headers(test_client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_information_object_import_resolves_authoritative_system(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(
        test_client, name="CRM Platform", metadata={"aliases": ["Customer Relationship Mgmt"]}
    )

    rows = [
        [
            "Customer",
            "Customer master data",
            "Data Office",
            "Customer Relationship Mgmt",
            "Confidential",
            "IO-1",
        ],
        ["Order", "Order records", "Ops", "Missing System", "Internal", "IO-2"],
    ]
    previewed = preview(
        test_client, workspace_id, payload("information_object", INFO_HEADERS, rows, INFO_MAPPING)
    )
    assert previewed.status_code == 200, previewed.text
    body = previewed.json()
    assert body["blocked_count"] == 1
    assert body["rows"][0]["issues"] == []
    assert "does not match a catalog system" in body["rows"][1]["issues"][0]["message"]
    assert body["resolved_reference_counts"]["authoritative_systems_resolved"] == 1

    committed = commit(
        test_client,
        workspace_id,
        payload(
            "information_object",
            INFO_HEADERS,
            rows,
            INFO_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
            ],
        ),
    )
    assert committed.status_code == 201, committed.text
    counts = committed.json()["counts"]
    assert counts["created"] == 1
    assert counts["blocked"] == 1

    with sessions() as db:
        records = list(db.scalars(select(InformationObject)))
        assert len(records) == 1
        assert records[0].name == "Customer"
        assert records[0].classification == "Confidential"
        assert records[0].external_identifier == "IO-1"
        registry = db.scalar(
            select(ArchitectureObject).where(ArchitectureObject.id == records[0].object_id)
        )
        assert registry is not None and registry.kind == "information_object"


INTEGRATION_HEADERS = [
    "Name",
    "Description",
    "Source System",
    "Target System",
    "Source Object",
    "Target Object",
    "Integration Type",
    "Owner",
    "Lifecycle",
    "External ID",
    "Contract Reference",
]
INTEGRATION_MAPPING = {
    "name": "Name",
    "description": "Description",
    "source_system": "Source System",
    "target_system": "Target System",
    "source_object": "Source Object",
    "target_object": "Target Object",
    "integration_type": "Integration Type",
    "owner": "Owner",
    "lifecycle": "Lifecycle",
    "external_id": "External ID",
    "contract_reference": "Contract Reference",
}


def test_integration_import_resolves_endpoints_and_blocks_ambiguous(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    source = create_system(test_client, name="Source App")
    target = create_system(test_client, name="Target App")
    ambiguous = create_system(test_client, name="Ambiguous App")
    create_object(test_client, source["id"], "Customer")
    create_object(test_client, target["id"], "Invoice")
    create_object(test_client, ambiguous["id"], "Alpha")
    create_object(test_client, ambiguous["id"], "Beta")

    rows = [
        [
            "Customer to Invoice",
            "Push customers",
            "Source App",
            "Target App",
            "",
            "",
            "one-way",
            "Integration Team",
            "active",
            "INT-1",
            "",
        ],
        ["Ambiguous flow", "", "Source App", "Ambiguous App", "", "", "", "", "", "INT-2", ""],
        [
            "Bad type flow",
            "",
            "Source App",
            "Target App",
            "Customer",
            "Invoice",
            "telepathy",
            "",
            "",
            "INT-3",
            "",
        ],
    ]
    previewed = preview(
        test_client,
        workspace_id,
        payload("integration", INTEGRATION_HEADERS, rows, INTEGRATION_MAPPING),
    )
    assert previewed.status_code == 200, previewed.text
    body = previewed.json()
    assert body["blocked_count"] == 2
    assert body["resolved_reference_counts"]["endpoints_resolved"] == 1
    assert "objects" in body["rows"][1]["issues"][0]["message"]
    assert "not recognized" in body["rows"][2]["issues"][0]["message"]

    committed = commit(
        test_client,
        workspace_id,
        payload(
            "integration",
            INTEGRATION_HEADERS,
            rows,
            INTEGRATION_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
                {"row_number": 3, "decision": "create"},
            ],
        ),
    )
    assert committed.status_code == 201, committed.text
    counts = committed.json()["counts"]
    assert counts["created"] == 1
    assert counts["blocked"] == 2

    with sessions() as db:
        from app.models import Integration

        contracts = list(db.scalars(select(Integration).where(Integration.deleted_at.is_(None))))
        assert len(contracts) == 1
        assert contracts[0].name == "Customer to Invoice"
        assert contracts[0].interaction_type == "ONE_WAY"
        assert contracts[0].graph["nodes"] == []
        assert contracts[0].extra_metadata == {"owner": "Integration Team", "lifecycle": "active"}


def test_integration_contract_reference_updates_instead_of_duplicating(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    source = create_system(test_client, name="Billing")
    target = create_system(test_client, name="Data Lake")
    source_object = create_object(test_client, source["id"], "Invoice")
    target_object = create_object(test_client, target["id"], "Invoice Record")
    created = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source["id"],
            "source_object_id": source_object["id"],
            "target_system_id": target["id"],
            "target_object_id": target_object["id"],
            "name": "Billing export",
            "description": "Nightly export",
        },
        headers=csrf_headers(test_client),
    )
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]

    rows = [
        [
            "Billing export row",
            "Refreshed purpose",
            "Billing",
            "Data Lake",
            "",
            "",
            "",
            "",
            "",
            "",
            "Billing export",
        ],
    ]
    previewed = preview(
        test_client,
        workspace_id,
        payload("integration", INTEGRATION_HEADERS, rows, INTEGRATION_MAPPING),
    )
    assert previewed.status_code == 200, previewed.text
    matched = previewed.json()["rows"][0]["matches"][0]
    assert matched["id"] == integration_id
    assert previewed.json()["rows"][0]["suggested_decision"] == "use_existing"

    committed = commit(
        test_client,
        workspace_id,
        payload(
            "integration",
            INTEGRATION_HEADERS,
            rows,
            INTEGRATION_MAPPING,
            decisions=[{"row_number": 1, "decision": "update", "target_id": integration_id}],
        ),
    )
    assert committed.status_code == 201, committed.text
    assert committed.json()["counts"]["updated"] == 1

    with sessions() as db:
        from app.models import Integration

        contracts = list(db.scalars(select(Integration).where(Integration.deleted_at.is_(None))))
        assert len(contracts) == 1
        assert contracts[0].description == "Refreshed purpose"


SOLUTION_HEADERS = ["Solution", "Description", "Owner", "External ID", "Included Systems"]
SOLUTION_MAPPING = {
    "name": "Solution",
    "description": "Description",
    "owner": "Owner",
    "external_id": "External ID",
    "included_systems": "Included Systems",
}


def test_solution_import_reuses_canonical_systems(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(test_client, name="Core Banking", external_identifier="SYS-CORE")
    create_system(test_client, name="Card Services", metadata={"aliases": ["Cards"]})

    rows = [
        [
            "Payments Solution",
            "End-to-end payments",
            "Solution Team",
            "SOL-1",
            "Core Banking; Cards",
        ],
        ["Broken Solution", "", "Solution Team", "SOL-2", "Core Banking; Unknown System"],
    ]
    previewed = preview(
        test_client, workspace_id, payload("solution", SOLUTION_HEADERS, rows, SOLUTION_MAPPING)
    )
    assert previewed.status_code == 200, previewed.text
    body = previewed.json()
    assert body["blocked_count"] == 1
    assert body["resolved_reference_counts"]["member_systems_resolved"] == 2
    assert "Unknown System" in body["rows"][1]["issues"][0]["message"]

    committed = commit(
        test_client,
        workspace_id,
        payload(
            "solution",
            SOLUTION_HEADERS,
            rows,
            SOLUTION_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
            ],
        ),
    )
    assert committed.status_code == 201, committed.text
    assert committed.json()["counts"]["created"] == 1
    assert committed.json()["counts"]["blocked"] == 1

    with sessions() as db:
        from app.models import SolutionBoundary

        boundaries = list(db.scalars(select(SolutionBoundary)))
        assert len(boundaries) == 1
        assert boundaries[0].name == "Payments Solution"
        assert boundaries[0].external_identifier == "SOL-1"
        members = list(
            db.scalars(
                select(SolutionMember).where(
                    SolutionMember.solution_object_id == boundaries[0].object_id
                )
            )
        )
        assert len(members) == 2
        # Membership references canonical systems; no system copies were created.
        systems = list(
            db.scalars(select(CatalogSystem).where(CatalogSystem.deleted_at.is_(None)))
        )
        assert sorted(system.name for system in systems) == ["Card Services", "Core Banking"]
        member_ids = {member.system_id for member in members}
        assert member_ids == {system.id for system in systems}


def test_information_import_requires_enabled_discipline(client) -> None:
    test_client, _ = client
    workspace_id = create_workspace(test_client, disciplines=["solution"])
    body = payload(
        "information_object",
        INFO_HEADERS,
        [["Customer", "", "Owner", "Some System", "", ""]],
        INFO_MAPPING,
    )
    response = preview(test_client, workspace_id, body)
    assert response.status_code == 422
    assert "Information Architecture is not enabled" in response.json()["detail"]


def test_import_requires_csrf_and_workspace_access(client) -> None:
    test_client, _ = client
    workspace_id = create_workspace(test_client)
    body = payload("system", SYSTEM_HEADERS, [["Anything", "", "", "", "", "", ""]], SYSTEM_MAPPING)
    without_csrf = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/preview", json=body
    )
    assert without_csrf.status_code == 403
    missing_workspace = preview(test_client, str(uuid4()), body)
    assert missing_workspace.status_code == 404


def test_undo_reverses_only_that_batch_and_reports_conflicts(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(test_client, name="Existing System", description="Original")

    rows = [
        ["Existing System", "Imported description", "", "", "", "", ""],
        ["Imported Alpha", "", "", "", "", "SYS-A", ""],
        ["Imported Beta", "", "", "", "", "SYS-B", ""],
    ]
    first = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            rows,
            SYSTEM_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "update"},
                {"row_number": 2, "decision": "create"},
                {"row_number": 3, "decision": "create"},
            ],
        ),
    )
    assert first.status_code == 201, first.text
    batch_id = first.json()["id"]
    assert first.json()["counts"]["created"] == 2

    # A second batch must survive the undo of the first.
    second = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            [["Imported Gamma", "", "", "", "", "SYS-G", ""]],
            SYSTEM_MAPPING,
            decisions=[{"row_number": 1, "decision": "create"}],
        ),
    )
    assert second.status_code == 201, second.text

    undone = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{batch_id}/undo",
        headers=csrf_headers(test_client),
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "undone"
    statuses = [row["status"] for row in undone.json()["rows"]]
    assert statuses == ["undone", "undone", "undone"]

    with sessions() as db:
        active = {
            system.name
            for system in db.scalars(
                select(CatalogSystem).where(CatalogSystem.deleted_at.is_(None))
            )
        }
        assert active == {"Existing System", "Imported Gamma"}
        restored = db.scalar(select(CatalogSystem).where(CatalogSystem.name == "Existing System"))
        assert restored.description == "Original"
        assert len(list(db.scalars(select(ImportBatch)))) == 2

    # Undo cannot run twice.
    again = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{batch_id}/undo",
        headers=csrf_headers(test_client),
    )
    assert again.status_code == 409


def test_undo_reports_conflict_when_record_changed_after_import(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    create_system(test_client, name="Contended System", description="Original")
    rows = [["Contended System", "Imported description", "", "", "", "", ""]]
    committed = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            rows,
            SYSTEM_MAPPING,
            decisions=[{"row_number": 1, "decision": "update"}],
        ),
    )
    assert committed.status_code == 201, committed.text
    batch_id = committed.json()["id"]

    system_id = None
    with sessions() as db:
        system_id = db.scalar(
            select(CatalogSystem.id).where(CatalogSystem.name == "Contended System")
        )
    edited = test_client.patch(
        f"/api/catalog/systems/{system_id}",
        json={"description": "Edited after import"},
        headers=csrf_headers(test_client),
    )
    assert edited.status_code == 200

    undone = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{batch_id}/undo",
        headers=csrf_headers(test_client),
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "undo_blocked"
    assert undone.json()["rows"][0]["status"] == "conflict"
    assert "changed after the import" in undone.json()["rows"][0]["message"]
    with sessions() as db:
        system = db.scalar(select(CatalogSystem).where(CatalogSystem.name == "Contended System"))
        assert system.description == "Edited after import"


def test_include_objects_enriches_current_state_with_selection(client) -> None:
    test_client, _ = client
    workspace_id = create_workspace(test_client)

    # The Current state is initialized before any import so it starts empty.
    states = test_client.get(f"/api/workspaces/{workspace_id}/states")
    assert states.status_code == 200, states.text
    current = next(state for state in states.json() if state["state_type"] == "current")
    assert current["nodes"] == []
    current_id = current["id"]

    committed = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            [
                ["Alpha App", "", "", "", "", "SYS-A", ""],
                ["Beta App", "", "", "", "", "SYS-B", ""],
            ],
            SYSTEM_MAPPING,
            decisions=[
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
            ],
        ),
    )
    assert committed.status_code == 201, committed.text
    untouched = create_system(test_client, name="Untouched App")
    systems = test_client.get("/api/catalog/systems").json()
    by_name = {system["name"]: system for system in systems}
    alpha_id = by_name["Alpha App"]["id"]
    beta_id = by_name["Beta App"]["id"]
    alpha_object = create_object(test_client, alpha_id, "Customers")
    beta_object = create_object(test_client, beta_id, "Customers")
    integration = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": alpha_id,
            "source_object_id": alpha_object["id"],
            "target_system_id": beta_id,
            "target_object_id": beta_object["id"],
            "name": "Alpha to Beta",
        },
        headers=csrf_headers(test_client),
    )
    assert integration.status_code == 201, integration.text
    integration_id = integration.json()["id"]

    solution = commit(
        test_client,
        workspace_id,
        payload(
            "solution",
            SOLUTION_HEADERS,
            [["Alpha Solution", "", "Owner", "SOL-A", "Alpha App; Beta App"]],
            SOLUTION_MAPPING,
            decisions=[{"row_number": 1, "decision": "create"}],
        ),
    )
    assert solution.status_code == 201, solution.text
    solution_objects = test_client.get(
        f"/api/workspaces/{workspace_id}/architecture-objects"
    ).json()
    solution_id = next(
        item["id"] for item in solution_objects if item["kind"] == "solution_boundary"
    )

    # An integration whose endpoint system is not selected is skipped.
    partial = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current_id}/include-objects",
        json={"system_ids": [alpha_id], "integration_ids": [integration_id]},
        headers=csrf_headers(test_client),
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["added_occurrences"] == 1
    assert partial.json()["added_relationships"] == 0
    assert partial.json()["skipped"][0]["kind"] == "integration"

    full = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current_id}/include-objects",
        json={
            "system_ids": [alpha_id, beta_id],
            "integration_ids": [integration_id],
            "architecture_object_ids": [solution_id],
        },
        headers=csrf_headers(test_client),
    )
    assert full.status_code == 200, full.text
    body = full.json()
    assert body["added_occurrences"] == 2
    assert body["added_relationships"] == 3
    node_objects = {node["object_id"] for node in body["state"]["nodes"]}
    assert node_objects == {alpha_id, beta_id, solution_id}
    assert untouched["id"] not in node_objects
    relationship_types = [item["type"] for item in body["state"]["relationships"]]
    assert relationship_types.count("Contains") == 2
    assert relationship_types.count("Consumes") == 1

    # Re-including the same selection changes nothing.
    repeat = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current_id}/include-objects",
        json={
            "system_ids": [alpha_id, beta_id],
            "integration_ids": [integration_id],
            "architecture_object_ids": [solution_id],
        },
        headers=csrf_headers(test_client),
    )
    assert repeat.status_code == 200
    assert repeat.json()["added_occurrences"] == 0
    assert repeat.json()["added_relationships"] == 0

    # The Current state is still read-only through the general update path.
    blocked = test_client.put(
        f"/api/workspaces/{workspace_id}/states/{current_id}",
        json={"description": "Attempted edit"},
        headers=csrf_headers(test_client),
    )
    assert blocked.status_code == 409


def test_undo_can_be_retried_after_the_blocking_reference_is_removed(client) -> None:
    test_client, sessions = client
    workspace_id = create_workspace(test_client)
    systems_batch = commit(
        test_client,
        workspace_id,
        payload(
            "system",
            SYSTEM_HEADERS,
            [["Referenced App", "", "", "", "", "SYS-REF", ""]],
            SYSTEM_MAPPING,
            decisions=[{"row_number": 1, "decision": "create"}],
        ),
    )
    assert systems_batch.status_code == 201, systems_batch.text
    systems_batch_id = systems_batch.json()["id"]
    with sessions() as db:
        referenced = db.scalar(
            select(CatalogSystem).where(CatalogSystem.name == "Referenced App")
        )
        referenced_id = referenced.id

    info_batch = commit(
        test_client,
        workspace_id,
        payload(
            "information_object",
            INFO_HEADERS,
            [["Dependent", "", "Owner", "Referenced App", "", "IO-REF"]],
            INFO_MAPPING,
            decisions=[{"row_number": 1, "decision": "create"}],
        ),
    )
    assert info_batch.status_code == 201, info_batch.text

    blocked = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{systems_batch_id}/undo",
        headers=csrf_headers(test_client),
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "undo_blocked"
    assert "information object 'Dependent'" in blocked.json()["rows"][0]["message"]
    with sessions() as db:
        assert db.get(CatalogSystem, referenced_id).deleted_at is None

    released = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{info_batch.json()['id']}/undo",
        headers=csrf_headers(test_client),
    )
    assert released.status_code == 200
    assert released.json()["status"] == "undone"

    retried = test_client.post(
        f"/api/workspaces/{workspace_id}/imports/{systems_batch_id}/undo",
        headers=csrf_headers(test_client),
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "undone"
    with sessions() as db:
        assert db.get(CatalogSystem, referenced_id).deleted_at is not None
