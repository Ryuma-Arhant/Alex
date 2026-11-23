"""One-time setup for real phone calls: connects a Twilio Elastic SIP trunk to LiveKit, so the agent can dial out.

    cd backend && uv run python -m app.scripts.setup_phone_calls [--country IN] [--dry-run]

Reads from the environment (.env): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER (a voice number the
account owns, E.164, shown as the caller ID) and the LIVEKIT_* settings. Optional: SIP_TRUNK_DOMAIN (default derived
from the account), SIP_AUTH_USERNAME / SIP_AUTH_PASSWORD (generated when absent).

Safe to run again: everything is looked up by name and only created when missing. It does, on Twilio,
  1. a SIP trunk "alex-livekit" with a *.pstn.twilio.com termination domain,
  2. a credential list (the username/password LiveKit authenticates with) attached to the trunk,
  3. the phone number attached to the trunk,
  4. (with --country) outbound calling allowed to that country (Voice Geographic Permissions),
and on LiveKit an outbound trunk pointing at the Twilio domain. It prints the SIP_OUTBOUND_TRUNK_ID to set; phone calls
stay switched off in the app until that variable is set.
"""

import argparse
import asyncio
import json
import secrets
import ssl
import string
import sys
from dataclasses import dataclass
from typing import Any

import aiohttp
import certifi
import httpx
from dotenv import dotenv_values
from livekit import api

NAME = "alex-livekit"  # Twilio trunk + credential list
LIVEKIT_TRUNK_NAME = "alex-twilio"
TWILIO_API = "https://api.twilio.com/2010-04-01"
TRUNKING_API = "https://trunking.twilio.com/v1"
VOICE_API = "https://voice.twilio.com/v1"


class SetupError(RuntimeError):
    pass


@dataclass
class Config:
    account_sid: str
    auth_token: str
    phone_number: str
    domain: str
    sip_username: str
    sip_password: str
    password_generated: bool
    livekit_url: str
    livekit_key: str
    livekit_secret: str


def strong_password() -> str:
    """Twilio SIP credentials need 12+ characters with upper case, lower case and a digit."""
    alphabet = string.ascii_letters + string.digits
    while True:
        p = "".join(secrets.choice(alphabet) for _ in range(24))
        if any(c.isupper() for c in p) and any(c.islower() for c in p) and any(c.isdigit() for c in p):
            return p


def load_config(env: dict[str, str | None]) -> Config:
    need = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "LIVEKIT_URL", "LIVEKIT_API_KEY"]
    missing = [k for k in [*need, "LIVEKIT_API_SECRET"] if not (env.get(k) or "").strip()]
    if missing:
        raise SetupError("Missing settings: " + ", ".join(missing))
    sid = str(env["TWILIO_ACCOUNT_SID"]).strip()
    password = (env.get("SIP_AUTH_PASSWORD") or "").strip()
    return Config(
        account_sid=sid,
        auth_token=str(env["TWILIO_AUTH_TOKEN"]).strip(),
        phone_number=str(env["TWILIO_PHONE_NUMBER"]).strip(),
        domain=(env.get("SIP_TRUNK_DOMAIN") or f"alex-voice-{sid[-8:].lower()}.pstn.twilio.com").strip(),
        sip_username=(env.get("SIP_AUTH_USERNAME") or "alex_livekit").strip(),
        sip_password=password or strong_password(),
        password_generated=not password,
        livekit_url=str(env["LIVEKIT_URL"]).strip().strip('"'),
        livekit_key=str(env["LIVEKIT_API_KEY"]).strip(),
        livekit_secret=str(env["LIVEKIT_API_SECRET"]).strip(),
    )


def _ok(r: httpx.Response, what: str) -> dict[str, Any]:
    if r.status_code >= 400:
        try:
            detail = r.json().get("message", r.text)
        except ValueError:
            detail = r.text
        raise SetupError(f"Twilio refused to {what} ({r.status_code}): {detail}")
    return r.json() if r.content else {}


