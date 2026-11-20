import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, utcnow


class User(Base, CreatedMixin):
    """A signed-in person. `workspace_id` ties them to the pre-existing call/profile data (1:1)."""

    __tablename__ = "users"
    uid: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # None for Google-only users
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), unique=True)


class Agent(Base, CreatedMixin):
    """A user's Loan-Recovery voice agent. At most one ACTIVE agent per user; deleting marks it DELETED so its past
    calls stay linked to it."""

    __tablename__ = "agents"
    __table_args__ = (
        Index(
            "uq_agents_one_active_per_user",
            "uid",
            unique=True,
            postgresql_where=text("lifecycle = 'ACTIVE'"),
            sqlite_where=text("lifecycle = 'ACTIVE'"),
        ),
    )
    aid: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uid: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.uid"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role_behavior: Mapped[str] = mapped_column(Text)  # the agent's role; always "Loan-Recovery Agent" today
    voice: Mapped[str] = mapped_column(String(10), default="male", server_default="male")  # male | female
    lifecycle: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE | DELETED
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_profiles.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CallLink(Base, CreatedMixin):
    """Says whose call this is (and which agent made it, if any) without touching the `calls` table."""

    __tablename__ = "call_links"
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.uid"), index=True)
    agent_aid: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.aid"), nullable=True, index=True)


class ScreenTimeDaily(Base):
    """Foreground seconds a user spent in the app on one local day. A running total only: no page or time history."""

    __tablename__ = "screen_time_daily"
    uid: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.uid"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_beat_at: Mapped[datetime | None] = mapped_column(nullable=True)  # caps credit to elapsed time
