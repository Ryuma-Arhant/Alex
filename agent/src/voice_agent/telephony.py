"""Phone calls: the agent dials the borrower through the LiveKit outbound SIP trunk (Twilio) and waits for an answer,
so it only starts speaking once a person has picked up."""

import logging
from dataclasses import dataclass
from typing import Any

from livekit import api

log = logging.getLogger("telephony")

# SIP response codes -> why the call did not connect (what the Dashboard and the call record show).
_BUSY = {486, 600}
_NO_ANSWER = {408, 480, 487}  # timed out / temporarily unavailable / cancelled after ringing
_DECLINED = {603}
_INVALID = {404, 410, 484, 604}


def failure_reason(sip_status_code: int | None) -> str:
    if sip_status_code in _BUSY:
        return "busy"
    if sip_status_code in _NO_ANSWER:
        return "no_answer"
    if sip_status_code in _DECLINED:
        return "declined"
    if sip_status_code in _INVALID:
        return "invalid_number"
    return "dial_failed"  # trunk, permission or network problems (e.g. 403: country not allowed on the trunk)


def phone_identity(call_id: str) -> str:
    """The borrower's participant identity in the room; the session listens to this participant only."""
    return f"phone-{call_id.replace('-', '')[:12]}"


@dataclass
class DialResult:
    identity: str | None  # set when the borrower answered
    reason: str | None = None  # set when they did not: busy | no_answer | declined | invalid_number | dial_failed
    sip_status_code: int | None = None

    @property
    def answered(self) -> bool:
        return self.identity is not None


def dial_request(room: str, call_id: str, dial: dict[str, Any]) -> api.CreateSIPParticipantRequest:
    req = api.CreateSIPParticipantRequest(
        room_name=room,
        sip_trunk_id=str(dial["trunk_id"]),
        sip_call_to=str(dial["to"]),
        participant_identity=phone_identity(call_id),
        participant_name="Phone",
        wait_until_answered=True,  # returns once the borrower picks up, or raises with the SIP status
        play_dialtone=False,
    )
    req.ringing_timeout.seconds = int(dial.get("ringing_timeout_s", 40))
    return req


async def dial_borrower(lk: Any, *, room: str, call_id: str, dial: dict[str, Any]) -> DialResult:
    """Rings the borrower and waits. `lk` is a LiveKitAPI (the job context's)."""
    req = dial_request(room, call_id, dial)
    try:
        await lk.sip.create_sip_participant(req)
    except api.SipCallError as e:  # the call itself failed: busy, no answer, declined, ...
        code = e.sip_status_code
        log.info("phone call not connected", extra={"call_id": call_id, "sip_status_code": code})
        return DialResult(identity=None, reason=failure_reason(code), sip_status_code=code)
    except Exception:  # trunk misconfiguration, auth, network
        log.exception("phone call could not be placed", extra={"call_id": call_id})
        return DialResult(identity=None, reason="dial_failed")
    return DialResult(identity=req.participant_identity)
