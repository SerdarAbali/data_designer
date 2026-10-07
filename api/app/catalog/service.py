from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_position(db: Session, model, parent_column, parent_id: UUID) -> int:
    current_max = db.scalar(
        select(func.max(model.position)).where(
            parent_column == parent_id,
            model.deleted_at.is_(None),
        )
    )
    return (current_max if current_max is not None else -1) + 1
