"""Bulk calling: the valid rows of an uploaded CSV become a job whose borrowers the user's agent phones one at a time.

A background loop (`run_forever`) calls `tick` every few seconds. Each tick first closes the item whose call has ended,
then, for running jobs, places the next call when the agent is free and no other bulk call is in progress (one call
at a time keeps the agent worker inside its memory limit). A borrower's full number is kept only until their call
ends; only its last four digits are ever returned.
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.db.models import Agent, BulkJob, BulkJobItem, Call, User
from app.services import agent_service, bulk_service, collections_service
from app.services.call_service import DIAL_FAILURES
from app.services.collections_prompt import BorrowerDetails

log = logging.getLogger("bulk")

ACTIVE = ("running", "paused")
STALE_CALL = timedelta(minutes=30)  # a call that never reported its end is treated as lost (as agent_service does)
MAX_CONCURRENT_CALLS = 1


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)  # SQLite hands back naive UTC


async def _items(s: AsyncSession, job_id: uuid.UUID) -> list[BulkJobItem]:
    return list(
        (await s.scalars(select(BulkJobItem).where(BulkJobItem.job_id == job_id).order_by(BulkJobItem.seq))).all()
    )


async def job_out(s: AsyncSession, job: BulkJob) -> dict[str, Any]:
    items = await _items(s, job.id)
    counts = {k: 0 for k in ("pending", "calling", "done", "skipped")}
    for i in items:
        counts[i.status] = counts.get(i.status, 0) + 1
    return {
        "job_id": str(job.id),
        "status": job.status,
        "file_name": job.file_name,
        "created_at": _aware(job.created_at).isoformat(),
        "total": len(items),
        "counts": counts,
        "answered": sum(1 for i in items if i.result == "answered"),
        "items": [
            {
                "seq": i.seq,
                "name": i.name,
                "phone_last4": i.phone_last4,
                "amount": i.amount,
                "currency": i.currency,
                "status": i.status,
                "result": i.result,
                "call_id": str(i.call_id) if i.call_id else None,
            }
            for i in items
        ],
    }


async def current(s: AsyncSession, uid: uuid.UUID) -> BulkJob | None:
    """The user's latest bulk run (active or finished)."""
    return await s.scalar(select(BulkJob).where(BulkJob.uid == uid).order_by(BulkJob.created_at.desc()).limit(1))


async def create_job(s: AsyncSession, settings: Settings, user: User, data: bytes, file_name: str) -> BulkJob:
    if not settings.phone_calls_enabled:
        raise Conflict("Phone calls are not set up yet.")
    agent = await agent_service.get_active(s, user.uid)
    if agent is None:
        raise Conflict("Create your agent before placing calls.")
    if await s.scalar(select(BulkJob.id).where(BulkJob.uid == user.uid, BulkJob.status.in_(ACTIVE))):
        raise Conflict("A bulk call is already in progress. Cancel it before starting another.")
    parsed = bulk_service.parse_csv(data)
    rows = [r for r in parsed["rows"] if r["valid"]]
    if not rows:
        raise bulk_service.BadCsv("The file has no rows that are ready to call.")
    job = BulkJob(id=uuid.uuid4(), uid=user.uid, agent_aid=agent.aid, file_name=file_name[:200], status="running")
    s.add(job)
    await s.flush()
    for n, r in enumerate(rows):
        s.add(
            BulkJobItem(
                job_id=job.id,
                seq=n,
                line=r["line"],
                name=r["name"],
                phone=r["phone"],
                phone_last4=r["phone"][-4:],
                amount=r["amount"],
                currency=r["currency"],
                deadline=date.fromisoformat(r["deadline"]) if r["deadline"] else None,
                lender=r["lender"],
                loan_reference=r["loan_reference"],
                notes=r["notes"],
            )
        )
    await s.commit()
    return job


async def _own_job(s: AsyncSession, uid: uuid.UUID, job_id: uuid.UUID) -> BulkJob:
    job = await s.get(BulkJob, job_id)
    if job is None or job.uid != uid:
        raise NotFound("Bulk call not found")
    return job


