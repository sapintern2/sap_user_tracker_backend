from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.daily_user import DailyUser
from app.models.deleted_user import DeletedUser
from app.models.upload import Upload


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def category_key(category: str | None) -> str:
    value = (category or "").lower()
    if "advanced" in value:
        return "advanced_users"
    if "core" in value:
        return "core_users"
    if "self-service" in value or "self service" in value:
        return "self_service_users"
    return "other_users"


@router.get("/users")
def get_latest_users(
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    latest_upload = db.scalar(
        select(Upload).order_by(Upload.upload_date.desc(), Upload.id.desc()).limit(1)
    )

    if not latest_upload:
        return {"upload_date": None, "category": category, "users": []}

    users = db.scalars(
        select(DailyUser)
        .where(DailyUser.upload_id == latest_upload.id)
        .order_by(DailyUser.username)
    ).all()

    if category:
        users = [user for user in users if category_key(user.category) == category]

    return {
        "upload_date": latest_upload.upload_date.date().isoformat(),
        "category": category,
        "users": [
            {
                "username": user.username,
                "category": user.category,
            }
            for user in users
        ],
    }


@router.get("")
def get_dashboard(
    deleted_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    latest_upload = db.scalar(
        select(Upload).order_by(Upload.upload_date.desc(), Upload.id.desc()).limit(1)
    )

    category_counts = {
        "advanced_users": 0,
        "core_users": 0,
        "self_service_users": 0,
        "other_users": 0,
    }

    if latest_upload:
        latest_users = db.scalars(
            select(DailyUser).where(DailyUser.upload_id == latest_upload.id)
        ).all()
        for user in latest_users:
            category_counts[category_key(user.category)] += 1

    total_uploads = db.scalar(select(func.count(Upload.id))) or 0

    today = datetime.utcnow().date()
    selected_date = deleted_date or today
    start_at = datetime.combine(selected_date, time.min)
    end_at = datetime.combine(selected_date, time.max)

    selected_deleted_users = db.scalars(
        select(DeletedUser)
        .where(DeletedUser.deleted_date >= start_at, DeletedUser.deleted_date <= end_at)
        .order_by(DeletedUser.username)
    ).all()

    trend_rows = db.execute(
        select(
            func.date(DeletedUser.deleted_date).label("deleted_day"),
            func.count(DeletedUser.id).label("deleted_count"),
        )
        .group_by(func.date(DeletedUser.deleted_date))
        .order_by(func.date(DeletedUser.deleted_date))
    ).all()

    return {
        "latest_upload": {
            "id": latest_upload.id,
            "upload_date": latest_upload.upload_date.date().isoformat(),
            "total_users": latest_upload.total_users,
        }
        if latest_upload
        else None,
        "summary": {
            "total_users": latest_upload.total_users if latest_upload else 0,
            **category_counts,
            "deleted_users_for_selected_date": len(selected_deleted_users),
            "total_uploads": total_uploads,
        },
        "selected_deleted_date": selected_date.isoformat(),
        "deleted_users": [
            {
                "username": user.username,
                "category": user.category,
                "deleted_date": user.deleted_date.date().isoformat(),
                "last_seen_date": user.last_seen_date.date().isoformat(),
            }
            for user in selected_deleted_users
        ],
        "deleted_user_trend": [
            {
                "date": row.deleted_day.isoformat(),
                "count": row.deleted_count,
            }
            for row in trend_rows
        ],
    }
