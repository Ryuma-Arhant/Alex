import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_user_for_uid
from app.core.config import Settings, get_settings
from app.core.ratelimit import limiter
from app.db.models import User
from app.db.session import get_session
from app.services import bulk_jobs_service, bulk_service
from app.services.bulk_service import BadCsv

router = APIRouter(prefix="/users/{uid}/bulk-calls", tags=["bulk-calls"])


@router.post("/preview")
@limiter.limit(lambda: get_settings().rate_limit_public)
async def preview(request: Request, user: User = Depends(get_user_for_uid)) -> dict[str, Any]:
    """Raw CSV bytes in the body (up to 1 MB). Returns every row, validated; nothing is stored or called."""
    return bulk_service.parse_csv(await _read_csv(request))


async def _read_csv(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > bulk_service.MAX_BYTES:
        raise BadCsv("The file is larger than 1 MB.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > bulk_service.MAX_BYTES:
            raise BadCsv("The file is larger than 1 MB.")
    return bytes(data)


@router.post("", status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_public)
async def start_bulk_call(
    request: Request,
    file_name: str = "",
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Raw CSV bytes in the body: its valid rows are phoned one at a time by the user's agent."""
    job = await bulk_jobs_service.create_job(session, settings, user, await _read_csv(request), file_name)
    return await bulk_jobs_service.job_out(session, job)


@router.get("/current")
async def current_bulk_call(
    user: User = Depends(get_user_for_uid), session: AsyncSession = Depends(get_session)
) -> dict[str, Any] | None:
    """The latest bulk run with each borrower's status (only the last 4 digits of their number), or null."""
    job = await bulk_jobs_service.current(session, user.uid)
    return await bulk_jobs_service.job_out(session, job) if job else None


@router.post("/{job_id}/{action}")
async def control_bulk_call(
    job_id: uuid.UUID,
    action: Literal["pause", "resume", "cancel"],
    user: User = Depends(get_user_for_uid),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await bulk_jobs_service.set_status(session, user.uid, job_id, action)
    return await bulk_jobs_service.job_out(session, job)
