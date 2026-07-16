from datetime import datetime, time, timezone, timedelta


SRI_LANKA_TZ = timezone(timedelta(hours=5, minutes=30))


def sri_lanka_now() -> datetime:
    return datetime.now(SRI_LANKA_TZ).replace(tzinfo=None)


def sri_lanka_day_range(value) -> tuple[datetime, datetime]:
    return datetime.combine(value, time.min), datetime.combine(value, time.max)


def sri_lanka_iso(value: datetime | None) -> str | None:
    if not value:
        return None

    return value.replace(tzinfo=SRI_LANKA_TZ).isoformat()
