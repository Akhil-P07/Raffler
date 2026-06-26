"""SQLAlchemy models and database initialization.

The schema mirrors the SQL in the spec exactly: organizations → raffles →
tickets → entries, plus an immutable winners table. UUIDs are stored as TEXT
so the same models work on PostgreSQL (production) and SQLite (local dev).
"""
import secrets
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
_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    _connect_args = {"connect_timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS}

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


def _invite_token() -> str:
    return secrets.token_urlsafe(24)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    """A tenant whose name + Games-of-Chance ID appear on its raffle tickets.
    Users join orgs through Membership rows — a user can belong to several."""

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

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    invites: Mapped[list["OrgInvite"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    # passive_deletes lets the DB's ON DELETE CASCADE own the cascade rather
    # than SQLAlchemy emitting its own child DELETEs.
    raffles: Mapped[list["Raffle"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )


class User(Base):
    """A login identity (email + optional password / Google). A user can belong
    to multiple organizations via Membership; the session token names which org
    is currently selected. There are no API keys — all access is session-based.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # bcrypt hash; NULL for Google-only accounts that never set a password.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Google "sub" claim, set when the account is linked to Google sign-in.
    google_sub: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Membership(Base):
    """A user's role in an organization. A user can have many; an org can have
    many. 'owner' can manage members; 'member' shares the org's raffles."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_membership"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, default="owner", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    org: Mapped["Organization"] = relationship(back_populates="memberships")


class OrgInvite(Base):
    """An email invited to join an organization. Accepting (via the emailed
    link) creates a Membership — a new account if the email has none yet, or an
    added org if it already does."""

    __tablename__ = "org_invites"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_invite"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Unguessable token in the emailed accept link.
    token: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, default=_invite_token
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped["Organization"] = relationship(back_populates="invites")


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
    # Full international phone number, E.164-style (e.g. "+1 5855551234").
    # Nullable so historical entries (and registrations without a phone) are fine.
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
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


def _add_missing_columns() -> None:
    """Tiny idempotent migration for additive columns (no Alembic in this app).
    Adds columns introduced after the table already existed, so deployed
    databases pick them up on the next startup. Safe to run every time."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "entries" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("entries")}
    if "phone" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE entries ADD COLUMN phone VARCHAR"))


def init_db() -> None:
    """Create tables if they do not exist. Called on app startup."""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
