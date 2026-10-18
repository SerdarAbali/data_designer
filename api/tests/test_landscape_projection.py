"""Integration Landscape projection additions (Slice 4: Landscape filtering).

The Landscape is a read-only projection, so these tests only assert what the
projection returns: stable endpoint identities, effective state-specific facts,
mediation, evidence counts, and derived information references — computed in a
bounded number of queries and in a deterministic order.
"""

from uuid import UUID, uuid4

from sqlalchemy import event

from tests.test_integrations import client as client_fixture
from tests.test_integrations import create_endpoint, csrf_headers
from tests.test_scenarios import mapped_contract, string_endpoint

client = client_fixture

FULL = ["enterprise", "information", "solution", "integration"]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _workspace(test_client, headers, disciplines=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Landscape"), "disciplines": list(disciplines or FULL)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Candidate"), "target_state_type": "candidate"},
        headers=headers,
    ).json()
    target = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Target"), "target_state_type": "target"},
        headers=headers,
    ).json()
    return workspace, current, candidate, target


def _design(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/integration-design"


def _landscape(test_client, workspace_id, state_id):
    response = test_client.get(
        f"{_design(workspace_id)}/landscape", params={"state_id": state_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _summary(landscape, contract_id):
    return next(item for item in landscape["contracts"] if item["id"] == contract_id)


def _patch_contract(test_client, headers, contract_id, **fields):
    current = test_client.get(f"/api/integrations/{contract_id}").json()
    return test_client.patch(
        f"/api/integrations/{contract_id}",
        json={"expected_revision": current["revision"], **fields},
        headers=headers,
    )


def _put_facts(test_client, headers, workspace_id, contract_id, state_id, **fields):
    return test_client.put(
        f"{_design(workspace_id)}/contracts/{contract_id}/facts",
        json={"state_id": state_id, **fields},
        headers=headers,
    )


def _system(test_client, headers, *, name=None, kind="application"):
    response = test_client.post(
        "/api/catalog/systems",
        json={"name": name or _unique("System"), "kind": kind},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- 1: stable endpoint identities -------------------------------------------


def test_landscape_returns_stable_source_and_target_ids_and_labels(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Customer push", source, target)

    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert summary["source"]["system_id"] == source["system"]["id"]
    assert summary["source"]["system_name"] == source["system"]["name"]
    assert summary["source"]["object_id"] == source["object"]["id"]
    assert summary["source"]["object_name"] == source["object"]["label"]
    assert summary["target"]["system_id"] == target["system"]["id"]
    assert summary["target"]["object_id"] == target["object"]["id"]
    assert summary["target"]["object_name"] == target["object"]["label"]
    assert summary["implementation_status"] == "draft"
    assert summary["interaction_type"] == "REQUEST_RESPONSE"


# --- 2-4: effective facts ------------------------------------------------------


def test_landscape_returns_effective_candidate_and_target_facts(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate, target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    dest = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Facts", source, dest)
    patched = _patch_contract(
        test_client,
        headers,
        contract["id"],
        lifecycle_stage="active",
        operational_status="live",
        environment_scope="production",
    )
    assert patched.status_code == 200, patched.text

    canonical = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert canonical["lifecycle_stage"]["value"] == "active"
    assert canonical["operational_status"]["value"] == "live"
    assert canonical["environment_scope"]["value"] == "production"
    assert canonical["lifecycle_stage"]["overridden"] is False

    candidate_override = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="retiring", environment_scope="staging",
    )
    assert candidate_override.status_code == 200, candidate_override.text
    candidate_view = _summary(
        _landscape(test_client, workspace["id"], candidate["id"]), contract["id"]
    )
    assert candidate_view["lifecycle_stage"]["value"] == "retiring"
    assert candidate_view["lifecycle_stage"]["override"] == "retiring"
    assert candidate_view["environment_scope"]["value"] == "staging"
    # A fact without an override still reports the canonical baseline.
    assert candidate_view["operational_status"]["value"] == "live"

    target_override = _put_facts(
        test_client, headers, workspace["id"], contract["id"], target["id"],
        operational_status="degraded",
    )
    assert target_override.status_code == 200, target_override.text
    target_view = _summary(
        _landscape(test_client, workspace["id"], target["id"]), contract["id"]
    )
    assert target_view["operational_status"]["value"] == "degraded"
    assert target_view["lifecycle_stage"]["value"] == "active"

    # Current is untouched by the Candidate/Target overrides.
    again = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert again["lifecycle_stage"]["value"] == "active"
    assert again["operational_status"]["value"] == "live"


# --- 5-6: mediation ------------------------------------------------------------


def test_landscape_explicit_mediation_fields(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "SF", "name")
    dest = string_endpoint(test_client, "NS", "code")
    contract = mapped_contract(test_client, "Salesforce to NetSuite", source, dest)
    mediator = _system(test_client, headers, kind="runtime")
    patched = _patch_contract(
        test_client, headers, contract["id"], mediator_system_id=mediator["id"]
    )
    assert patched.status_code == 200, patched.text

    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert summary["mediated"] is True
    assert summary["explicit_mediator"] is True
    assert summary["mediation_source"] == "explicit"
    assert summary["mediator"]["system_id"] == mediator["id"]
    assert summary["mediator"]["explicit"] is True
    # The mediator is never substituted for a business endpoint.
    assert summary["source"]["system_id"] == source["system"]["id"]
    assert summary["target"]["system_id"] == dest["system"]["id"]


def test_landscape_legacy_heuristic_mediation(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "SF", "name")
    dest = string_endpoint(test_client, "NS", "code")
    contract = mapped_contract(test_client, "Legacy", source, dest)
    patched = test_client.patch(
        f"/api/catalog/systems/{dest['system']['id']}",
        json={"kind": "integration_runtime"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert summary["mediated"] is True
    assert summary["explicit_mediator"] is False
    assert summary["mediation_source"] == "legacy_endpoint_heuristic"
    assert summary["mediator"]["system_id"] == dest["system"]["id"]
    assert summary["mediator"]["explicit"] is False
    # A direct contract stays direct.
    other_source = string_endpoint(test_client, "Other", "name")
    other_target = string_endpoint(test_client, "Other target", "code")
    plain = mapped_contract(test_client, "Plain", other_source, other_target)
    plain_summary = _summary(
        _landscape(test_client, workspace["id"], current["id"]), plain["id"]
    )
    assert plain_summary["mediated"] is False
    assert plain_summary["mediation_source"] == "none"
    assert plain_summary["mediator"] is None


# --- 7: evidence count ---------------------------------------------------------


def test_landscape_evidence_count(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "SF", "name")
    dest = string_endpoint(test_client, "NS", "code")
    contract = mapped_contract(test_client, "Evidenced", source, dest)

    before = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert before["evidence_count"] == 0
    created = test_client.post(
        f"/api/workspaces/{workspace['id']}/evidence",
        json={
            "target_kind": "integration",
            "target_id": contract["id"],
            "evidence_classification": "assumption",
            "source_type": "meeting",
            "source_title": "Design review",
            "source_reference": "meeting-notes/2026-01-02",
            "summary": "The team assumed nightly batching.",
            "confidence": "medium",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    after = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    assert after["evidence_count"] == 1


# --- 8-9: information references ----------------------------------------------


def test_landscape_information_references_derive_from_field_refs(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Mapped", source, target)

    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    references = summary["referenced_information_objects"]
    by_id = {item["object_id"]: item for item in references}
    assert source["object"]["id"] in by_id
    assert target["object"]["id"] in by_id
    source_ref = by_id[source["object"]["id"]]
    target_ref = by_id[target["object"]["id"]]
    assert source_ref["name"] == source["object"]["name"]
    assert source_ref["label"] == source["object"]["label"]
    assert source_ref["system_id"] == source["system"]["id"]
    assert source_ref["system_name"] == source["system"]["name"]
    assert "source" in source_ref["anchors"]
    assert "target" in target_ref["anchors"]
    # Deterministic ordering: by label, then id.
    ordered = [(item["label"].casefold(), item["object_id"]) for item in references]
    assert ordered == sorted(ordered)


def test_landscape_never_invents_information_references(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = create_endpoint(test_client, "Unmapped", "name")
    target = create_endpoint(test_client, "Unmapped target", "code")
    created = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source["system"]["id"],
            "source_object_id": source["object"]["id"],
            "target_system_id": target["system"]["id"],
            "target_object_id": target["object"]["id"],
            "name": "No references",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]

    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract_id)
    # Objects are named "Unmapped"/"Unmapped target" but nothing is referenced, so
    # no reference is synthesized from the names or the endpoints.
    assert summary["referenced_information_objects"] == []


# --- 10: bounded queries -------------------------------------------------------


def _select_count(sessions, action) -> int:
    engine = sessions().get_bind()
    counter = {"count": 0}

    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            counter["count"] += 1

    event.listen(engine, "before_cursor_execute", record)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return counter["count"]


def test_landscape_information_projection_avoids_one_query_per_contract(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    mapped_contract(test_client, "First", source, target)

    one = _select_count(
        sessions,
        lambda: _landscape(test_client, workspace["id"], current["id"]),
    )

    second_source = string_endpoint(test_client, "CRM two", "name")
    second_target = string_endpoint(test_client, "ERP two", "code")
    mapped_contract(test_client, "Second", second_source, second_target)
    third_source = string_endpoint(test_client, "CRM three", "name")
    third_target = string_endpoint(test_client, "ERP three", "code")
    mapped_contract(test_client, "Third", third_source, third_target)

    landscape = _landscape(test_client, workspace["id"], current["id"])
    assert len(landscape["contracts"]) == 3
    three = _select_count(
        sessions,
        lambda: _landscape(test_client, workspace["id"], current["id"]),
    )
    # The information projection is bulk-loaded: adding Contracts adds no queries.
    assert three == one


# --- 11-13: determinism and isolation -----------------------------------------


def test_landscape_contract_ordering_is_deterministic(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    names = ["Zulu", "Alpha", "Mike"]
    for name in names:
        source = string_endpoint(test_client, f"{name} source", "name")
        target = string_endpoint(test_client, f"{name} target", "code")
        mapped_contract(test_client, name, source, target)

    first = _landscape(test_client, workspace["id"], current["id"])["contracts"]
    second = _landscape(test_client, workspace["id"], current["id"])["contracts"]
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert [item["name"] for item in first] == sorted(item["name"] for item in first)


def test_landscape_tenant_isolation(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    mapped_contract(test_client, "Owned", source, target)

    other, other_current, _other_candidate, _other_target = _workspace(test_client, headers)
    other_landscape = _landscape(test_client, other["id"], other_current["id"])
    assert other_landscape["contracts"] == []
    # The original workspace still sees exactly its own contract.
    assert len(_landscape(test_client, workspace["id"], current["id"])["contracts"]) == 1


def test_landscape_workspace_and_state_isolation(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    other, _other_current, _other_candidate, _other_target = _workspace(test_client, headers)

    # A state that belongs to another workspace can never be read.
    forbidden = test_client.get(
        f"{_design(other['id'])}/landscape", params={"state_id": current["id"]}
    )
    assert forbidden.status_code == 404
    # A workspace without the discipline is still gated.
    gated, gated_current, _gc, _gt = _workspace(test_client, headers, ["information"])
    assert (
        test_client.get(
            f"{_design(gated['id'])}/landscape", params={"state_id": gated_current["id"]}
        ).status_code
        == 404
    )


def test_contract_detail_and_flow_carry_information_references(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Detail", source, target)

    detail = test_client.get(
        f"{_design(workspace['id'])}/contracts/{contract['id']}",
        params={"state_id": current["id"]},
    ).json()
    assert detail["contract"]["referenced_information_objects"]
    flow = test_client.get(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/flow",
        params={"state_id": current["id"]},
    ).json()
    assert flow["contract"]["referenced_information_objects"]
    # The Landscape payload does not duplicate detail/mapping/scenario content.
    summary = _summary(_landscape(test_client, workspace["id"], current["id"]), contract["id"])
    for forbidden in ("phases", "source_interface", "target_interface", "scenarios"):
        assert forbidden not in summary


def test_landscape_projection_issues_no_writes(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Read-only", source, target)

    from app.models import Integration

    def snapshot():
        with sessions() as db:
            row = db.get(Integration, UUID(contract["id"]))
            return (row.revision, row.updated_at, row.lifecycle_stage)

    before = snapshot()
    _landscape(test_client, workspace["id"], current["id"])
    _landscape(test_client, workspace["id"], current["id"])
    assert snapshot() == before
