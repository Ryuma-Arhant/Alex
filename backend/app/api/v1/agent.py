from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_user_for_uid
from app.db.models import Agent, User
from app.db.session import get_session
from app.schemas.account import AgentCreateIn, AgentNameIn, AgentOut
from app.services import agent_service

router = APIRouter(prefix="/users/{uid}/agent", tags=["agent"])


async def _out(s: AsyncSession, a: Agent) -> AgentOut:
    return AgentOut(
        aid=str(a.aid),
        name=a.name,
        role=a.role_behavior,
        voice=a.voice,  # only male | female are ever stored
        status="busy" if await agent_service.is_busy(s, a) else "free",
        system_prompt=await agent_service.system_prompt(s, a),
        created_at=a.created_at,
    )


@router.get("", response_model=AgentOut | None)
async def get_agent(
    user: User = Depends(get_user_for_uid), session: AsyncSession = Depends(get_session)
) -> AgentOut | None:
    """The user's agent, or null when they have none yet."""
    a = await agent_service.get_active(session, user.uid)
    return await _out(session, a) if a else None


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreateIn, user: User = Depends(get_user_for_uid), session: AsyncSession = Depends(get_session)
) -> AgentOut:
    """A user has at most one agent: 409 when one already exists."""
    return await _out(session, await agent_service.create(session, user, body.name, body.voice))


@router.put("", response_model=AgentOut)
async def rename_agent(
    body: AgentNameIn, user: User = Depends(get_user_for_uid), session: AsyncSession = Depends(get_session)
) -> AgentOut:
    return await _out(session, await agent_service.rename(session, user, body.name))


@router.delete("", status_code=204)
async def delete_agent(
    user: User = Depends(get_user_for_uid), session: AsyncSession = Depends(get_session)
) -> Response:
    await agent_service.delete(session, user)
    return Response(status_code=204)
