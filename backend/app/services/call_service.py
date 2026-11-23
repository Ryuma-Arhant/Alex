import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.correlation import new_correlation_id
from app.core.errors import NotFound, UpstreamError
from app.core.state_machine import CALL, CallState
from app.db.models import AgentProfileVersion, Call, CallLink, CallTurn
from app.services import audit_service, livekit_service, profile_service

log = logging.getLogger("calls")

# Why a phone call ended without a conversation, as reported by the agent ("dial_failed" event).
DIAL_FAILURES = {"busy", "no_answer", "declined", "invalid_number", "dial_failed"}


async def create_web_call(
    s: AsyncSession,
    settings: Settings,
    workspace_id: uuid.UUID,
    profile_id: uuid.UUID | None,
    *,
    version: AgentProfileVersion | None = None,
    link: CallLink | None = None,
) -> tuple[Call, str]:
    """`version`/`link` let agent calls pin a specific profile version and record ownership."""
    if profile_id is not None:
        raise NotFound("Selecting a non-active profile is not supported yet")
    if version is None:
        _, version = await profile_service.get_active(s, workspace_id)  # snapshot current version
    call = Call(
        workspace_id=workspace_id,
        direction="WEB",
        state=CallState.CREATED,
        room_name=livekit_service.new_room_name(),
        correlation_id=new_correlation_id(),
        profile_version_id=version.id,
        started_at=datetime.now(UTC),
    )
    s.add(call)
    await s.flush()
    if link is not None:
        link.call_id = call.id
        s.add(link)
    token = livekit_service.mint_participant_token(
        settings,
        room=call.room_name,
        identity=f"web-{call.id.hex[:12]}",
        call_id=call.id,
        correlation_id=call.correlation_id,
    )
    await audit_service.record(
        s,
        "call.created",
        actor="user",
        workspace_id=workspace_id,
        call_id=call.id,
        correlation_id=call.correlation_id,
        payload={"profile_version": version.version, "room": call.room_name},
    )
    await s.commit()
    return call, token


async def create_phone_call(
    s: AsyncSession,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    version: AgentProfileVersion,
    link: CallLink,
    dial_to: str,
) -> tuple[Call, str]:
    """A real phone call: the agent is sent into a new room and dials `dial_to` (E.164) through the SIP trunk. Returns
    the call and a listen-only token so the user's browser can follow it (a bulk call simply never uses it)."""
    call = Call(
        workspace_id=workspace_id,
        direction="OUTBOUND",
        state=CallState.CREATED,
        room_name=livekit_service.new_room_name(),
        correlation_id=new_correlation_id(),
        profile_version_id=version.id,
        started_at=datetime.now(UTC),
        dial_to=dial_to,
    )
    s.add(call)
    await s.flush()
    link.call_id = call.id
    s.add(link)
    await audit_service.record(
        s,
        "call.created",
        actor="user",
        workspace_id=workspace_id,
        call_id=call.id,
        correlation_id=call.correlation_id,
        payload={"profile_version": version.version, "room": call.room_name, "direction": "OUTBOUND"},
    )
    await s.commit()  # the agent reads the call (and the number) as soon as it is dispatched
    try:
        await livekit_service.dispatch_agent(
            settings, room=call.room_name, call_id=call.id, correlation_id=call.correlation_id
        )
    except Exception:
        log.exception("agent dispatch failed", extra={"call_id": str(call.id)})
        call.state = CALL.check(CallState(call.state), CallState.FAILED)
        call.ended_at, call.end_reason, call.dial_to = datetime.now(UTC), "dial_failed", None
        await s.commit()  # the sweeper writes its "no conversation" summary
        raise UpstreamError("Could not start the phone call. Please try again.") from None
    token = livekit_service.mint_listener_token(settings, room=call.room_name, identity=f"listen-{call.id.hex[:12]}")
    return call, token


async def get_scoped_call(s: AsyncSession, workspace_id: uuid.UUID, call_id: uuid.UUID) -> Call:
    call = await s.get(Call, call_id)
    if call is None or call.workspace_id != workspace_id:
        raise NotFound("Call not found")
    return call


async def get_call_any(s: AsyncSession, call_id: uuid.UUID) -> Call:
    call = await s.get(Call, call_id)
    if call is None:
        raise NotFound("Call not found")
    return call


async def list_turns(s: AsyncSession, call_id: uuid.UUID) -> list[CallTurn]:
    return list((await s.scalars(select(CallTurn).where(CallTurn.call_id == call_id).order_by(CallTurn.seq))).all())


async def upsert_turns(s: AsyncSession, call: Call, turns: list[dict[str, Any]]) -> int:
    """Idempotent by (call_id, seq): duplicate / retried / out-of-order posts converge."""
    for t in turns:
        existing = await s.scalar(select(CallTurn).where(CallTurn.call_id == call.id, CallTurn.seq == t["seq"]))
        if existing is None:
            s.add(CallTurn(call_id=call.id, **t))
        else:
            for k, v in t.items():
                setattr(existing, k, v)
    await s.commit()
    return len(turns)


async def apply_event(s: AsyncSession, call: Call, event_type: str, payload: dict[str, Any]) -> None:
    if event_type == "agent_joined" and call.state == CallState.CREATED:
        call.state = CALL.check(CallState(call.state), CallState.ACTIVE)
    elif event_type == "answered":  # phone calls: the length is counted from the moment the borrower picks up
        call.started_at = datetime.now(UTC)
    elif event_type == "dial_failed":
        reason = str(payload.get("reason", "dial_failed"))
        call.ended_at = call.ended_at or datetime.now(UTC)
        call.end_reason = reason if reason in DIAL_FAILURES else "dial_failed"
        call.dial_to = None
    elif event_type == "session_closed":
        call.ended_at = call.ended_at or datetime.now(UTC)
        call.end_reason = call.end_reason or str(payload.get("reason", "closed"))[:60]
        call.dial_to = None  # the number is no longer needed once the call is over
    await audit_service.record(
        s,
        f"call.{event_type}",
        actor="agent",
        workspace_id=call.workspace_id,
        call_id=call.id,
        correlation_id=call.correlation_id,
        payload=payload,
    )
    await s.commit()


async def runtime_context(s: AsyncSession, call: Call, settings: Settings | None = None) -> dict[str, Any]:
    from app.services.profile_builder import build_generic_profile

    v = await s.get(AgentProfileVersion, call.profile_version_id)
    assert v is not None
    ctx: dict[str, Any] = {
        "call_id": str(call.id),
        "correlation_id": call.correlation_id,
        "direction": call.direction,
        "profile_version": v.version,
        "profile": build_generic_profile(v),
        "runtime": {"now_utc": datetime.now(UTC).isoformat(), "timezone": "UTC"},
    }
    if call.direction == "OUTBOUND" and call.dial_to and settings is not None and settings.phone_calls_enabled:
        # what the agent dials; only on this token-protected internal endpoint, never on the public API
        ctx["dial"] = {
            "to": call.dial_to,
            "trunk_id": settings.sip_outbound_trunk_id.strip(),
            "ringing_timeout_s": settings.sip_ringing_timeout_seconds,
        }
    return ctx
