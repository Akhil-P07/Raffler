"""SQLAlchemy models and database initialization.

The schema mirrors the SQL in the spec exactly: organizations → raffles →
tickets → entries, plus an immutable winners table. UUIDs are stored as TEXT
so the same models work on PostgreSQL (production) and SQLite (local dev).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from config import settings


def _normalize_db_url(url: str) -> str:
    # Railway hands out `postgres://`; SQLAlchemy 2.x needs `postgresql://`.
    # We also pin the psycopg (v3) driver explicitly, since that's what's in
    # requirements.txt — the bare `postgresql://` would default to psycopg2.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_db_url(settings.DATABASE_URL)

# check_same_thread is a SQLite-only knob; it would error on PostgreSQL.
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # bcrypt hash of the API key — the plaintext key is shown once at creation.
    api_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String, default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raffles: Mapped[list["Raffle"]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


class Raffle(Base):
    __tablename__ = "raffles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    rng_seed: Mapped[str | None] = mapped_column(String, nullable=True)
    drawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped["Organization"] = relationship(back_populates="raffles")
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="raffle", cascade="all, delete-orphan"
    )
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="raffle", cascade="all, delete-orphan"
    )
    winners: Mapped[list["Winner"]] = relationship(
        back_populates="raffle", cascade="all, delete-orphan"
    )


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # Human-readable ticket numbers are unique within a raffle, but the
        # same number can reappear in a different raffle (and across orgs).
        UniqueConstraint("raffle_id", "ticket_number", name="uq_ticket_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    raffle_id: Mapped[str] = mapped_column(
        String, ForeignKey("raffles.id", ondelete="CASCADE"), nullable=False
    )
    ticket_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Unguessable random string carried in the QR registration URL.
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raffle: Mapped["Raffle"] = relationship(back_populates="tickets")
    entry: Mapped["Entry | None"] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", uselist=False
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # One entry per ticket — UNIQUE enforces it at the database layer.
    ticket_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    raffle_id: Mapped[str] = mapped_column(
        String, ForeignKey("raffles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="entry")
    raffle: Mapped["Raffle"] = relationship(back_populates="entries")
    winner: Mapped["Winner | None"] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )


class Winner(Base):
    __tablename__ = "winners"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    raffle_id: Mapped[str] = mapped_column(
        String, ForeignKey("raffles.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(
        String, ForeignKey("entries.id", ondelete="CASCADE"), nullable=False
    )
    prize_rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    drawn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raffle: Mapped["Raffle"] = relationship(back_populates="winners")
    entry: Mapped["Entry"] = relationship(back_populates="winner")


def init_db() -> None:
    """Create tables if they do not exist. Called on app startup."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
