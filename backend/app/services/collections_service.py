import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Call, CallLink, User
from app.schemas.collections import SoloCallIn
from app.services import call_service, profile_service
from app.services.collections_prompt import BorrowerDetails, build_collections_prompt, opening_line

AGENT_NAME = "Maya"


def profile_fields(agent_name: str, borrower: BorrowerDetails | None) -> dict[str, object]:
    """What the worker reads from the profile: the spoken opening and the call-ending conditions."""
    return {
        "agent_name": agent_name,
        "role_summary": "Loan EMI payment reminder call",
        "conversation_flow": {"opening": opening_line(agent_name, borrower)},
        "escalation_rules": "Offer a callback from the lender's team for anything you cannot answer.",
        "call_ending_conditions": [
            "A payment commitment or outcome has been recorded",
            "The person asks to stop the call or not to be contacted",
            "Wrong number or wrong person",
        ],
        "assumptions_made": [],
    }


async def start_solo_call(s: AsyncSession, settings: Settings, user: User, body: SoloCallIn) -> tuple[Call, str]:
    """One borrower, one call. The details live only in this call's own prompt snapshot (a profile nobody else uses)."""
    borrower = BorrowerDetails(
        name=body.borrower_name,
        phone=body.phone,
        amount=body.amount,
        bank=body.bank,
        currency=body.currency,
        due_date=body.due_date,
    )
    _, version = await profile_service.create_detached(
        s,
        user.workspace_id,
        source="collections",
        fields=profile_fields(AGENT_NAME, borrower),
        prompt=build_collections_prompt(AGENT_NAME, borrower),
        model="collections",
    )
    # Owned by the user, but neither a manager call nor an agent call, so it appears in neither list nor graph.
    return await call_service.create_web_call(
        s, settings, user.workspace_id, None, version=version, link=CallLink(call_id=uuid.uuid4(), uid=user.uid)
    )
