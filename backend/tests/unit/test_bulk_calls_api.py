from httpx import AsyncClient

from tests.unit.test_accounts_api import register

GOOD = (
    "Borrower Name,Mobile Number,Amount Due,Due Date,Bank,Loan ID,Extra\n"
    'Ravi Kumar,+91 98765-43210,"₹5,200.50",05/11/2026,Sunrise Bank,LN-1,x\n'
    "Asha Rao,9876500000,1500,2026-12-01,,,\n"
    "\n"
    "Bad Row,12345,-3,31/02/2026,,,\n"
    "Dup Person,+919876543210,100,5 Nov 2026,,,\n"
)


async def _preview(c: AsyncClient, uid: str, body: bytes) -> tuple[int, dict]:  # type: ignore[type-arg]
    r = await c.post(f"/api/v1/users/{uid}/bulk-calls/preview", content=body, headers={"content-type": "text/csv"})
    return r.status_code, r.json()


async def test_preview_validates_every_row(client: AsyncClient) -> None:
    u = await register(client)
    status, body = await _preview(client, u["uid"], GOOD.encode())
    assert status == 200, body
    assert (body["total"], body["valid"], body["invalid"]) == (4, 3, 1)
    assert body["columns"]["phone"] == "Mobile Number" and body["ignored_columns"] == ["Extra"]
    ravi, asha, bad, dup = body["rows"]
    assert ravi["valid"] and ravi["phone"] == "+919876543210" and ravi["amount"] == "5200.50"
    assert ravi["deadline"] == "2026-11-05" and ravi["lender"] == "Sunrise Bank" and ravi["loan_reference"] == "LN-1"
    assert asha["valid"] and asha["currency"] == "INR" and asha["lender"] == ""
    assert not bad["valid"] and bad["line"] == 5 and len(bad["errors"]) == 3
    assert dup["valid"] and dup["deadline"] == "2026-11-05" and dup["warnings"] == ["Same phone number as line 2"]


async def test_preview_rejects_unusable_files(client: AsyncClient) -> None:
    u = await register(client)
    assert (await _preview(client, u["uid"], b""))[0] == 422
    status, body = await _preview(client, u["uid"], b"name,phone\nRavi,+919876543210\n")
    assert status == 422 and "Amount due" in body["error"]["message"] and "Deadline" in body["error"]["message"]
    assert (await _preview(client, u["uid"], b"name,phone,amount,deadline\n"))[0] == 422
    assert (await _preview(client, u["uid"], b"x" * (1024 * 1024 + 1)))[0] == 422


async def test_preview_handles_semicolons_bom_and_cp1252(client: AsyncClient) -> None:
    u = await register(client)
    semi = "﻿Name;Phone;Amount;Deadline\nRené Doe;+33612345678;10;01.02.2027\n"
    status, body = await _preview(client, u["uid"], semi.encode("utf-8"))
    assert status == 200 and body["rows"][0]["name"] == "René Doe" and body["valid"] == 1
    status, body = await _preview(client, u["uid"], semi.replace("﻿", "").encode("cp1252"))
    assert status == 200 and body["rows"][0]["name"] == "René Doe"


async def test_preview_is_scoped_and_csrf_protected(client: AsyncClient, other_client: AsyncClient) -> None:
    a = await register(client)
    await register(other_client, "bob@example.com", "Bob")
    assert (await _preview(other_client, a["uid"], GOOD.encode()))[0] == 403
    del client.headers["X-CSRF-Token"]
    assert (await _preview(client, a["uid"], GOOD.encode()))[0] == 403
