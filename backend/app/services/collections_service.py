import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict
from app.db.models import Call, CallLink, User
from app.schemas.collections import SoloCallIn
from app.services import agent_service, call_service, profile_service
from app.services.collections_prompt import BorrowerDetails, build_recovery_prompt, opening_line


def profile_fields(agent_name: str, borrower: BorrowerDetails | None) -> dict[str, object]:
    """What the worker reads from the profile: the spoken opening and the call-ending conditions."""
    return {
        **agent_service.agent_fields(agent_name),
        "role_summary": "Loan recovery call",
        "conversation_flow": {"opening": opening_line(agent_name, borrower)},
    }


async def start_solo_call(s: AsyncSession, settings: Settings, user: User, body: SoloCallIn) -> tuple[Call, str]:
    """One borrower, one call, made by the user's agent. The borrower's details live only in this call's own prompt
    snapshot (a profile nobody else uses); the call is linked to the agent so it shows as busy and is counted."""
    agent = await agent_service.get_active(s, user.uid)
    if agent is None:
        raise Conflict("Create your agent before placing calls.")
    borrower = BorrowerDetails(
        name=body.borrower_name,
        phone=body.phone,
        amount=body.amount,
        bank=body.bank,
        currency=body.currency,
        due_date=body.due_date,
        notes=body.context,
    )
    _, version = await profile_service.create_detached(
        s,
        user.workspace_id,
        source="loan-recovery-call",
        fields=profile_fields(agent.name, borrower),
        prompt=build_recovery_prompt(agent.name, borrower),
        model="loan-recovery",
    )
    return await call_service.create_web_call(
        s,
        settings,
        user.workspace_id,
        None,
        version=version,
        link=CallLink(call_id=uuid.uuid4(), uid=user.uid, agent_aid=agent.aid),
    )
