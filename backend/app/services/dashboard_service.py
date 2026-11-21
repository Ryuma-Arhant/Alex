"""The Dashboard: today's figures and recent activity for the user's agent, all read from stored calls, their summaries
and the reply timings the worker records. "Today" is the user's local day, as on the calls-per-day chart."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.db.models import Agent, AgentProfileVersion, Call, CallLink, CallSummary, CallTurn, NextActionDone
from app.services import stats_service
from app.services.agent_service import BUSY_WINDOW

RECENT_CALLS = 5


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)  # SQLite hands back naive UTC


def _when(call: Call) -> datetime:
    return _aware(call.started_at or call.created_at)


def _actions(summary: CallSummary | None) -> list[dict[str, Any]]:
    if summary is None:
        return []
    items = summary.summary_json.get("agent_commitments_and_next_actions") or []
    return [a for a in items if isinstance(a, dict)]


def _status(call: Call, now: datetime) -> str:
    if call.ended_at is None and _aware(call.created_at) > now - BUSY_WINDOW:
        return "live"
    return "summarising" if call.summary_status == "PENDING" else "done"


def _recent(call: Call, summary: CallSummary | None, fields: dict[str, Any], now: datetime) -> dict[str, Any]:
    borrower = fields.get("borrower") or {}
    s = summary.summary_json if summary is not None else {}
    length = None
    if call.started_at is not None and call.ended_at is not None:
        length = max(0, round((_aware(call.ended_at) - _aware(call.started_at)).total_seconds()))
    return {
        "call_id": str(call.id),
        "at": _when(call).isoformat(),
        "phone_last4": borrower.get("phone_last4"),
        "amount": borrower.get("amount"),
        "currency": borrower.get("currency"),
        "status": _status(call, now),
        "outcome": s.get("call_outcome"),
        "promise_to_pay": s.get("promise_to_pay"),  # absent on summaries written before it was recorded
        "escalation_needed": bool(s.get("escalation_needed", False)),
        "sentiment": s.get("sentiment") or None,
        "length_seconds": length,
    }


async def overview(
    s: AsyncSession, uid: uuid.UUID, agent: Agent | None, tz: ZoneInfo, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    today = stats_service.last_days(tz, now)[-1]
    out: dict[str, Any] = {
        "tz": tz.key,
        "today": today.isoformat(),
        "calls_today": 0,
        "promises": {"promised": 0, "of": 0},  # of = today's calls whose summary records promise_to_pay
        "reply_seconds": None,  # average time from the caller finishing to the agent starting to speak, today
        "replies": 0,
        "need_person": 0,  # today's calls whose summary says a person must follow up
        "recent_calls": [],
        "next_actions": [],  # from today's call summaries
    }
    if agent is None:
        return out

    base = (
        select(Call, CallSummary, AgentProfileVersion.structured_fields)
        .join(CallLink, CallLink.call_id == Call.id)
        .join(AgentProfileVersion, AgentProfileVersion.id == Call.profile_version_id)
        .outerjoin(CallSummary, CallSummary.call_id == Call.id)
        .where(CallLink.uid == uid, CallLink.agent_aid == agent.aid)
    )
    recent = (await s.execute(base.order_by(Call.created_at.desc()).limit(RECENT_CALLS))).all()
    out["recent_calls"] = [_recent(c, summ, fields or {}, now) for c, summ, fields in recent]

    since = datetime.combine(today, time.min, tzinfo=tz).astimezone(UTC) - timedelta(days=1)
    rows = (await s.execute(base.where(Call.created_at >= since).order_by(Call.created_at.desc()))).all()
    todays = [(c, summ) for c, summ, _ in rows if _when(c).astimezone(tz).date() == today]
    out["calls_today"] = len(todays)
    for _, summ in todays:
        if summ is None:
            continue
        promise = summ.summary_json.get("promise_to_pay")
        if isinstance(promise, bool):
            out["promises"]["of"] += 1
            out["promises"]["promised"] += int(promise)
        out["need_person"] += int(bool(summ.summary_json.get("escalation_needed")))

    ids = [c.id for c, _ in todays]
    if ids:
        metrics = await s.scalars(
            select(CallTurn.metrics_json).where(CallTurn.call_id.in_(ids), CallTurn.speaker == "agent")
        )
        replies = [
            float(m["e2e_latency"])
            for m in metrics
            if isinstance(m, dict) and isinstance(m.get("e2e_latency"), (int, float)) and m["e2e_latency"] > 0
        ]
        if replies:
            out["reply_seconds"] = round(sum(replies) / len(replies), 2)
            out["replies"] = len(replies)
        done = {
            (r.call_id, r.idx) for r in await s.scalars(select(NextActionDone).where(NextActionDone.call_id.in_(ids)))
        }
        for c, summ in todays:
            for i, a in enumerate(_actions(summ)):
                out["next_actions"].append(
                    {
                        "call_id": str(c.id),
                        "index": i,
                        "action": str(a.get("action") or "").strip(),
                        "owner": str(a.get("owner") or "").strip(),
                        "due": a.get("due_if_stated") or None,
                        "done": (c.id, i) in done,
                        "at": _when(c).isoformat(),
                    }
                )
        out["next_actions"] = [a for a in out["next_actions"] if a["action"]]
    return out


async def set_action_done(s: AsyncSession, uid: uuid.UUID, call_id: uuid.UUID, idx: int, done: bool) -> bool:
    """Ticks (or unticks) one next action of one of the user's own calls."""
    link = await s.get(CallLink, call_id)
    if link is None or link.uid != uid:
        raise NotFound("Call not found")
    summary = await s.scalar(select(CallSummary).where(CallSummary.call_id == call_id))
    if not 0 <= idx < len(_actions(summary)):
        raise NotFound("Next action not found")
    existing = await s.get(NextActionDone, (call_id, idx))
    if done and existing is None:
        s.add(NextActionDone(call_id=call_id, idx=idx, uid=uid))
    elif not done and existing is not None:
        await s.execute(delete(NextActionDone).where(NextActionDone.call_id == call_id, NextActionDone.idx == idx))
    await s.commit()
    return done
