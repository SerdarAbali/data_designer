import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.auth.security import hash_password
from app.catalog.service import next_position
from app.db import SessionLocal
from app.models import CatalogField, CatalogObject, CatalogSystem, Tenant, User


def create_initial_user(email: str, tenant_name: str) -> None:
    normalized_email = email.strip().casefold()
    if "@" not in normalized_email:
        raise ValueError("A valid email address is required")

    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    if not password:
        raise ValueError("Password must not be empty")

    with SessionLocal.begin() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise ValueError("An initial user already exists")
        tenant = Tenant(name=tenant_name)
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email=normalized_email,
                password_hash=hash_password(password),
            )
        )
    print(f"Created the initial internal user {normalized_email}.")


def load_demo_catalog() -> None:
    fixture_path = Path(__file__).parent / "catalog" / "demo_catalog.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    with SessionLocal.begin() as db:
        tenants = list(db.scalars(select(Tenant).order_by(Tenant.created_at).limit(2)))
        if len(tenants) != 1:
            raise ValueError("Create the single internal user before loading demo catalog data")
        tenant_id = tenants[0].id

        for system_data in fixtures:
            system = db.scalar(
                select(CatalogSystem).where(
                    CatalogSystem.tenant_id == tenant_id,
                    CatalogSystem.name == system_data["name"],
                    CatalogSystem.deleted_at.is_(None),
                )
            )
            if system is None:
                system = CatalogSystem(
                    tenant_id=tenant_id,
                    name=system_data["name"],
                    kind=system_data["kind"],
                    description=system_data["description"],
                    binding_state="unbound",
                    extra_metadata={},
                )
                db.add(system)
                db.flush()

            for object_data in system_data["objects"]:
                obj = db.scalar(
                    select(CatalogObject).where(
                        CatalogObject.tenant_id == tenant_id,
                        CatalogObject.system_id == system.id,
                        CatalogObject.name == object_data["name"],
                        CatalogObject.deleted_at.is_(None),
                    )
                )
                if obj is None:
                    obj = CatalogObject(
                        tenant_id=tenant_id,
                        system_id=system.id,
                        name=object_data["name"],
                        label=object_data["label"],
                        origin="demo",
                        position=next_position(
                            db, CatalogObject, CatalogObject.system_id, system.id
                        ),
                        extra_metadata={},
                    )
                    db.add(obj)
                    db.flush()

                for field_data in object_data["fields"]:
                    existing = db.scalar(
                        select(CatalogField.id).where(
                            CatalogField.tenant_id == tenant_id,
                            CatalogField.object_id == obj.id,
                            CatalogField.name == field_data["name"],
                            CatalogField.deleted_at.is_(None),
                        )
                    )
                    if existing is None:
                        db.add(
                            CatalogField(
                                tenant_id=tenant_id,
                                object_id=obj.id,
                                name=field_data["name"],
                                label=field_data["label"],
                                data_type=field_data["data_type"],
                                origin="demo",
                                position=next_position(
                                    db, CatalogField, CatalogField.object_id, obj.id
                                ),
                                extra_metadata={},
                            )
                        )
                        db.flush()
    print(f"Loaded {len(fixtures)} generic demo systems (existing catalog data was preserved).")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_user = subparsers.add_parser("create-initial-user")
    create_user.add_argument("--email", required=True)
    create_user.add_argument("--tenant-name", default="Internal")
    subparsers.add_parser("load-demo-catalog")
    args = parser.parse_args()

    try:
        if args.command == "create-initial-user":
            create_initial_user(args.email, args.tenant_name)
        elif args.command == "load-demo-catalog":
            load_demo_catalog()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
