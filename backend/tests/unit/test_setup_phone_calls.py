"""The one-time Twilio + LiveKit trunk setup, against a simulated Twilio REST API and LiveKit SIP API."""

import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.scripts.setup_phone_calls import (
    LIVEKIT_TRUNK_NAME,
    NAME,
    SetupError,
    load_config,
    setup_livekit,
    setup_twilio,
    strong_password,
)

SID = "AC0000000000000000000000000000abcd"
ENV = {
    "TWILIO_ACCOUNT_SID": SID,
    "TWILIO_AUTH_TOKEN": "token",
    "TWILIO_PHONE_NUMBER": "+15550001111",
    "LIVEKIT_URL": '"wss://x.livekit.cloud"',
    "LIVEKIT_API_KEY": "key",
    "LIVEKIT_API_SECRET": "secret",
    "SIP_AUTH_PASSWORD": "Abcdefghijk1",
}


class FakeTwilio:
    """Just enough of Twilio's REST API: state in dicts, every write recorded."""

    def __init__(self, *, trial: bool = False, owns_number: bool = True) -> None:
        self.trial, self.owns_number = trial, owns_number
        self.trunks: list[dict[str, Any]] = []
        self.cred_lists: list[dict[str, Any]] = []
        self.creds: list[dict[str, Any]] = []
        self.trunk_lists: list[dict[str, Any]] = []
        self.trunk_numbers: list[dict[str, Any]] = []
        self.writes: list[tuple[str, dict[str, list[str]]]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, form = req.url.path, parse_qs(req.content.decode()) if req.method == "POST" else {}
        if req.method == "POST":
            self.writes.append((path, form))
        acct = f"/2010-04-01/Accounts/{SID}"
        if path == f"{acct}.json":
            return httpx.Response(200, json={"type": "Trial" if self.trial else "Full"})
        if path == f"{acct}/IncomingPhoneNumbers.json":
            nums = [{"sid": "PN1", "phone_number": "+15550001111"}] if self.owns_number else []
            return httpx.Response(200, json={"incoming_phone_numbers": nums})
        if path == "/v1/Trunks" and req.method == "GET":
            return httpx.Response(200, json={"trunks": self.trunks})
        if path == "/v1/Trunks":
            t = {"sid": "TK1", "friendly_name": form["FriendlyName"][0], "domain_name": form["DomainName"][0]}
            self.trunks.append(t)
            return httpx.Response(201, json=t)
        if path == f"{acct}/SIP/CredentialLists.json" and req.method == "GET":
            return httpx.Response(200, json={"credential_lists": self.cred_lists})
        if path == f"{acct}/SIP/CredentialLists.json":
            cl = {"sid": "CL1", "friendly_name": form["FriendlyName"][0]}
            self.cred_lists.append(cl)
            return httpx.Response(201, json=cl)
        if path == f"{acct}/SIP/CredentialLists/CL1/Credentials.json" and req.method == "GET":
            return httpx.Response(200, json={"credentials": self.creds})
        if path == f"{acct}/SIP/CredentialLists/CL1/Credentials.json":
            self.creds.append({"sid": "CR1", "username": form["Username"][0]})
            return httpx.Response(201, json=self.creds[-1])
        if path == f"{acct}/SIP/CredentialLists/CL1/Credentials/CR1.json":
            return httpx.Response(200, json=self.creds[0])
        if path == "/v1/Trunks/TK1/CredentialLists":
            if req.method == "POST":
                self.trunk_lists.append({"sid": form["CredentialListSid"][0]})
            return httpx.Response(200, json={"credential_lists": self.trunk_lists})
        if path == "/v1/Trunks/TK1/PhoneNumbers":
            if req.method == "POST":
                self.trunk_numbers.append({"sid": form["PhoneNumberSid"][0]})
            return httpx.Response(200, json={"phone_numbers": self.trunk_numbers})
        if path == "/v1/DialingPermissions/BulkCountryUpdates":
            return httpx.Response(202, json={"update_count": 1})
        return httpx.Response(404, json={"message": f"unexpected {req.method} {path}"})


def _client(fake: FakeTwilio) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


def test_config_needs_the_twilio_number_and_generates_a_strong_password() -> None:
    with pytest.raises(SetupError, match="TWILIO_PHONE_NUMBER"):
        load_config({**ENV, "TWILIO_PHONE_NUMBER": ""})
    cfg = load_config({k: v for k, v in ENV.items() if k != "SIP_AUTH_PASSWORD"})
    assert cfg.password_generated and len(cfg.sip_password) >= 12
    assert cfg.domain == "alex-voice-0000abcd.pstn.twilio.com" and cfg.livekit_url == "wss://x.livekit.cloud"
    p = strong_password()
    assert any(c.isupper() for c in p) and any(c.islower() for c in p) and any(c.isdigit() for c in p)


def test_first_run_creates_and_connects_everything() -> None:
    fake, cfg = FakeTwilio(), load_config(ENV)
    setup_twilio(_client(fake), cfg, country="in", log=lambda *_: None)
    paths = [p for p, _ in fake.writes]
    assert paths == [
        "/v1/Trunks",
        f"/2010-04-01/Accounts/{SID}/SIP/CredentialLists.json",
        f"/2010-04-01/Accounts/{SID}/SIP/CredentialLists/CL1/Credentials.json",
        "/v1/Trunks/TK1/CredentialLists",
        "/v1/Trunks/TK1/PhoneNumbers",
        "/v1/DialingPermissions/BulkCountryUpdates",
    ]
    forms = dict(fake.writes)
    assert forms["/v1/Trunks"] == {"FriendlyName": [NAME], "DomainName": ["alex-voice-0000abcd.pstn.twilio.com"]}
    cred = forms[f"/2010-04-01/Accounts/{SID}/SIP/CredentialLists/CL1/Credentials.json"]
    assert cred == {"Username": ["alex_livekit"], "Password": ["Abcdefghijk1"]}
    assert forms["/v1/Trunks/TK1/PhoneNumbers"] == {"PhoneNumberSid": ["PN1"]}
    upd = json.loads(forms["/v1/DialingPermissions/BulkCountryUpdates"]["UpdateRequest"][0])
    assert upd == [{"iso_code": "IN", "low_risk_numbers_enabled": "true"}]


def test_second_run_only_resets_the_credential_password() -> None:
    fake, cfg = FakeTwilio(), load_config(ENV)
    setup_twilio(_client(fake), cfg, country=None, log=lambda *_: None)
    fake.writes.clear()
    setup_twilio(_client(fake), cfg, country=None, log=lambda *_: None)
    assert [p for p, _ in fake.writes] == [f"/2010-04-01/Accounts/{SID}/SIP/CredentialLists/CL1/Credentials/CR1.json"]


def test_stops_on_a_trial_account_or_a_number_it_does_not_own() -> None:
    with pytest.raises(SetupError, match="trial account"):
        setup_twilio(_client(FakeTwilio(trial=True)), load_config(ENV), country=None, log=lambda *_: None)
    fake = FakeTwilio(owns_number=False)
    with pytest.raises(SetupError, match="not a number on this Twilio account"):
        setup_twilio(_client(fake), load_config(ENV), country=None, log=lambda *_: None)
    assert fake.writes == []  # nothing was changed


class FakeSip:
    def __init__(self, existing: bool) -> None:
        self.items = [SimpleNamespace(name=LIVEKIT_TRUNK_NAME, sip_trunk_id="ST_old")] if existing else []
        self.created: list[Any] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    async def list_outbound_trunk(self, _req: Any) -> Any:
        return SimpleNamespace(items=self.items)

    async def create_outbound_trunk(self, req: Any) -> Any:
        self.created.append(req)
        return SimpleNamespace(sip_trunk_id="ST_new")

    async def update_outbound_trunk_fields(self, trunk_id: str, **fields: Any) -> Any:
        self.updated.append((trunk_id, fields))
        return SimpleNamespace(sip_trunk_id=trunk_id)


async def test_livekit_trunk_is_created_once_then_updated_in_place() -> None:
    cfg = load_config(ENV)
    cfg.domain = "alex-voice-x.pstn.twilio.com"
    sip = FakeSip(existing=False)
    assert await setup_livekit(SimpleNamespace(sip=sip), cfg, log=lambda *_: None) == "ST_new"
    t = sip.created[0].trunk
    assert (t.name, t.address, list(t.numbers), t.auth_username, t.auth_password) == (
        LIVEKIT_TRUNK_NAME,
        "alex-voice-x.pstn.twilio.com",
        ["+15550001111"],
        "alex_livekit",
        "Abcdefghijk1",
    )
    sip = FakeSip(existing=True)
    assert await setup_livekit(SimpleNamespace(sip=sip), cfg, log=lambda *_: None) == "ST_old"  # same trunk id kept
    assert sip.created == [] and sip.updated[0][1]["address"] == "alex-voice-x.pstn.twilio.com"
