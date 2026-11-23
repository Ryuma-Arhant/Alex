import uuid
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Call
from app.services import livekit_service
from tests.conftest import INTERNAL
from tests.unit.test_accounts_api import make_agent, register

BODY = {"phone": "+91 98123 45678", "amount": "12000", "context": "Client: Asha Rao", "mode": "phone"}
SECRET = "test-livekit-secret-0123456789abcdef0123"


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Records agent dispatches instead of calling LiveKit."""
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(settings: Any, *, room: str, call_id: uuid.UUID, correlation_id: str) -> None:
        seen.append({"room": room, "call_id": str(call_id), "agent": settings.agent_name})

    monkeypatch.setattr(livekit_service, "dispatch_agent", fake_dispatch)
    return seen


@pytest.fixture
def phone_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Phone calls switched on (a LiveKit outbound trunk is configured). Must come before `client` in a test."""
    monkeypatch.setenv("SIP_OUTBOUND_TRUNK_ID", "ST_test_trunk")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _setup(client: AsyncClient) -> str:
    u = await register(client)
    await make_agent(client, u["uid"], "Maya")
    return str(u["uid"])


async def test_phone_calls_are_off_until_the_trunk_is_set_up(client: AsyncClient, dispatched: list[Any]) -> None:
    uid = await _setup(client)
    assert (await client.get("/api/v1/auth/config")).json()["phone_calls"] is False
    r = await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)
    assert r.status_code == 409 and "not set up" in r.text
    assert dispatched == []
    # browser calls are unchanged
    r = await client.post(f"/api/v1/users/{uid}/collections/calls", json={**BODY, "mode": "web"})
    assert r.status_code == 200 and r.json()["mode"] == "web"


async def test_phone_call_dispatches_the_agent_and_gives_a_listen_only_token(
    phone_on: None, client: AsyncClient, dispatched: list[dict[str, Any]]
) -> None:
    uid = await _setup(client)
    assert (await client.get("/api/v1/auth/config")).json()["phone_calls"] is True
    r = await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "phone"
    cid = body["call_id"]
    assert len(dispatched) == 1 and dispatched[0]["call_id"] == cid

    claims = jwt.decode(body["token"], SECRET, algorithms=["HS256"], options={"verify_aud": False})
    assert claims["video"]["roomJoin"] is True and claims["video"]["room"] == dispatched[0]["room"]
    assert claims["video"]["canPublish"] is False and claims["video"]["canSubscribe"] is True
    assert "roomConfig" not in claims  # joining must not dispatch a second agent

    ctx = (await client.get(f"/internal/calls/{cid}/context", headers=INTERNAL)).json()
    assert ctx["direction"] == "OUTBOUND"
    assert ctx["dial"] == {"to": "+919812345678", "trunk_id": "ST_test_trunk", "ringing_timeout_s": 40}
    assert "outbound phone call" not in str(ctx["profile"])  # the agent adds the direction itself at runtime

    public = (await client.get(f"/api/v1/calls/{cid}")).json()
    assert "9812345678" not in str(public)  # the number never leaves through the public API
    # one call at a time: the agent is now busy
    again = await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)
    assert again.status_code == 409 and "already on a call" in again.text


async def test_unanswered_call_records_why_and_forgets_the_number(
    phone_on: None, client: AsyncClient, dispatched: list[Any]
) -> None:
    uid = await _setup(client)
    cid = (await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)).json()["call_id"]
    ev = {"type": "dial_failed", "payload": {"reason": "busy", "sip_status_code": 486}}
    assert (await client.post(f"/internal/calls/{cid}/events", json=ev, headers=INTERNAL)).status_code == 200
    ctx = (await client.get(f"/internal/calls/{cid}/context", headers=INTERNAL)).json()
    assert "dial" not in ctx  # dial_to was cleared
    call = (await client.get(f"/api/v1/calls/{cid}")).json()
    assert call["end_reason"] == "busy" and call["ended_at"] is not None
    recent = (await client.get(f"/api/v1/users/{uid}/dashboard")).json()["recent_calls"][0]
    assert recent["phone"] is True and recent["end_reason"] == "busy"


async def test_unknown_dial_failures_are_recorded_generically(
    phone_on: None, client: AsyncClient, dispatched: list[Any]
) -> None:
    uid = await _setup(client)
    cid = (await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)).json()["call_id"]
    ev = {"type": "dial_failed", "payload": {"reason": "something; DROP TABLE"}}
    await client.post(f"/internal/calls/{cid}/events", json=ev, headers=INTERNAL)
    assert (await client.get(f"/api/v1/calls/{cid}")).json()["end_reason"] == "dial_failed"


async def test_answered_call_counts_from_pickup_and_forgets_the_number_at_the_end(
    phone_on: None, client: AsyncClient, dispatched: list[Any], app_and_sm: Any
) -> None:
    _, sm = app_and_sm
    uid = await _setup(client)
    cid = (await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)).json()["call_id"]
    async with sm() as s:
        created = (await s.get(Call, uuid.UUID(cid))).started_at
    await client.post(f"/internal/calls/{cid}/events", json={"type": "answered"}, headers=INTERNAL)
    await client.post(f"/internal/calls/{cid}/events", json={"type": "agent_joined"}, headers=INTERNAL)
    async with sm() as s:
        call = await s.get(Call, uuid.UUID(cid))
        assert call is not None and call.started_at >= created and call.dial_to == "+919812345678"
    await client.post(
        f"/internal/calls/{cid}/events",
        json={"type": "session_closed", "payload": {"reason": "hangup"}},
        headers=INTERNAL,
    )
    async with sm() as s:
        call = await s.get(Call, uuid.UUID(cid))
        assert call is not None and call.dial_to is None and call.end_reason == "hangup"


async def test_dispatch_failure_is_reported_and_leaves_no_number(
    phone_on: None, client: AsyncClient, app_and_sm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sm = app_and_sm

    async def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("livekit down")

    monkeypatch.setattr(livekit_service, "dispatch_agent", broken)
    uid = await _setup(client)
    r = await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)
    assert r.status_code == 502 and "Could not start the phone call" in r.text
    async with sm() as s:
        row = (await s.scalars(select(Call))).one()
        assert row.state == "FAILED" and row.end_reason == "dial_failed" and row.dial_to is None
