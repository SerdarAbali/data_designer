"""Shared helpers for tests that need a locked or draft Current baseline.

Slice 8C made the Current write policy depend on the baseline lifecycle, so a
test that asserts "Current is read-only" must first lock the baseline. These
helpers keep that step identical everywhere instead of repeating the endpoint
call and its assertions in each suite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def baseline_url(workspace_id: str, state_id: str) -> str:
    return f"/api/workspaces/{workspace_id}/states/{state_id}/lock-baseline"


def validate_baseline(
    test_client: TestClient, workspace_id: str, state_id: str, headers: dict[str, str]
) -> dict:
    """Read the bounded baseline validation without writing anything."""
    response = test_client.post(
        baseline_url(workspace_id, state_id),
        json={"validate_only": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def lock_baseline(
    test_client: TestClient,
    workspace_id: str,
    state_id: str,
    headers: dict[str, str],
    *,
    confirm_empty: bool = True,
) -> dict:
    """Lock a Current baseline and return the response body.

    ``confirm_empty`` defaults to true so an empty capture locks without the
    explicit human confirmation step, which the tests that care about that step
    exercise directly.
    """
    response = test_client.post(
        baseline_url(workspace_id, state_id),
        json={"confirm_empty": confirm_empty},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["locked"] is True
    return body
