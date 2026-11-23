from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_user_for_uid
from app.core.config import Settings, get_settings
from app.core.ratelimit import limiter
from app.db.models import User
from app.db.session import get_session
from app.schemas.call import CreateCallResponse
from app.schemas.collections import SoloCallIn
from app.services import collections_service

router = APIRouter(prefix="/users/{uid}/collections", tags=["collections"])


@router.post("/calls", response_model=CreateCallResponse)
@limiter.limit(lambda: get_settings().rate_limit_public)
async def start_solo_call(
    request: Request,
    body: SoloCallIn,
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CreateCallResponse:
    """Individual call: the borrower's details in, a ready-to-join call out (phone mode: one to follow)."""
    call, token = await collections_service.start_solo_call(session, settings, user, body)
    return CreateCallResponse(call_id=str(call.id), livekit_url=settings.livekit_url, token=token, mode=body.mode)
