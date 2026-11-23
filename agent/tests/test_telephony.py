"""Phone calls: dialing through the SIP trunk, and why a call did not connect."""

from typing import Any

import pytest
from livekit import api

from voice_agent.telephony import dial_borrower, dial_request, failure_reason, phone_identity

DIAL = {"to": "+919812345678", "trunk_id": "ST_trunk", "ringing_timeout_s": 35}
CALL = "0b3f8c1e-1d2c-4f5a-9e8d-7c6b5a4f3e2d"


class FakeSip:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[Any] = []

    async def create_sip_participant(self, req: Any) -> None:
        self.requests.append(req)
        if self.error:
            raise self.error


class FakeLK:
    def __init__(self, error: Exception | None = None) -> None:
        self.sip = FakeSip(error)


def sip_error(code: int, reason: str) -> api.SipCallError:
    return api.SipCallError(
        "unavailable", f"{code} {reason}", status=503, metadata={"sip_status_code": str(code), "sip_status": reason}
    )


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (486, "busy"),
        (600, "busy"),
        (480, "no_answer"),
        (408, "no_answer"),
        (487, "no_answer"),
        (603, "declined"),
        (404, "invalid_number"),
        (484, "invalid_number"),
        (403, "dial_failed"),
        (500, "dial_failed"),
        (None, "dial_failed"),
    ],
)
def test_sip_status_codes_map_to_a_reason(code: int | None, reason: str) -> None:
    assert failure_reason(code) == reason


def test_the_request_waits_for_an_answer_on_the_configured_trunk() -> None:
    req = dial_request("call-room", CALL, DIAL)
    assert req.room_name == "call-room" and req.sip_trunk_id == "ST_trunk" and req.sip_call_to == "+919812345678"
    assert req.wait_until_answered is True and req.ringing_timeout.seconds == 35
    assert req.participant_identity == phone_identity(CALL) == "phone-0b3f8c1e1d2c"


async def test_answered_call_returns_the_phone_participant() -> None:
    lk = FakeLK()
    r = await dial_borrower(lk, room="r", call_id=CALL, dial=DIAL)
    assert r.answered and r.identity == "phone-0b3f8c1e1d2c" and r.reason is None
    assert len(lk.sip.requests) == 1


async def test_busy_line_is_reported_with_its_sip_status() -> None:
    r = await dial_borrower(FakeLK(sip_error(486, "Busy Here")), room="r", call_id=CALL, dial=DIAL)
    assert not r.answered and r.reason == "busy" and r.sip_status_code == 486


async def test_unreachable_trunk_is_a_generic_failure() -> None:
    r = await dial_borrower(FakeLK(RuntimeError("connection refused")), room="r", call_id=CALL, dial=DIAL)
    assert not r.answered and r.reason == "dial_failed" and r.sip_status_code is None
