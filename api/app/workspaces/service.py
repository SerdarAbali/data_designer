import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.service import next_position
from app.models import (
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    Scenario,
    Tenant,
)


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


def _remap_uuids_in_json(obj: dict | list, mapping: dict[str, str]) -> dict | list:
    dumped = json.dumps(obj)
    for old_id, new_id in mapping.items():
        dumped = dumped.replace(old_id, new_id)
    return json.loads(dumped)


def fork_workspace(
    db: Session,
    source_tenant_id: UUID,
    new_tenant: Tenant,
) -> None:
    now = datetime.now(UTC)
    system_map: dict[UUID, UUID] = {}
    object_map: dict[UUID, UUID] = {}
    field_map: dict[UUID, UUID] = {}
    uuid_str_map: dict[str, str] = {}

    # 1. Clone Systems
    source_systems = list(
        db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == source_tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    )
    for s in source_systems:
        new_id = uuid4()
        system_map[s.id] = new_id
        uuid_str_map[str(s.id)] = str(new_id)
        db.add(
            CatalogSystem(
                id=new_id,
                tenant_id=new_tenant.id,
                name=s.name,
                description=s.description,
                kind=s.kind,
                icon=s.icon,
                color=s.color,
                position=deepcopy(s.position),
                binding_state=s.binding_state,
                extra_metadata=deepcopy(s.extra_metadata),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    # 2. Clone Objects
    source_objects = list(
        db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == source_tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    )
    for o in source_objects:
        if o.system_id not in system_map:
            continue
        new_id = uuid4()
        object_map[o.id] = new_id
        uuid_str_map[str(o.id)] = str(new_id)
        db.add(
            CatalogObject(
                id=new_id,
                tenant_id=new_tenant.id,
                system_id=system_map[o.system_id],
                name=o.name,
                label=o.label,
                description=o.description,
                external_identifier=o.external_identifier,
                origin=o.origin,
                position=o.position,
                extra_metadata=deepcopy(o.extra_metadata),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    # 3. Clone Fields
    source_fields = list(
        db.scalars(
            select(CatalogField).where(
                CatalogField.tenant_id == source_tenant_id,
                CatalogField.deleted_at.is_(None),
            )
        )
    )
    for f in source_fields:
        if f.object_id not in object_map:
            continue
        new_id = uuid4()
        field_map[f.id] = new_id
        uuid_str_map[str(f.id)] = str(new_id)
        db.add(
            CatalogField(
                id=new_id,
                tenant_id=new_tenant.id,
                object_id=object_map[f.object_id],
                name=f.name,
                label=f.label,
                description=f.description,
                data_type=f.data_type,
                required=f.required,
                nullable=f.nullable,
                default_value=f.default_value,
                external_identifier=f.external_identifier,
                origin=f.origin,
                position=f.position,
                extra_metadata=deepcopy(f.extra_metadata),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    # 4. Clone Integrations
    integration_map: dict[UUID, UUID] = {}
    source_integrations = list(
        db.scalars(
            select(Integration).where(
                Integration.tenant_id == source_tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
    )
    for i in source_integrations:
        if i.source_system_id not in system_map or i.target_system_id not in system_map:
            continue
        if i.source_object_id not in object_map or i.target_object_id not in object_map:
            continue
        new_id = uuid4()
        integration_map[i.id] = new_id
        uuid_str_map[str(i.id)] = str(new_id)

        remapped_graph = _remap_uuids_in_json(i.graph, uuid_str_map)
        remapped_resp_graph = _remap_uuids_in_json(i.response_graph, uuid_str_map)
        remapped_err_graph = _remap_uuids_in_json(i.error_response_graph, uuid_str_map)
        remapped_sample = _remap_uuids_in_json(i.sample_source_records, uuid_str_map)

        err_obj_id = object_map.get(i.error_response_object_id) if i.error_response_object_id else None

        db.add(
            Integration(
                id=new_id,
                tenant_id=new_tenant.id,
                name=i.name,
                description=i.description,
                interaction_type=i.interaction_type,
                source_system_id=system_map[i.source_system_id],
                source_object_id=object_map[i.source_object_id],
                target_system_id=system_map[i.target_system_id],
                target_object_id=object_map[i.target_object_id],
                error_response_object_id=err_obj_id,
                graph=remapped_graph,
                response_graph=remapped_resp_graph,
                error_response_graph=remapped_err_graph,
                sample_source_records=remapped_sample,
                trigger_config=deepcopy(i.trigger_config),
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    # 5. Clone Scenarios
    source_scenarios = list(
        db.scalars(
            select(Scenario).where(
                Scenario.tenant_id == source_tenant_id,
                Scenario.deleted_at.is_(None),
            )
        )
    )
    for sc in source_scenarios:
        new_id = uuid4()
        new_scope_id = integration_map.get(sc.scope_integration_id) if sc.scope_integration_id else None
        remapped_doc = _remap_uuids_in_json(sc.document, uuid_str_map)

        db.add(
            Scenario(
                id=new_id,
                tenant_id=new_tenant.id,
                scope_integration_id=new_scope_id,
                name=sc.name,
                category=sc.category,
                description=sc.description,
                document=remapped_doc,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def export_workspace_bundle(db: Session, tenant_id: UUID) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Workspace not found")

    systems = list(
        db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    )
    objects = list(
        db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    )
    fields = list(
        db.scalars(
            select(CatalogField).where(
                CatalogField.tenant_id == tenant_id,
                CatalogField.deleted_at.is_(None),
            )
        )
    )
    integrations = list(
        db.scalars(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
    )
    scenarios = list(
        db.scalars(
            select(Scenario).where(
                Scenario.tenant_id == tenant_id,
                Scenario.deleted_at.is_(None),
            )
        )
    )

    return {
        "format": "data-designer-workspace",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "workspace": {
            "name": tenant.name,
            "description": tenant.description,
        },
        "systems": [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "kind": s.kind,
                "icon": s.icon,
                "color": s.color,
                "position": s.position,
                "binding_state": s.binding_state,
                "metadata": s.extra_metadata,
            }
            for s in systems
        ],
        "objects": [
            {
                "id": str(o.id),
                "system_id": str(o.system_id),
                "name": o.name,
                "label": o.label,
                "description": o.description,
                "external_identifier": o.external_identifier,
                "origin": o.origin,
                "position": o.position,
                "metadata": o.extra_metadata,
            }
            for o in objects
        ],
        "fields": [
            {
                "id": str(f.id),
                "object_id": str(f.object_id),
                "name": f.name,
                "label": f.label,
                "description": f.description,
                "data_type": f.data_type,
                "required": f.required,
                "nullable": f.nullable,
                "default_value": f.default_value,
                "external_identifier": f.external_identifier,
                "origin": f.origin,
                "position": f.position,
                "metadata": f.extra_metadata,
            }
            for f in fields
        ],
        "integrations": [
            {
                "id": str(i.id),
                "name": i.name,
                "description": i.description,
                "interaction_type": i.interaction_type,
                "source_system_id": str(i.source_system_id),
                "source_object_id": str(i.source_object_id),
                "target_system_id": str(i.target_system_id),
                "target_object_id": str(i.target_object_id),
                "error_response_object_id": str(i.error_response_object_id)
                if i.error_response_object_id
                else None,
                "graph": i.graph,
                "response_graph": i.response_graph,
                "error_response_graph": i.error_response_graph,
                "sample_source_records": i.sample_source_records,
                "trigger_config": i.trigger_config,
            }
            for i in integrations
        ],
        "scenarios": [
            {
                "id": str(sc.id),
                "scope_integration_id": str(sc.scope_integration_id)
                if sc.scope_integration_id
                else None,
                "name": sc.name,
                "category": sc.category,
                "description": sc.description,
                "document": sc.document,
            }
            for sc in scenarios
        ],
    }


def import_workspace_bundle(db: Session, new_tenant: Tenant, bundle: dict) -> None:
    now = datetime.now(UTC)
    system_map: dict[str, UUID] = {}
    object_map: dict[str, UUID] = {}
    field_map: dict[str, UUID] = {}
    uuid_str_map: dict[str, str] = {}

    for s_data in bundle.get("systems", []):
        old_id = s_data["id"]
        new_id = uuid4()
        system_map[old_id] = new_id
        uuid_str_map[old_id] = str(new_id)
        db.add(
            CatalogSystem(
                id=new_id,
                tenant_id=new_tenant.id,
                name=s_data["name"],
                description=s_data.get("description"),
                kind=s_data.get("kind", "application"),
                icon=s_data.get("icon"),
                color=s_data.get("color"),
                position=s_data.get("position"),
                binding_state=s_data.get("binding_state", "unbound"),
                extra_metadata=s_data.get("metadata", {}),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    for o_data in bundle.get("objects", []):
        old_id = o_data["id"]
        new_id = uuid4()
        object_map[old_id] = new_id
        uuid_str_map[old_id] = str(new_id)
        sys_id = system_map.get(o_data["system_id"])
        if not sys_id:
            continue
        db.add(
            CatalogObject(
                id=new_id,
                tenant_id=new_tenant.id,
                system_id=sys_id,
                name=o_data["name"],
                label=o_data.get("label", o_data["name"]),
                description=o_data.get("description"),
                external_identifier=o_data.get("external_identifier"),
                origin=o_data.get("origin", "import"),
                position=o_data.get("position", 1),
                extra_metadata=o_data.get("metadata", {}),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    for f_data in bundle.get("fields", []):
        old_id = f_data["id"]
        new_id = uuid4()
        field_map[old_id] = new_id
        uuid_str_map[old_id] = str(new_id)
        obj_id = object_map.get(f_data["object_id"])
        if not obj_id:
            continue
        db.add(
            CatalogField(
                id=new_id,
                tenant_id=new_tenant.id,
                object_id=obj_id,
                name=f_data["name"],
                label=f_data.get("label", f_data["name"]),
                description=f_data.get("description"),
                data_type=f_data.get("data_type", "string"),
                required=f_data.get("required", False),
                nullable=f_data.get("nullable", True),
                default_value=f_data.get("default_value"),
                external_identifier=f_data.get("external_identifier"),
                origin=f_data.get("origin", "import"),
                position=f_data.get("position", 1),
                extra_metadata=f_data.get("metadata", {}),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    integration_map: dict[str, UUID] = {}
    for i_data in bundle.get("integrations", []):
        old_id = i_data["id"]
        src_sys = system_map.get(i_data["source_system_id"])
        tgt_sys = system_map.get(i_data["target_system_id"])
        src_obj = object_map.get(i_data["source_object_id"])
        tgt_obj = object_map.get(i_data["target_object_id"])
        if not (src_sys and tgt_sys and src_obj and tgt_obj):
            continue
        new_id = uuid4()
        integration_map[old_id] = new_id
        uuid_str_map[old_id] = str(new_id)

        err_obj = object_map.get(i_data["error_response_object_id"]) if i_data.get("error_response_object_id") else None

        remapped_graph = _remap_uuids_in_json(i_data.get("graph", {"version": 1, "nodes": [], "edges": []}), uuid_str_map)
        remapped_resp_graph = _remap_uuids_in_json(i_data.get("response_graph", {"version": 1, "nodes": [], "edges": []}), uuid_str_map)
        remapped_err_graph = _remap_uuids_in_json(i_data.get("error_response_graph", {"version": 1, "nodes": [], "edges": []}), uuid_str_map)
        remapped_sample = _remap_uuids_in_json(i_data.get("sample_source_records", []), uuid_str_map)

        db.add(
            Integration(
                id=new_id,
                tenant_id=new_tenant.id,
                name=i_data["name"],
                description=i_data.get("description"),
                interaction_type=i_data.get("interaction_type", "ONE_WAY"),
                source_system_id=src_sys,
                source_object_id=src_obj,
                target_system_id=tgt_sys,
                target_object_id=tgt_obj,
                error_response_object_id=err_obj,
                graph=remapped_graph,
                response_graph=remapped_resp_graph,
                error_response_graph=remapped_err_graph,
                sample_source_records=remapped_sample,
                trigger_config=deepcopy(i_data.get("trigger_config", {})),
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

    for sc_data in bundle.get("scenarios", []):
        new_id = uuid4()
        new_scope = integration_map.get(sc_data["scope_integration_id"]) if sc_data.get("scope_integration_id") else None
        remapped_doc = _remap_uuids_in_json(sc_data.get("document", {}), uuid_str_map)
        db.add(
            Scenario(
                id=new_id,
                tenant_id=new_tenant.id,
                scope_integration_id=new_scope,
                name=sc_data["name"],
                category=sc_data.get("category", "happy_path"),
                description=sc_data.get("description"),
                document=remapped_doc,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()

