import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from httpx import AsyncClient

from app.core.config import get_settings

PW = "correct-horse-1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def register(c: AsyncClient, email: str = "ann@example.com", name: str = "Ann") -> dict[str, Any]:
    r = await c.post("/api/v1/auth/register", json={"username": name, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]
    return r.json()  # type: ignore[no-any-return]


async def test_register_login_me_logout(client: AsyncClient) -> None:
    u = await register(client)
    assert u["username"] == "Ann" and u["agent_count"] == 0
    assert (await client.get("/api/v1/auth/me")).json()["uid"] == u["uid"]
    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.post("/api/v1/auth/login", json={"email": "ann@example.com", "password": "wrong-password"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "no@example.com", "password": "wrong-password"})
    assert (
        bad.status_code == unknown.status_code == 401
        and bad.json()["error"]["message"] == unknown.json()["error"]["message"]
    )
    ok = await client.post("/api/v1/auth/login", json={"email": "ANN@example.com", "password": PW})
    assert ok.status_code == 200 and ok.json()["uid"] == u["uid"]


async def test_register_validation_and_duplicate(client: AsyncClient) -> None:
    await register(client)
    dup = await client.post(
        "/api/v1/auth/register", json={"username": "Ann2", "email": "ann@example.com", "password": PW}
    )
    assert dup.status_code == 409
    short = await client.post(
        "/api/v1/auth/register", json={"username": "Bo", "email": "bo@example.com", "password": "short"}
    )
    assert short.status_code == 422


async def test_password_not_stored_plaintext(client: AsyncClient, app_and_sm: Any) -> None:
    from sqlalchemy import select

    from app.db.models import User

    await register(client)
    _, sm = app_and_sm
    async with sm() as s:
        u = (await s.scalars(select(User))).one()
    assert u.password_hash and PW not in u.password_hash and u.password_hash.startswith("$argon2")


async def test_tampered_and_expired_tokens_rejected(client: AsyncClient) -> None:
    u = await register(client)
    good = client.cookies["access_token"]
    s = get_settings()
    forged = jwt.encode(
        {"sub": u["uid"], "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "x" * 32,
        algorithm="HS256",
    )
    expired = jwt.encode(
        {"sub": u["uid"], "iat": datetime.now(UTC) - timedelta(hours=2), "exp": datetime.now(UTC) - timedelta(hours=1)},
        s.auth_jwt_secret,
        algorithm="HS256",
    )
    for bad in (forged, expired, good[:-3] + "abc", "garbage"):
        client.cookies.set("access_token", bad)
        assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.set("access_token", good)
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_uid_mismatch_is_403_and_csrf_enforced(client: AsyncClient, other_client: AsyncClient) -> None:
    a = await register(client)
    b = await register(other_client, "bob@example.com", "Bob")
    assert (await client.get(f"/api/v1/users/{b['uid']}")).status_code == 403
    assert (await client.get(f"/api/v1/users/{b['uid']}/agent")).status_code == 403
    assert (await client.get(f"/api/v1/users/{a['uid']}/agent")).status_code == 200
    del client.headers["X-CSRF-Token"]
    body = {"name": "X", "voice": "male"}
    assert (await client.post(f"/api/v1/users/{a['uid']}/agent", json=body)).status_code == 403


async def make_agent(c: AsyncClient, uid: str, name: str = "Ava", voice: str = "male") -> dict[str, Any]:
    r = await c.post(f"/api/v1/users/{uid}/agent", json={"name": name, "voice": voice})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_single_agent_lifecycle(client: AsyncClient) -> None:
    u = await register(client)
    url = f"/api/v1/users/{u['uid']}/agent"
    r = await client.get(url)
    assert r.status_code == 200 and r.json() is None  # state A: no agent yet
    a = await make_agent(client, u["uid"], "  Ava   Rao ")
    assert a["name"] == "Ava Rao" and a["status"] == "free" and a["role"] == "Loan-Recovery Agent"
    assert "Loan-Recovery Agent" in a["system_prompt"] and "You are Ava Rao" in a["system_prompt"]
    assert (await client.get(url)).json()["aid"] == a["aid"]
    assert (await client.get("/api/v1/auth/me")).json()["agent_count"] == 1
    # only one agent at a time
    dup = await client.post(url, json={"name": "Second", "voice": "female"})
    assert dup.status_code == 409
    for bad in ({"name": ""}, {"name": "   "}, {"name": "x" * 81}, {}):
        assert (await client.post(url, json=bad)).status_code in (409, 422)
    # rename: a new prompt version carries the new name
    r = await client.put(url, json={"name": "Maya"})
    assert r.status_code == 200 and r.json()["name"] == "Maya" and "You are Maya" in r.json()["system_prompt"]
    assert r.json()["aid"] == a["aid"]
    # delete -> back to state A, and a new agent can be created
    assert (await client.delete(url)).status_code == 204
    assert (await client.get(url)).json() is None
    assert (await client.get("/api/v1/auth/me")).json()["agent_count"] == 0
    assert (await client.put(url, json={"name": "Ghost"})).status_code == 404
    assert (await client.delete(url)).status_code == 404
    b = await make_agent(client, u["uid"], "Ben")
    assert b["aid"] != a["aid"]


async def test_agent_voice_is_chosen_at_creation_and_kept(client: AsyncClient) -> None:
    u = await register(client)
    url = f"/api/v1/users/{u['uid']}/agent"
    for bad in ({"name": "Ava"}, {"name": "Ava", "voice": "robot"}, {"name": "Ava", "voice": ""}):
        assert (await client.post(url, json=bad)).status_code == 422, bad
    a = await make_agent(client, u["uid"], "Ava", "female")
    assert a["voice"] == "female" and (await client.get(url)).json()["voice"] == "female"
    assert (await client.put(url, json={"name": "Maya"})).json()["voice"] == "female"  # renaming keeps it


async def test_every_agent_shares_the_same_prompt(client: AsyncClient, other_client: AsyncClient) -> None:
    a = await register(client)
    b = await register(other_client, "bob@example.com", "Bob")
    pa = (await make_agent(client, a["uid"], "Ava"))["system_prompt"]
    pb = (await make_agent(other_client, b["uid"], "Ava"))["system_prompt"]
    assert pa == pb


async def test_agent_is_busy_during_a_call_and_cannot_be_deleted(client: AsyncClient, app_and_sm: Any) -> None:
    from app.db.models import Call

    u = await register(client)
    await make_agent(client, u["uid"])
    r = await client.post(
        f"/api/v1/users/{u['uid']}/collections/calls",
        json={"borrower_name": "Ravi Kumar", "phone": "+919876543210", "amount": "100", "bank": "Sunrise Bank"},
    )
    assert r.status_code == 200, r.text
    url = f"/api/v1/users/{u['uid']}/agent"
    assert (await client.get(url)).json()["status"] == "busy"
    assert (await client.delete(url)).status_code == 409
    _, sm = app_and_sm
    async with sm() as s:
        call = await s.get(Call, uuid.UUID(r.json()["call_id"]))
        call.ended_at = datetime.now(UTC)
        await s.commit()
    assert (await client.get(url)).json()["status"] == "free"
    assert (await client.delete(url)).status_code == 204


async def test_avatar_upload(client: AsyncClient) -> None:
    u = await register(client)
    url = f"/api/v1/users/{u['uid']}/avatar"
    assert (await client.get(url)).status_code == 404
    bad = await client.put(url, content=b"not an image", headers={"content-type": "image/png"})
    assert bad.status_code == 422
    big = await client.put(url, content=PNG + b"0" * (2 * 1024 * 1024))
    assert big.status_code == 422
    ok = await client.put(url, content=PNG, headers={"content-type": "image/png"})
    assert ok.status_code == 200 and ok.json()["avatar_url"].startswith(url)
    got = await client.get(url)
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"


async def test_calls_isolated_between_users(client: AsyncClient, other_client: AsyncClient) -> None:
    a = await register(client)
    await register(other_client, "bob@example.com", "Bob")
    await make_agent(client, a["uid"])
    cid = (
        await client.post(
            f"/api/v1/users/{a['uid']}/collections/calls",
            json={"borrower_name": "Ravi Kumar", "phone": "+919876543210", "amount": "100", "bank": "Sunrise Bank"},
        )
    ).json()["call_id"]
    assert (await client.get(f"/api/v1/calls/{cid}")).status_code == 200
    assert (await other_client.get(f"/api/v1/calls/{cid}")).status_code == 404
