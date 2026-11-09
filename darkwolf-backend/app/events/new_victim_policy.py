from datetime import datetime, timedelta, timezone


SOURCE_DATE_GATED_DISCOVERIES = frozenset({"gunra", "lapsus", "leakeddata"})
NEW_VICTIM_WINDOW = timedelta(hours=48)


def has_recent_source_date(value, now: datetime | None = None) -> bool:
    """Return true only when the leak-site date is within the past 48 hours."""
    if not isinstance(value, datetime):
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    source_date = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    age = current - source_date
    return timedelta(0) <= age <= NEW_VICTIM_WINDOW
