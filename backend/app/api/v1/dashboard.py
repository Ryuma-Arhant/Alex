import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_user_for_uid
from app.db.models import User
from app.db.session import get_session
from app.services import agent_service, dashboard_service, stats_service

router = APIRouter(prefix="/users/{uid}/dashboard", tags=["dashboard"])


class NextActionDoneIn(BaseModel):
    done: bool


@router.get("")
async def dashboard(
    tz: str | None = None,
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Today's figures, the agent's recent calls and today's next actions, in the client's timezone."""
    zone = stats_service.resolve_tz(tz)
    agent = await agent_service.get_active(session, user.uid)
    return await dashboard_service.overview(session, user.uid, agent, zone)


@router.put("/next-actions/{call_id}/{index}")
async def set_next_action_done(
    call_id: uuid.UUID,
    index: int,
    body: NextActionDoneIn,
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    return {"done": await dashboard_service.set_action_done(session, user.uid, call_id, index, body.done)}
