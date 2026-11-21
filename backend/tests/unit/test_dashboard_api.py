import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from app.db.models import Call
from tests.conftest import INTERNAL
from tests.unit.test_accounts_api import make_agent, register
from tests.unit.test_calls_api import GOOD_SUMMARY

BODY = {"phone": "+91 98123 45678", "amount": "12000", "context": "Client: Asha Rao"}


async def _call(client: AsyncClient, uid: str, **summary: Any) -> str:
    """An individual call through the real API, with reply timings and (optionally) a summary."""
    r = await client.post(f"/api/v1/users/{uid}/collections/calls", json=BODY)
    assert r.status_code == 200, r.text
    cid: str = r.json()["call_id"]
    turns = [
        {"seq": 0, "speaker": "agent", "text": "Hello", "metrics_json": {"tts_node_ttfb": 0.3}},  # greeting
        {"seq": 1, "speaker": "user", "text": "Hi"},
        {"seq": 2, "speaker": "agent", "text": "About your loan", "metrics_json": {"e2e_latency": 1.0}},
        {"seq": 3, "speaker": "agent", "text": "Can you pay?", "metrics_json": {"e2e_latency": 2.0}},
    ]
    assert (
        await client.post(f"/internal/calls/{cid}/turns", json={"turns": turns}, headers=INTERNAL)
    ).status_code == 200
    await client.post(f"/internal/calls/{cid}/events", json={"type": "session_closed"}, headers=INTERNAL)
    if summary:
        body = {"summary": {**GOOD_SUMMARY, **summary}, "model_version": "m"}
        assert (await client.post(f"/internal/calls/{cid}/summary", json=body, headers=INTERNAL)).status_code == 200
    return cid


async def test_empty_dashboard_without_an_agent(client: AsyncClient) -> None:
    u = await register(client)
    d = (await client.get(f"/api/v1/users/{u['uid']}/dashboard")).json()
    assert d["calls_today"] == 0 and d["recent_calls"] == [] and d["next_actions"] == []
    assert d["reply_seconds"] is None and d["promises"] == {"promised": 0, "of": 0} and d["need_person"] == 0


async def test_dashboard_figures_come_from_the_agents_calls(client: AsyncClient, app_and_sm: Any) -> None:
    _, sm = app_and_sm
    u = await register(client)
    await make_agent(client, u["uid"], "Maya")
    actions = [
        {"action": "Send the UPI link", "owner": "agent", "due_if_stated": None},
        {"action": "Pay 6,000 rupees", "owner": "caller", "due_if_stated": "Friday"},
    ]
    a = await _call(client, u["uid"], promise_to_pay=True, sentiment="calm", agent_commitments_and_next_actions=actions)
    b = await _call(client, u["uid"], call_outcome="escalated", escalation_needed=True, sentiment="upset")
    c = await _call(client, u["uid"])  # summary not written yet
    async with sm() as s:  # a known length for the first call
        call = await s.get(Call, uuid.UUID(a))
        assert call is not None
        call.started_at = datetime.now(UTC) - timedelta(minutes=3, seconds=10)
        call.ended_at = datetime.now(UTC)
        await s.commit()

    d = (await client.get(f"/api/v1/users/{u['uid']}/dashboard", params={"tz": "Asia/Kolkata"})).json()
    assert d["tz"] == "Asia/Kolkata" and d["calls_today"] == 3
    assert d["promises"] == {"promised": 1, "of": 2}  # the unsummarised call is not counted
    assert d["need_person"] == 1
    assert d["reply_seconds"] == 1.5 and d["replies"] == 6  # greetings (no e2e_latency) are not replies
    assert [r["call_id"] for r in d["recent_calls"]] == [c, b, a]  # newest first
    first = d["recent_calls"][2]
    assert first["phone_last4"] == "5678" and first["amount"] == "12000.00" and first["currency"] == "INR"
    assert first["promise_to_pay"] is True and first["sentiment"] == "calm" and first["length_seconds"] == 190
    assert d["recent_calls"][1]["outcome"] == "escalated" and d["recent_calls"][1]["escalation_needed"] is True
    assert d["recent_calls"][0]["status"] == "summarising" and d["recent_calls"][0]["outcome"] is None
    assert "98123" not in str(d)  # only the last four digits are ever stored or shown
    assert [(n["action"], n["owner"], n["due"], n["done"]) for n in d["next_actions"]] == [
        ("Send the UPI link", "agent", None, False),
        ("Pay 6,000 rupees", "caller", "Friday", False),
    ]


async def test_next_actions_can_be_ticked_and_unticked(client: AsyncClient, other_client: AsyncClient) -> None:
    u = await register(client)
    await make_agent(client, u["uid"])
    acts = [{"action": "Send the UPI link", "owner": "agent", "due_if_stated": None}]
    cid = await _call(client, u["uid"], agent_commitments_and_next_actions=acts)
    url = f"/api/v1/users/{u['uid']}/dashboard/next-actions/{cid}"
    assert (await client.put(f"{url}/0", json={"done": True})).json() == {"done": True}
    assert (await client.put(f"{url}/0", json={"done": True})).status_code == 200  # idempotent
    dash = f"/api/v1/users/{u['uid']}/dashboard"
    assert (await client.get(dash)).json()["next_actions"][0]["done"] is True
    assert (await client.put(f"{url}/0", json={"done": False})).json() == {"done": False}
    assert (await client.get(dash)).json()["next_actions"][0]["done"] is False
    assert (await client.put(f"{url}/1", json={"done": True})).status_code == 404  # no such action
    unknown = f"/api/v1/users/{u['uid']}/dashboard/next-actions/{uuid.uuid4()}/0"
    assert (await client.put(unknown, json={"done": True})).status_code == 404
    # another user can neither read nor tick this user's dashboard
    b = await register(other_client, "bob@example.com", "Bob")
    assert (await other_client.get(dash)).status_code == 403
    assert (await other_client.put(f"{url}/0", json={"done": True})).status_code == 403
    theirs = f"/api/v1/users/{b['uid']}/dashboard/next-actions/{cid}/0"
    assert (await other_client.put(theirs, json={"done": True})).status_code == 404  # not their call
    del client.headers["X-CSRF-Token"]
    assert (await client.put(f"{url}/0", json={"done": True})).status_code == 403
