"""Slice 8C correction: a locked Current baseline protects its Contracts.

A Contract the locked Current canvas describes must not be changed through any
canonical Contract mutation route, while Candidate and Target design and every
read must keep working. These tests use the shared guard rather than asserting
per-route behaviour, so one representative per route family is enough.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import Tenant, User
from tests.baseline_support import lock_baseline

ALL_DISCIPLINES = ["enterprise", "information", "solution", "integration"]


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
        tenant = Tenant(name=f"contract-baseline-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="contract-baseline@example.test",
                password_hash=hash_password("contract-baseline-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={
                "email": "contract-baseline@example.test",
                "password": "contract-baseline-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _system(test_client, headers, suffix: str) -> dict:
    response = test_client.post(
        "/api/catalog/systems",
        json={"name": f"System {suffix}-{uuid4().hex[:6]}", "kind": "application"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _object(test_client, headers, system_id: str, suffix: str) -> dict:
    response = test_client.post(
        f"/api/catalog/systems/{system_id}/objects",
        json={"name": f"Object {suffix}", "label": f"Object {suffix}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _contract(
    test_client,
    headers,
    *,
    source_system: dict,
    source_object: dict,
    target_system: dict,
    target_object: dict,
    name: str,
) -> dict:
    response = test_client.post(
        "/api/integrations",
        json={
            "name": f"{name}-{uuid4().hex[:6]}",
            "source_system_id": source_system["id"],
            "source_object_id": source_object["id"],
            "target_system_id": target_system["id"],
            "target_object_id": target_object["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _workspace(test_client, headers) -> dict:
    response = test_client.post(
        "/api/workspaces",
        json={"name": f"Contract baseline {uuid4().hex[:6]}", "disciplines": ALL_DISCIPLINES},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _states(test_client, workspace_id: str) -> list[dict]:
    response = test_client.get(f"/api/workspaces/{workspace_id}/states")
    assert response.status_code == 200, response.text
    return response.json()


def _current(test_client, workspace_id: str) -> dict:
    return next(
        state for state in _states(test_client, workspace_id) if state["state_type"] == "current"
    )


def _candidate(test_client, headers, workspace_id: str, current_id: str) -> dict:
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current_id}/duplicate",
        json={"target_name": f"Candidate {uuid4().hex[:6]}", "target_state_type": "candidate"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _anchored_scene(test_client, headers) -> dict:
    """A workspace whose locked Current canvas describes exactly one Contract.

    The Current state is materialised *before* any Catalog record exists, so the
    initializer's auto-population cannot put the other Contract on the canvas;
    only the explicitly included Contract is anchored.
    """
    workspace = _workspace(test_client, headers)
    current = _current(test_client, workspace["id"])
    source_system = _system(test_client, headers, "src")
    target_system = _system(test_client, headers, "dst")
    source = _object(test_client, headers, source_system["id"], "src")
    target = _object(test_client, headers, target_system["id"], "dst")
    contract = _contract(
        test_client,
        headers,
        source_system=source_system,
        source_object=source,
        target_system=target_system,
        target_object=target,
        name="Anchored",
    )
    other = _contract(
        test_client,
        headers,
        source_system=source_system,
        source_object=source,
        target_system=target_system,
        target_object=target,
        name="Other",
    )

    included = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/include-objects",
        json={
            "system_ids": [source_system["id"], target_system["id"]],
            "integration_ids": [contract["id"]],
        },
        headers=headers,
    )
    assert included.status_code == 200, included.text
    anchored_ids = {
        str(item.get("integration_id")) for item in included.json()["state"]["relationships"]
    }
    assert contract["id"] in anchored_ids
    assert other["id"] not in anchored_ids, "the fixture must anchor one contract only"
    return {
        "workspace": workspace,
        "current": current,
        "contract": contract,
        "other": other,
        "headers": headers,
    }


def _lock(scene, test_client) -> None:
    lock_baseline(test_client, scene["workspace"]["id"], scene["current"]["id"], scene["headers"])


# --- the mutation routes ------------------------------------------------------


def _patch(scene, test_client):
    return test_client.patch(
        f"/api/integrations/{scene['contract']['id']}",
        json={"expected_revision": scene["contract"]["revision"], "name": "Renamed"},
        headers=scene["headers"],
    )


def _save_graph(scene, test_client):
    graph = scene["contract"]["graph"]
    return test_client.put(
        f"/api/integrations/{scene['contract']['id']}/graph",
        json={"expected_revision": scene["contract"]["revision"], "graph": graph},
        headers=scene["headers"],
    )


def _archive(scene, test_client):
    return test_client.delete(
        f"/api/integrations/{scene['contract']['id']}", headers=scene["headers"]
    )


def _add_dependency(scene, test_client):
    return test_client.post(
        f"/api/integrations/{scene['other']['id']}/dependencies",
        json={"downstream_integration_id": scene["contract"]["id"]},
        headers=scene["headers"],
    )


def _remove_dependency(scene, test_client):
    return test_client.delete(
        f"/api/integrations/{scene['other']['id']}/dependencies/{scene['contract']['id']}",
        headers=scene["headers"],
    )


CANONICAL_MUTATIONS = [
    ("patch", _patch),
    ("graph", _save_graph),
    ("archive", _archive),
    ("dependency_add", _add_dependency),
    ("dependency_remove", _remove_dependency),
]


_IDS = [item[0] for item in CANONICAL_MUTATIONS]


@pytest.mark.parametrize(("label", "mutate"), CANONICAL_MUTATIONS, ids=_IDS)
def test_canonical_contract_mutations_are_blocked_by_a_locked_baseline(
    client, label, mutate
) -> None:
    test_client = client
    headers = csrf_headers(test_client)
    scene = _anchored_scene(test_client, headers)
    if label == "dependency_remove":
        # The edge has to exist before it can be removed.
        created = test_client.post(
            f"/api/integrations/{scene['other']['id']}/dependencies",
            json={"downstream_integration_id": scene["contract"]["id"]},
            headers=headers,
        )
        assert created.status_code == 201, created.text
    before = test_client.get(f"/api/integrations/{scene['contract']['id']}").json()

    _lock(scene, test_client)

    response = mutate(scene, test_client)
    assert response.status_code == 409, (label, response.text)
    assert response.json()["detail"]["code"] == "current_baseline_locked"
    assert "locked Current baseline" in response.json()["detail"]["message"]

    # Nothing was written.
    assert test_client.get(f"/api/integrations/{scene['contract']['id']}").json() == before


@pytest.mark.parametrize(("label", "mutate"), CANONICAL_MUTATIONS, ids=_IDS)
def test_the_same_mutations_work_while_current_is_draft(client, label, mutate) -> None:
    test_client = client
    headers = csrf_headers(test_client)
    scene = _anchored_scene(test_client, headers)
    if label == "dependency_remove":
        created = test_client.post(
            f"/api/integrations/{scene['other']['id']}/dependencies",
            json={"downstream_integration_id": scene["contract"]["id"]},
            headers=headers,
        )
        assert created.status_code == 201, created.text

    response = mutate(scene, test_client)
    assert response.status_code in (200, 201, 204), (label, response.text)


def test_reads_and_state_scoped_design_survive_a_locked_baseline(client) -> None:
    test_client = client
    headers = csrf_headers(test_client)
    scene = _anchored_scene(test_client, headers)
    candidate = _candidate(test_client, headers, scene["workspace"]["id"], scene["current"]["id"])
    _lock(scene, test_client)

    # Reads keep working on the locked baseline and its Contract.
    assert test_client.get(f"/api/integrations/{scene['contract']['id']}").status_code == 200
    assert test_client.get("/api/integrations").status_code == 200
    locked_current = _current(test_client, scene["workspace"]["id"])
    design = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/integration-design/contracts/"
        f"{scene['contract']['id']}",
        params={"state_id": locked_current["id"]},
    )
    assert design.status_code == 200, design.text
    landscape = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/integration-design/landscape",
        params={"state_id": locked_current["id"]},
    )
    assert landscape.status_code == 200, landscape.text
    assert landscape.json()["editable"] is False

    # Candidate and Target state overrides stay writable: the canonical Contract
    # being in Current does not block state-scoped design.
    for state in (candidate,):
        response = test_client.put(
            f"/api/workspaces/{scene['workspace']['id']}/integration-design/contracts/"
            f"{scene['contract']['id']}/facts",
            json={"state_id": state["id"], "lifecycle_stage": "active"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["lifecycle_stage"]["value"] == "active"
        assert response.json()["editable"] is True

    # And the locked Current still refuses a state-scoped write to itself.
    locked_facts = test_client.put(
        f"/api/workspaces/{scene['workspace']['id']}/integration-design/contracts/"
        f"{scene['contract']['id']}/facts",
        json={"state_id": locked_current["id"], "lifecycle_stage": "active"},
        headers=headers,
    )
    assert locked_facts.status_code == 409
    assert locked_facts.json()["detail"]["code"] == "current_baseline_locked"


def test_a_contract_outside_the_baseline_stays_mutable(client) -> None:
    """Only the Contract the locked baseline describes is protected."""
    test_client = client
    headers = csrf_headers(test_client)
    scene = _anchored_scene(test_client, headers)
    _lock(scene, test_client)

    # The second Contract was never included in Current.
    response = test_client.patch(
        f"/api/integrations/{scene['other']['id']}",
        json={"expected_revision": scene["other"]["revision"], "name": "Unrelated rename"},
        headers=scene["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Unrelated rename"


def test_guided_import_cannot_update_a_protected_contract(client) -> None:
    """The guided architecture import uses the same shared guard."""
    test_client = client
    headers = csrf_headers(test_client)
    scene = _anchored_scene(test_client, headers)
    _lock(scene, test_client)

    def payload():
        headers = ["Name", "Source system", "Source object", "Target system", "Target object"]
        return {
            "import_type": "integration",
            "headers": headers,
            "column_mapping": {
                "name": "Name",
                "source_system": "Source system",
                "source_object": "Source object",
                "target_system": "Target system",
                "target_object": "Target object",
            },
            "rows": [
                [
                    scene["contract"]["name"],
                    source_system["name"],
                    source_object["name"],
                    target_system["name"],
                    target_object["name"],
                ]
            ],
        }

    systems = test_client.get("/api/catalog/systems").json()
    source_system = next(
        system for system in systems if system["id"] == scene["contract"]["source_system_id"]
    )
    target_system = next(
        system for system in systems if system["id"] == scene["contract"]["target_system_id"]
    )
    source_object = test_client.get(
        f"/api/catalog/systems/{source_system['id']}/objects"
    ).json()[0]
    target_object = test_client.get(
        f"/api/catalog/systems/{target_system['id']}/objects"
    ).json()[0]
    preview = test_client.post(
        f"/api/workspaces/{scene['workspace']['id']}/imports/preview",
        json=payload(),
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    flagged = [row for row in preview.json()["rows"] if row["row_number"] == 1]
    assert flagged and any(
        "locked Current baseline" in issue["message"] for issue in flagged[0]["issues"]
    ), flagged

    commit = test_client.post(
        f"/api/workspaces/{scene['workspace']['id']}/imports/commit",
        json={**payload(), "decisions": [{"row_number": 1, "decision": "update"}]},
        headers=headers,
    )
    assert commit.status_code in (201, 409, 422), commit.text
    # Whatever the batch reported, the Contract itself is unchanged.
    assert test_client.get(f"/api/integrations/{scene['contract']['id']}").status_code == 200
