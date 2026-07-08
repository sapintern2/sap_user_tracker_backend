from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.deleted_user import DeletedUser


router = APIRouter(prefix="/deleted-users", tags=["Deleted Users"])


@router.get("")
def get_deleted_users(
    deleted_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, str | None]] | str | None]:
    statement = select(DeletedUser).order_by(DeletedUser.deleted_date.desc(), DeletedUser.username)

    if deleted_date:
        start_at = datetime.combine(deleted_date, time.min)
        end_at = datetime.combine(deleted_date, time.max)
        statement = statement.where(
            DeletedUser.deleted_date >= start_at,
            DeletedUser.deleted_date <= end_at,
        )

    users = db.scalars(statement).all()

    return {
        "deleted_date": deleted_date.isoformat() if deleted_date else None,
        "users": [
            {
                "username": user.username,
                "category": user.category,
                "deleted_date": user.deleted_date.date().isoformat(),
                "last_seen_date": user.last_seen_date.date().isoformat(),
            }
            for user in users
        ],
    }
