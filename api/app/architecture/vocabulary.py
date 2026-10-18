"""Controlled vocabularies for generic architecture facts.

These three vocabularies describe *where a fact sits over time and space* and are
deliberately separate from the concepts they are often confused with:

* **Architecture state** (Current / Candidate / Target) is a what-if scope.
* **Implementation status** (draft / in_progress / built / verified) is how far a
  contract has been engineered.
* **Lifecycle stage** is the strategic and retirement position of an item.
* **Operational status** is how mature an item actually is in operation.
* **Environment scope** is where the described fact applies.
* **Evidence classification / source type / confidence / verification status**
  describe *why we believe an architecture assertion* and are a separate family
  of vocabularies from the four above.

Keeping the words in one module means the database check constraints, the API
schemas and the frontend selectors share a single source of truth, so the
meanings cannot silently drift apart.
"""

from __future__ import annotations

from typing import Literal

LIFECYCLE_STAGES: tuple[str, ...] = (
    "strategic",
    "planned",
    "active",
    "transitional",
    "legacy",
    "retiring",
    "retired",
)

OPERATIONAL_STATUSES: tuple[str, ...] = (
    "unknown",
    "proposed",
    "tested",
    "live",
    "degraded",
    "suspended",
    "retiring",
    "decommissioned",
)

ENVIRONMENT_SCOPES: tuple[str, ...] = (
    "unknown",
    "development",
    "test",
    "sandbox",
    "staging",
    "production",
    "mixed",
)

# --- Architecture evidence vocabularies --------------------------------------
# Four deliberately separate vocabularies. Evidence classification says *what an
# assertion currently represents* (a confirmed fact, an assumption, an open
# decision, or future scope); source type says *what kind of artefact or
# observation* supports it; confidence says how sure the recorder is; and
# verification status says where the assertion stands in review. They are never
# collapsed into one another, and none of them reuses the lifecycle,
# operational-status or environment vocabularies above.

EVIDENCE_CLASSIFICATIONS: tuple[str, ...] = (
    "confirmed_by_requirements_document",
    "confirmed_by_current_implementation",
    "confirmed_by_field_mapping",
    "confirmed_by_user_working_knowledge",
    "assumption",
    "open_decision",
    "future_scope",
)

EVIDENCE_SOURCE_TYPES: tuple[str, ...] = (
    "document",
    "implementation",
    "mapping",
    "meeting",
    "message",
    "test",
    "ticket",
    "repository",
    "user_statement",
    "other",
)

CONFIDENCES: tuple[str, ...] = (
    "low",
    "medium",
    "high",
)

VERIFICATION_STATUSES: tuple[str, ...] = (
    "unverified",
    "verified",
    "disputed",
    "superseded",
)

# The classifications that represent a confirmed fact, versus the ones that
# represent something still to be settled. Used for grouping only; the database
# stores the raw classification.
CONFIRMED_EVIDENCE_CLASSIFICATIONS: tuple[str, ...] = (
    "confirmed_by_requirements_document",
    "confirmed_by_current_implementation",
    "confirmed_by_field_mapping",
    "confirmed_by_user_working_knowledge",
)

UNSETTLED_EVIDENCE_CLASSIFICATIONS: tuple[str, ...] = (
    "assumption",
    "open_decision",
    "future_scope",
)

# The exclusive evidence target arc. Exactly one of these columns is non-null.
EVIDENCE_TARGET_KINDS: tuple[str, ...] = (
    "architecture_object",
    "architecture_relationship",
    "integration",
    "integration_dependency",
    "solution_member",
)

EVIDENCE_TARGET_COLUMNS: dict[str, str] = {
    "architecture_object": "architecture_object_id",
    "architecture_relationship": "architecture_relationship_id",
    "integration": "integration_id",
    "integration_dependency": "integration_dependency_id",
    "solution_member": "solution_member_id",
}

LifecycleStage = Literal[
    "strategic",
    "planned",
    "active",
    "transitional",
    "legacy",
    "retiring",
    "retired",
]

OperationalStatus = Literal[
    "unknown",
    "proposed",
    "tested",
    "live",
    "degraded",
    "suspended",
    "retiring",
    "decommissioned",
]

EnvironmentScope = Literal[
    "unknown",
    "development",
    "test",
    "sandbox",
    "staging",
    "production",
    "mixed",
]

EvidenceClassification = Literal[
    "confirmed_by_requirements_document",
    "confirmed_by_current_implementation",
    "confirmed_by_field_mapping",
    "confirmed_by_user_working_knowledge",
    "assumption",
    "open_decision",
    "future_scope",
]

EvidenceSourceType = Literal[
    "document",
    "implementation",
    "mapping",
    "meeting",
    "message",
    "test",
    "ticket",
    "repository",
    "user_statement",
    "other",
]

Confidence = Literal["low", "medium", "high"]

VerificationStatus = Literal["unverified", "verified", "disputed", "superseded"]

EvidenceTargetKind = Literal[
    "architecture_object",
    "architecture_relationship",
    "integration",
    "integration_dependency",
    "solution_member",
]


def sql_in_list(values: tuple[str, ...]) -> str:
    """Render a parenthesised SQL ``IN`` list for the given code constants.

    ``NULL IN (...)`` evaluates to ``NULL`` (never ``FALSE``), so a column that
    uses one of these lists stays nullable while still rejecting unknown values.
    The values are module constants, never user input.
    """

    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
