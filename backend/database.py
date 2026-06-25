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
    LargeBinary,
    String,
    UniqueConstraint,
    create_engine,
    event,
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


if DATABASE_URL.startswith("sqlite"):
    # SQLite ignores ON DELETE CASCADE unless foreign keys are enabled per
    # connection. Turn them on so local dev matches PostgreSQL's enforcement.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    """A tenant. Each user account owns exactly one organization, whose name +
    Games-of-Chance ID appear on its raffle tickets."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(String, default="free", nullable=False)
    # NY/RIT raffle rules: the org's Games of Chance ID, printed on tickets
    # "if applicable". Optional — orgs without one just omit the line.
    goc_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(
        back_populates="org", cascade="all, delete-orphan", uselist=False
    )
    # passive_deletes lets the DB's ON DELETE CASCADE own the cascade rather
    # than SQLAlchemy emitting its own child DELETEs.
    raffles: Mapped[list["Raffle"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )


class User(Base):
    """A login identity. Created by self-signup (email+password or Google).
    Owns one organization. There are no API keys — all access is session-based.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # bcrypt hash; NULL for Google-only accounts that never set a password.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Google "sub" claim, set when the account is linked to Google sign-in.
    google_sub: Mapped[str | None] = mapped_column(String, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped["Organization"] = relationship(back_populates="user")


class PremiumEmail(Base):
    """Allowlist of emails granted the club (premium) plan. The platform admin
    manages this; membership is also unioned with the PREMIUM_EMAILS env list.
    """

    __tablename__ = "premium_emails"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Raffle(Base):
    __tablename__ = "raffles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    # Print-only raffle metadata required on the ticket face by NY/RIT rules.
    # Stored so each printed ticket can carry them; NOT payment/sale tracking.
    ticket_price: Mapped[str | None] = mapped_column(String, nullable=True)
    prizes: Mapped[str | None] = mapped_column(String, nullable=True)
    drawing_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    drawing_location: Mapped[str | None] = mapped_column(String, nullable=True)
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
        back_populates="raffle", cascade="all, delete-orphan", passive_deletes=True
    )
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="raffle", cascade="all, delete-orphan", passive_deletes=True
    )
    winners: Mapped[list["Winner"]] = relationship(
        back_populates="raffle", cascade="all, delete-orphan", passive_deletes=True
    )
    logos: Mapped[list["RaffleLogo"]] = relationship(
        back_populates="raffle",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RaffleLogo.position",
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
        back_populates="ticket",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
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
        back_populates="entry",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
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


class RaffleLogo(Base):
    """A logo printed on a raffle's tickets. A raffle can carry several (it may
    be co-hosted by multiple organizations), each optionally labeled."""

    __tablename__ = "raffle_logos"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    raffle_id: Mapped[str] = mapped_column(
        String, ForeignKey("raffles.id", ondelete="CASCADE"), nullable=False
    )
    # Optional label (e.g. the co-hosting organization's name).
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Normalized PNG bytes (SVGs are rasterized to PNG before upload).
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raffle: Mapped["Raffle"] = relationship(back_populates="logos")


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
