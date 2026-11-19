import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import AgentProfileVersion, Call, CallLink, User
from tests.unit.test_accounts_api import make_agent, register


async def _add_call(sm: Any, uid: str, *, agent: str | None, start: datetime) -> None:
    async with sm() as s:
        user = await s.get(User, uuid.UUID(uid))
        assert user is not None
        pv = (await s.scalars(select(AgentProfileVersion).limit(1))).first()
        assert pv is not None
        cid = uuid.uuid4()
        s.add(
            Call(
                id=cid,
                workspace_id=user.workspace_id,
                room_name=f"r-{cid}",
                correlation_id="c",
                profile_version_id=pv.id,
                started_at=start,
                created_at=start,
                ended_at=start + timedelta(minutes=3),
            )
        )
        await s.flush()
        s.add(CallLink(call_id=cid, uid=user.uid, agent_aid=uuid.UUID(agent) if agent else None))
        await s.commit()


async def test_seven_zero_days_without_an_agent(client: AsyncClient) -> None:
    u = await register(client)
    r = await client.get(f"/api/v1/users/{u['uid']}/stats/calls-per-day")
    assert r.status_code == 200
    body = r.json()
    assert body["tz"] == "UTC" and len(body["days"]) == 7
    assert body["days"][-1]["date"] == body["today"] == datetime.now(UTC).date().isoformat()
    assert all(d["calls"] == 0 for d in body["days"])
    assert body["days"][-1]["weekday"] == ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[datetime.now(UTC).weekday()]


async def test_counts_only_the_agents_calls_in_the_last_seven_days(client: AsyncClient, app_and_sm: Any) -> None:
    _, sm = app_and_sm
    u = await register(client)
    aid = (await make_agent(client, u["uid"]))["aid"]
    now = datetime.now(UTC)
    for _ in range(3):
        await _add_call(sm, u["uid"], agent=aid, start=now)
    await _add_call(sm, u["uid"], agent=aid, start=now - timedelta(days=2))
    await _add_call(sm, u["uid"], agent=aid, start=now - timedelta(days=10))  # too old
    await _add_call(sm, u["uid"], agent=None, start=now)  # not an agent call
    days = (await client.get(f"/api/v1/users/{u['uid']}/stats/calls-per-day")).json()["days"]
    assert [d["calls"] for d in days] == [0, 0, 0, 0, 1, 0, 3]
    # a deleted agent's calls do not count for the new agent
    await client.delete(f"/api/v1/users/{u['uid']}/agent")
    await make_agent(client, u["uid"], "Ben")
    days = (await client.get(f"/api/v1/users/{u['uid']}/stats/calls-per-day")).json()["days"]
    assert sum(d["calls"] for d in days) == 0


async def test_timezone_validation_and_ownership(client: AsyncClient, other_client: AsyncClient) -> None:
    a = await register(client)
    b = await register(other_client, "bob@example.com", "Bob")
    url = f"/api/v1/users/{a['uid']}/stats/calls-per-day"
    assert (await client.get(url, params={"tz": "Asia/Kolkata"})).json()["tz"] == "Asia/Kolkata"
    assert (await client.get(url, params={"tz": "Nope/Zone"})).status_code == 422
    assert (await other_client.get(url)).status_code == 403
    assert (await other_client.get(f"/api/v1/users/{b['uid']}/stats/calls-per-day")).status_code == 200
