import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdMixin, utcnow


class BulkJob(Base, IdMixin, CreatedMixin):
    """One bulk calling run: the valid rows of an uploaded CSV, called one at a time by the user's agent."""

    __tablename__ = "bulk_jobs"
    uid: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.uid"), index=True)
    agent_aid: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.aid"))
    file_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | paused | cancelled | done
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class BulkJobItem(Base, IdMixin):
    """One borrower of a bulk run. `phone` (full number) is kept only until their call ends."""

    __tablename__ = "bulk_job_items"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bulk_jobs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)  # calling order (the CSV's order)
    line: Mapped[int] = mapped_column(Integer)  # line in the CSV file
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_last4: Mapped[str] = mapped_column(String(4))
    amount: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    lender: Mapped[str] = mapped_column(String(80), default="")
    loan_reference: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | calling | done | skipped
    # done: answered | busy | no_answer | declined | invalid_number | dial_failed; skipped: cancelled | agent_gone
    result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    call_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("calls.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
