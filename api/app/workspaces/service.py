import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    Scenario,
)

# Workspace portability (export/import/fork) lives in ``app.workspaces.bundle`` so
# that all three paths share one serializer, one importer and one id-remapping
# implementation. This module keeps only tenant seeding and summary counts.


def seed_demo_data_for_tenant(db: Session, tenant_id: UUID) -> None:
    fixture_path = Path(__file__).parent.parent / "catalog" / "demo_catalog.json"
    if not fixture_path.exists():
        return
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    for system_data in fixtures:
        system = CatalogSystem(
            tenant_id=tenant_id,
            name=system_data["name"],
            kind=system_data["kind"],
            description=system_data.get("description"),
            binding_state="unbound",
            extra_metadata={},
        )
        db.add(system)
        db.flush()

        for obj_idx, object_data in enumerate(system_data.get("objects", [])):
            obj = CatalogObject(
                tenant_id=tenant_id,
                system_id=system.id,
                name=object_data["name"],
                label=object_data.get("label", object_data["name"]),
                origin="demo",
                position=obj_idx + 1,
                extra_metadata={},
            )
            db.add(obj)
            db.flush()

            for f_idx, field_data in enumerate(object_data.get("fields", [])):
                db.add(
                    CatalogField(
                        tenant_id=tenant_id,
                        object_id=obj.id,
                        name=field_data["name"],
                        label=field_data.get("label", field_data["name"]),
                        data_type=field_data.get("data_type", "string"),
                        origin="demo",
                        position=f_idx + 1,
                        extra_metadata={},
                    )
                )
    db.flush()


def get_workspace_counts(db: Session, tenant_id: UUID) -> tuple[int, int, int]:
    systems_count = db.scalar(
        select(func.count(CatalogSystem.id)).where(
            CatalogSystem.tenant_id == tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    ) or 0
    contracts_count = db.scalar(
        select(func.count(Integration.id)).where(
            Integration.tenant_id == tenant_id,
            Integration.deleted_at.is_(None),
        )
    ) or 0
    scenarios_count = db.scalar(
        select(func.count(Scenario.id)).where(
            Scenario.tenant_id == tenant_id,
            Scenario.deleted_at.is_(None),
        )
    ) or 0
    return systems_count, contracts_count, scenarios_count
