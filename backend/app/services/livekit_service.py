"""Token minting and room control. Tokens are short-lived with minimal grants."""

import json
import ssl
import uuid
from datetime import timedelta

import aiohttp
import certifi
from livekit import api

from app.core.config import Settings


def new_room_name() -> str:
    return f"call-{uuid.uuid4().hex[:16]}"


def _dispatch_metadata(call_id: uuid.UUID, correlation_id: str) -> str:
    return json.dumps({"call_id": str(call_id), "correlation_id": correlation_id})


def mint_participant_token(
    settings: Settings, *, room: str, identity: str, call_id: uuid.UUID, correlation_id: str
) -> str:
    """Browser token. Joining this room triggers explicit dispatch of our named agent."""
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(seconds=settings.token_ttl_seconds))
        .with_grants(
            api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=True)
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=settings.agent_name, metadata=_dispatch_metadata(call_id, correlation_id)
                    )
                ],
                empty_timeout=60,
                departure_timeout=20,
            )
        )
        .to_jwt()
    )


def mint_listener_token(settings: Settings, *, room: str, identity: str) -> str:
    """Browser token for following a phone call: hears both sides and receives the transcript, but cannot publish
    (the agent must only hear the borrower) and does not dispatch an agent (the backend already did)."""
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(seconds=settings.token_ttl_seconds))
        .with_grants(
            api.VideoGrants(room_join=True, room=room, can_publish=False, can_subscribe=True, can_publish_data=False)
        )
        .to_jwt()
    )


def _ssl_context() -> ssl.SSLContext:
    """certifi's CA bundle: python.org builds of Python on macOS ship without a system trust store, so the default
    context cannot verify LiveKit Cloud's certificate (the agent worker applies the same fix to itself)."""
    return ssl.create_default_context(cafile=certifi.where())


async def close_room(settings: Settings, room: str) -> None:
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=_ssl_context())) as http:
        lk = api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret, session=http)
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room))
        finally:
            await lk.aclose()


async def dispatch_agent(settings: Settings, *, room: str, call_id: uuid.UUID, correlation_id: str) -> None:
    """Phone calls: create the room and send our agent into it now (no browser joins to trigger the dispatch). The
    agent then dials the borrower itself."""
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=_ssl_context())) as http:
        lk = api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret, session=http)
        try:
            await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=60, departure_timeout=20))
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=settings.agent_name, room=room, metadata=_dispatch_metadata(call_id, correlation_id)
                )
            )
        finally:
            await lk.aclose()