def setup_twilio(c: httpx.Client, cfg: Config, *, country: str | None, log: Any = print) -> None:
    acct = f"{TWILIO_API}/Accounts/{cfg.account_sid}"
    account = _ok(c.get(f"{acct}.json"), "read the account")
    if account.get("type") == "Trial":
        raise SetupError("The Twilio account is a trial account: upgrade it first (SIP trunking is not available).")

    numbers = _ok(
        c.get(f"{acct}/IncomingPhoneNumbers.json", params={"PhoneNumber": cfg.phone_number}), "find the number"
    )
    found = numbers.get("incoming_phone_numbers") or []
    if not found:
        raise SetupError(f"{cfg.phone_number} is not a number on this Twilio account.")
    number_sid = found[0]["sid"]

    trunks = _ok(c.get(f"{TRUNKING_API}/Trunks", params={"PageSize": 100}), "list SIP trunks").get("trunks", [])
    trunk = next((t for t in trunks if t.get("friendly_name") == NAME), None)
    if trunk is None:
        trunk = _ok(
            c.post(f"{TRUNKING_API}/Trunks", data={"FriendlyName": NAME, "DomainName": cfg.domain}), "create the trunk"
        )
        log(f"created Twilio trunk {NAME} ({trunk['domain_name']})")
    else:
        log(f"Twilio trunk {NAME} exists ({trunk['domain_name']})")
    cfg.domain = trunk["domain_name"]
    trunk_sid = trunk["sid"]

    lists = _ok(c.get(f"{acct}/SIP/CredentialLists.json", params={"PageSize": 100}), "list credential lists")
    cred_list = next((x for x in lists.get("credential_lists", []) if x.get("friendly_name") == NAME), None)
    if cred_list is None:
        cred_list = _ok(
            c.post(f"{acct}/SIP/CredentialLists.json", data={"FriendlyName": NAME}), "create a credential list"
        )
        log(f"created credential list {NAME}")
    creds_url = f"{acct}/SIP/CredentialLists/{cred_list['sid']}/Credentials"
    creds = _ok(c.get(f"{creds_url}.json", params={"PageSize": 100}), "list credentials").get("credentials", [])
    existing = next((x for x in creds if x.get("username") == cfg.sip_username), None)
    if existing is None:
        _ok(
            c.post(f"{creds_url}.json", data={"Username": cfg.sip_username, "Password": cfg.sip_password}),
            "add the SIP credential",
        )
        log(f"added SIP credential {cfg.sip_username}")
    else:  # Twilio never returns a password: set it to the one LiveKit will use
        _ok(
            c.post(f"{creds_url}/{existing['sid']}.json", data={"Password": cfg.sip_password}),
            "update the SIP credential",
        )
        log(f"updated the password of SIP credential {cfg.sip_username}")

    attached = _ok(c.get(f"{TRUNKING_API}/Trunks/{trunk_sid}/CredentialLists"), "list the trunk's credentials")
    if not any(x.get("sid") == cred_list["sid"] for x in attached.get("credential_lists", [])):
        _ok(
            c.post(f"{TRUNKING_API}/Trunks/{trunk_sid}/CredentialLists", data={"CredentialListSid": cred_list["sid"]}),
            "attach the credential list to the trunk",
        )
        log("attached the credential list to the trunk")

    on_trunk = _ok(c.get(f"{TRUNKING_API}/Trunks/{trunk_sid}/PhoneNumbers"), "list the trunk's numbers")
    if not any(x.get("sid") == number_sid for x in on_trunk.get("phone_numbers", [])):
        _ok(
            c.post(f"{TRUNKING_API}/Trunks/{trunk_sid}/PhoneNumbers", data={"PhoneNumberSid": number_sid}),
            "attach the phone number to the trunk",
        )
        log(f"attached {cfg.phone_number} to the trunk")

    if country:
        update = json.dumps([{"iso_code": country.upper(), "low_risk_numbers_enabled": "true"}])
        _ok(
            c.post(f"{VOICE_API}/DialingPermissions/BulkCountryUpdates", data={"UpdateRequest": update}),
            "allow the country",
        )
        log(f"allowed outbound calls to {country.upper()} (low-risk numbers)")


async def setup_livekit(lk: Any, cfg: Config, *, log: Any = print) -> str:
    listed = await lk.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    current = next((t for t in listed.items if t.name == LIVEKIT_TRUNK_NAME), None)
    if current is None:
        info = await lk.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(
                trunk=api.SIPOutboundTrunkInfo(
                    name=LIVEKIT_TRUNK_NAME,
                    address=cfg.domain,
                    numbers=[cfg.phone_number],
                    auth_username=cfg.sip_username,
                    auth_password=cfg.sip_password,
                )
            )
        )
        log(f"created LiveKit outbound trunk {info.sip_trunk_id}")
        return str(info.sip_trunk_id)
    await lk.sip.update_outbound_trunk_fields(
        current.sip_trunk_id,
        address=cfg.domain,
        numbers=[cfg.phone_number],
        auth_username=cfg.sip_username,
        auth_password=cfg.sip_password,
    )
    log(f"updated LiveKit outbound trunk {current.sip_trunk_id}")
    return str(current.sip_trunk_id)


async def _livekit(cfg: Config) -> str:
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as http:
        lk = api.LiveKitAPI(cfg.livekit_url, cfg.livekit_key, cfg.livekit_secret, session=http)
        try:
            return await setup_livekit(lk, cfg)
        finally:
            await lk.aclose()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Connect a Twilio SIP trunk to LiveKit for outbound phone calls.")
    p.add_argument("--country", help="ISO code to allow outbound calls to, e.g. IN")
    p.add_argument("--env-file", default="../.env")
    p.add_argument("--dry-run", action="store_true", help="only check the settings and the Twilio account")
    args = p.parse_args(argv)
    try:
        cfg = load_config({**dotenv_values(args.env_file)})
        with httpx.Client(auth=(cfg.account_sid, cfg.auth_token), timeout=30) as c:
            if args.dry_run:
                acct = _ok(c.get(f"{TWILIO_API}/Accounts/{cfg.account_sid}.json"), "read the account")
                print(f"Twilio account OK ({acct.get('type')}); trunk domain would be {cfg.domain}")
                return 0
            setup_twilio(c, cfg, country=args.country)
        trunk_id = asyncio.run(_livekit(cfg))
    except SetupError as e:
        print(f"Setup stopped: {e}", file=sys.stderr)
        return 1
    print("\nDone. Set these (in .env, and on Railway for the backend):")
    print(f"SIP_OUTBOUND_TRUNK_ID={trunk_id}")
    print(f"SIP_AUTH_USERNAME={cfg.sip_username}")
    if cfg.password_generated:
        print(f"SIP_AUTH_PASSWORD={cfg.sip_password}   # generated now; keep it with the other secrets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
