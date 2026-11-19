from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_user_for_uid
from app.db.models import User
from app.db.session import get_session
from app.services import agent_service, stats_service

router = APIRouter(prefix="/users/{uid}/stats", tags=["stats"])


@router.get("/calls-per-day")
async def calls_per_day(
    tz: str | None = None,
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Number of calls made by the user's agent on each of the last seven days, in the client's timezone."""
    zone = stats_service.resolve_tz(tz)
    agent = await agent_service.get_active(session, user.uid)
    return await stats_service.calls_per_day(session, user.uid, agent, zone)
