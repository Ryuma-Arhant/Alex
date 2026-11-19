import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Agent, Call, CallLink

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAYS = 7


class BadTimezone(AppError):
    status_code, code = 422, "bad_timezone"


def resolve_tz(name: str | None) -> ZoneInfo:
    """The client's IANA timezone (users have no stored timezone); UTC when absent."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise BadTimezone("Unknown timezone") from None


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)  # SQLite hands back naive UTC


def last_days(tz: ZoneInfo, now: datetime | None = None) -> list[date]:
    """The last seven local dates, oldest first, ending today."""
    today = (now or datetime.now(UTC)).astimezone(tz).date()
    return [today - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]


async def calls_per_day(
    s: AsyncSession, uid: uuid.UUID, agent: Agent | None, tz: ZoneInfo, now: datetime | None = None
) -> dict[str, object]:
    """Calls made by the user's agent on each of the last seven days (zero-filled; no agent -> all zeros)."""
    days = last_days(tz, now)
    counts = dict.fromkeys(days, 0)
    if agent is not None:
        since = datetime.combine(days[0], time.min, tzinfo=tz).astimezone(UTC)
        rows = await s.scalars(
            select(Call)
            .join(CallLink, CallLink.call_id == Call.id)
            .where(CallLink.uid == uid, CallLink.agent_aid == agent.aid, Call.created_at >= since - timedelta(days=1))
        )
        for call in rows:
            d = _aware(call.started_at or call.created_at).astimezone(tz).date()
            if d in counts:
                counts[d] += 1
    return {
        "tz": tz.key,
        "today": days[-1].isoformat(),
        "days": [{"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "calls": counts[d]} for d in days],
    }
