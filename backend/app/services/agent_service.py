"""The user's single Loan-Recovery Agent: create, read, rename, delete."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.db.models import Agent, Call, CallLink, User
from app.services import audit_service, profile_service
from app.services.collections_prompt import build_recovery_prompt, opening_line

ROLE = "Loan-Recovery Agent"
BUSY_WINDOW = timedelta(minutes=30)  # an unended call older than this is treated as a lost worker


def agent_prompt(name: str) -> str:
    """Every agent gets the same Loan-Recovery prompt; only its name differs."""
    return build_recovery_prompt(name)


def agent_fields(name: str) -> dict[str, object]:
    return {
        "agent_name": name,
        "role_summary": ROLE,
        "conversation_flow": {"opening": opening_line(name, None)},
        "escalation_rules": "Offer a callback from the lender's team for anything you cannot answer.",
        "call_ending_conditions": [
            "A payment commitment or other clear outcome has been recorded and repeated back",
            "The person asks to stop the call or not to be contacted",
            "Wrong number or wrong person",
        ],
        "assumptions_made": [],
    }


async def get_active(s: AsyncSession, uid: uuid.UUID) -> Agent | None:
    return await s.scalar(select(Agent).where(Agent.uid == uid, Agent.lifecycle == "ACTIVE"))


async def require_active(s: AsyncSession, uid: uuid.UUID) -> Agent:
    a = await get_active(s, uid)
    if a is None:
        raise NotFound("You have no agent yet")
    return a


async def is_busy(s: AsyncSession, agent: Agent) -> bool:
    """On a call: a linked call that has not ended and is recent enough not to be a lost worker."""
    cutoff = datetime.now(UTC) - BUSY_WINDOW
    found = await s.scalar(
        select(CallLink.call_id)
        .join(Call, Call.id == CallLink.call_id)
        .where(CallLink.agent_aid == agent.aid, Call.ended_at.is_(None), Call.created_at > cutoff)
        .limit(1)
    )
    return found is not None


async def system_prompt(s: AsyncSession, agent: Agent) -> str:
    if agent.profile_id is None:
        return agent_prompt(agent.name)
    return (await profile_service.current_version(s, agent.profile_id)).context_prompt


async def create(s: AsyncSession, user: User, name: str) -> Agent:
    if await get_active(s, user.uid) is not None:
        raise Conflict("You already have an agent. Delete it before creating a new one.")
    p, _ = await profile_service.create_detached(
        s, user.workspace_id, source=ROLE, fields=agent_fields(name), prompt=agent_prompt(name), model="loan-recovery"
    )
    a = Agent(aid=uuid.uuid4(), uid=user.uid, name=name, role_behavior=ROLE, lifecycle="ACTIVE", profile_id=p.id)
    s.add(a)
    await audit_service.record(
        s, "agent.created", actor="user", workspace_id=user.workspace_id, payload={"aid": str(a.aid)}
    )
    try:
        await s.commit()
    except IntegrityError:  # a concurrent request created one first (unique index on the ACTIVE agent)
        await s.rollback()
        raise Conflict("You already have an agent. Delete it before creating a new one.") from None
    return a


async def rename(s: AsyncSession, user: User, name: str) -> Agent:
    a = await require_active(s, user.uid)
    if name == a.name:
        return a
    a.name = name
    if a.profile_id is not None:  # new immutable version (the prompt carries the name); past calls keep theirs
        await profile_service.append_version(
            s, a.profile_id, source=ROLE, fields=agent_fields(name), prompt=agent_prompt(name), model="loan-recovery"
        )
    await audit_service.record(
        s, "agent.renamed", actor="user", workspace_id=user.workspace_id, payload={"aid": str(a.aid)}
    )
    await s.commit()
    return a


async def delete(s: AsyncSession, user: User) -> None:
    """Soft delete: the row stays (as DELETED) so the agent's past calls keep their link."""
    a = await require_active(s, user.uid)
    if await is_busy(s, a):
        raise Conflict("The agent is on a call. Try again when the call has ended.")
    a.lifecycle = "DELETED"
    await audit_service.record(
        s, "agent.deleted", actor="user", workspace_id=user.workspace_id, payload={"aid": str(a.aid)}
    )
    await s.commit()