async def set_status(s: AsyncSession, uid: uuid.UUID, job_id: uuid.UUID, action: str) -> BulkJob:
    """pause: no new calls (a call in progress finishes); resume; cancel: everyone not yet called is skipped."""
    job = await _own_job(s, uid, job_id)
    allowed = {"pause": ("running",), "resume": ("paused",), "cancel": ACTIVE}[action]
    if job.status not in allowed:
        raise Conflict(f"This bulk call is {job.status}; it cannot be {action}d.")
    if action == "cancel":
        job.status = "cancelled"
        await _skip_pending(s, job.id, "cancelled")
    else:
        job.status = "paused" if action == "pause" else "running"
    await s.commit()
    return job


async def _skip_pending(s: AsyncSession, job_id: uuid.UUID, why: str) -> None:
    for i in await s.scalars(select(BulkJobItem).where(BulkJobItem.job_id == job_id, BulkJobItem.status == "pending")):
        i.status, i.result, i.phone = "skipped", why, None


def _borrower(i: BulkJobItem) -> BorrowerDetails:
    notes = f"Loan reference: {i.loan_reference}" if i.loan_reference else ""
    if i.notes:
        notes = f"{notes}\n{i.notes}".strip()
    assert i.phone is not None
    return BorrowerDetails(
        name=i.name,
        phone=i.phone,
        amount=Decimal(i.amount),
        bank=i.lender,
        currency=i.currency,
        due_date=i.deadline,
        notes=notes,
    )


async def _close_finished(s: AsyncSession, now: datetime) -> None:
    """The item whose call has ended (or was lost) is done; its result is why the call ended."""
    for item in await s.scalars(select(BulkJobItem).where(BulkJobItem.status == "calling")):
        call = await s.get(Call, item.call_id) if item.call_id else None
        lost = call is None or (call.ended_at is None and _aware(call.created_at) < now - STALE_CALL)
        if call is not None and call.ended_at is None and not lost:
            continue
        reason = call.end_reason if call is not None else None
        item.status, item.phone = "done", None
        item.result = reason if reason in DIAL_FAILURES else ("dial_failed" if lost else "answered")


async def _start_next(s: AsyncSession, settings: Settings, job: BulkJob) -> None:
    pending = await s.scalar(
        select(BulkJobItem)
        .where(BulkJobItem.job_id == job.id, BulkJobItem.status == "pending")
        .order_by(BulkJobItem.seq)
        .limit(1)
    )
    if pending is None:
        job.status = "done"
        return
    agent = await s.get(Agent, job.agent_aid)
    user = await s.get(User, job.uid)
    if agent is None or agent.lifecycle != "ACTIVE" or user is None:  # the agent was deleted mid-run
        job.status = "cancelled"
        await _skip_pending(s, job.id, "agent_gone")
        return
    if await agent_service.is_busy(s, agent):  # e.g. an individual call; try again on the next tick
        return
    pending.status = "calling"
    await s.commit()
    try:
        call, _ = await collections_service.call_borrower(s, settings, user, agent, _borrower(pending), phone=True)
    except AppError:  # dispatch failed; the call (if created) is already marked failed
        log.warning("bulk call could not be started", extra={"job_id": str(job.id), "seq": pending.seq})
        pending.status, pending.result, pending.phone = "done", "dial_failed", None
        return
    pending.call_id = call.id


async def tick(s: AsyncSession, settings: Settings, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    await _close_finished(s, now)
    await s.commit()
    if not settings.phone_calls_enabled:
        return
    for job in await s.scalars(select(BulkJob).where(BulkJob.status == "running").order_by(BulkJob.created_at)):
        calling = await s.scalar(select(func.count()).select_from(BulkJobItem).where(BulkJobItem.status == "calling"))
        if (calling or 0) >= MAX_CONCURRENT_CALLS:
            break
        await _start_next(s, settings, job)
        await s.commit()


async def run_forever(sm: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    while True:
        try:
            async with sm() as s:
                await tick(s, settings)
        except Exception:
            log.exception("bulk calling tick failed")
        await asyncio.sleep(settings.bulk_call_interval_seconds)
