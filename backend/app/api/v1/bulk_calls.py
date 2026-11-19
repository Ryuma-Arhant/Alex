from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.auth_deps import get_user_for_uid
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.db.models import User
from app.services import bulk_service
from app.services.bulk_service import BadCsv

router = APIRouter(prefix="/users/{uid}/bulk-calls", tags=["bulk-calls"])


@router.post("/preview")
@limiter.limit(lambda: get_settings().rate_limit_public)
async def preview(request: Request, user: User = Depends(get_user_for_uid)) -> dict[str, Any]:
    """Raw CSV bytes in the body (up to 1 MB). Returns every row, validated; nothing is stored or called."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > bulk_service.MAX_BYTES:
        raise BadCsv("The file is larger than 1 MB.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > bulk_service.MAX_BYTES:
            raise BadCsv("The file is larger than 1 MB.")
    return bulk_service.parse_csv(bytes(data))
