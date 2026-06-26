# Raffler

A standalone, multi-tenant raffle **registration and draw** platform. Built for
RIT AI Club and designed to be licensed to other clubs. **No money ever touches
this platform** — ticket sales and payments are handled offline by the club.

- **Backend:** FastAPI · SQLAlchemy 2.0 · PostgreSQL (SQLite for local dev) ·
  `qrcode`/Pillow · `python-jose` (JWT) · `passlib`/bcrypt · `slowapi`
- **Frontend:** React · TypeScript · Vite · Axios · TailwindCSS
- **Hosting:** Railway (backend + frontend as separate services, one Postgres)

---

## How it works

```
BEFORE   Admin generates N tickets → downloads print sheet → prints tickets.
         Each ticket shows a human number AND an unguessable QR token.
AT EVENT Seller takes cash offline → hands over ticket → seller scans the QR
         in their logged-in portal → enters the buyer's name + email. The
         server confirms the ticket belongs to the seller's org first.
AFTER    Admin opens dashboard → Draw → winner selected with `secrets`,
         recorded immutably, shown with email to contact offline.
```

## Quick start (local, zero setup)

```bash
# Backend — defaults to a local SQLite file, no Postgres needed
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env          # then set SECRET_KEY — the app refuses the default
uvicorn main:app --reload
```

```bash
# Frontend — Vite proxies /api to the backend, so no CORS/env setup in dev
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Open http://localhost:5173 and **sign up** (email + password, or Google if
configured). Anyone can self-register into the **free tier**; emails on the
premium allowlist get the **club tier**.

> **Python note:** the pinned dependency versions are chosen to have prebuilt
> wheels on Python 3.12–3.14 (e.g. `psycopg` v3 instead of `psycopg2`,
> `bcrypt==4.3.0` for passlib compatibility). If you change Python versions and
> hit a build-from-source error, that's the place to look.

## Docker (full stack with Postgres)

```bash
docker compose up --build
# admin UI → http://localhost:5173 ; API → http://localhost:8000
```

---

## API reference

Auth is **session-based**: sign up (Google or email/password), then send the
returned token as `Authorization: Bearer <token>`. There are no API keys.
**Every** route below (including ticket registration) requires a session —
buyers never self-register; the logged-in seller registers each ticket.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/register` | Self-signup (email + password). Returns a session token. Free tier (or club if allowlisted). 10/min. |
| POST | `/auth/login` | Email + password → session token. 10/min. |
| GET | `/auth/google/login` | Returns the Google consent URL (`503` if Google isn't configured). |
| GET | `/auth/google/callback` | Google redirect target → redirects to the SPA with a session token. |
| GET | `/me` | Current account + org (plan, name, goc_id). |
| PATCH | `/org` | Update your org name / Games-of-Chance ID. |
| POST | `/auth/admin/login` | Super-admin login (manages the premium allowlist). |
| GET/POST | `/admin/premium` | List / add premium-allowlist emails (admin). |
| DELETE | `/admin/premium/{email}` | Remove an allowlisted email (admin). |
| POST | `/raffles` | Create raffle (enforces plan limit → 403). Optional ticket-face metadata. |
| GET | `/raffles` | List active raffles for your org. |
| GET | `/raffles/{id}` | Detail + entry/ticket counts. |
| PATCH | `/raffles/{id}` | Update name/status/metadata (409 if drawn). |
| DELETE | `/raffles/{id}` | Soft delete (sets `deleted_at`). |
| POST | `/raffles/{id}/tickets` | Generate N tickets + tokens (plan limit → 403). |
| GET | `/raffles/{id}/tickets` | List tickets. |
| GET | `/raffles/{id}/tickets/sheet` | PDF print sheet — 6 full-width tickets per A4 page (compliant ticket faces). |
| GET | `/tickets/{ticket_id}/qr` | Single-ticket QR PNG (ownership-checked). |
| POST | `/raffles/{id}/logos` | Upload a logo (multipart `file`, optional `name`). Max 6, ≤2 MB. |
| GET | `/raffles/{id}/logos` | List logo metadata (`id`, `name`, `position`). |
| GET | `/raffles/{id}/logos/{logo_id}` | Logo as `image/png`. |
| DELETE | `/raffles/{id}/logos/{logo_id}` | Remove a logo. |
| GET | `/register/{token}` | Seller scans a ticket: returns `owned` + (if owned) number/raffle/registered + registrant name/email/phone. |
| POST | `/register/{token}` | Seller registers the buyer (name + email + phone with country code). 403 if the ticket isn't the seller's org. |
| GET | `/raffles/{id}/entries` | List entries. |
| GET | `/raffles/{id}/entries/export` | CSV download. |
| POST | `/raffles/{id}/draw` | Draw winner(s). Idempotent. 5/min. |
| GET | `/raffles/{id}/winners` | Recorded winners. |

Interactive docs at `/docs` when the backend is running.

### Compliant raffle tickets (RIT / NY rules)

Printed tickets (the `/tickets/sheet` PDF) are **wide full-width strips** — 6 per
A4 page, separated with straight horizontal cuts to waste no paper. Each carries
the legally-required ticket face: the authorized organization name +
**Games-of-Chance ID** (`goc_id` on the org), the **drawing date/time/location**,
the consecutive **serial number** (on the body and both edges), the **ticket
price**, the **prize list**, the exact statement *"Ticket holders need not be
present to win."*, and a tear-off **stub** the seller keeps after the sale (with
its own QR plus Name / Address / Phone write-in rules). The QR (encoding the
unguessable registration token) is printed on both the body and the stub, so the
seller can scan it at point of sale to register the buyer.

These come from optional, **print-only** raffle fields (no payment/sale
tracking): `ticket_price`, `prizes`, `drawing_datetime`, `drawing_location` on
the raffle, and `goc_id` on the org. A raffle may carry up to 6 **logos** (it can
be co-hosted by several organizations); SVGs are rasterized to PNG by the web
uploader before upload.

---

## The three integrity rules (enforced, not documented)

1. **Seller-authenticated registration.** The QR encodes a 32-char
   `secrets.token_urlsafe` token (never the sequential number), validated for
   charset/length before any DB lookup. Registration is done by the **logged-in
   seller**, not the buyer: the server confirms the scanned ticket belongs to
   the seller's org before accepting an entry, and reports `owned: false` (no
   details) for another org's ticket. No public self-registration → no theft.
2. **Draws are final and verifiable.** A raffle draws once; re-calling returns
   the recorded winners (`already_drawn: true`) and never re-runs the RNG.
   Selection uses `secrets.SystemRandom` (not seedable). The raffle row is
   locked with `SELECT … FOR UPDATE` for the transaction, so concurrent draws
   can't race. `rng_seed` + `drawn_at` are recorded once.
3. **Strict org ownership.** Every ticket/entry/draw route resolves ownership by
   joining `ticket → raffle → org` (or `entry → raffle → org`) in a shared
   `middleware/ownership.py` dependency. Mismatches return **404**, not 403, so
   existence in another org's namespace can't be probed.

## Plan limits

| Plan | Raffles (lifetime) | Tickets per raffle |
|------|--------------------|--------------------|
| Free | 5 | 50 |
| Club | unlimited | unlimited |

The free raffle cap is a **lifetime** total — every raffle ever created counts,
including soft-deleted and already-drawn ones, so deleting one never frees a
slot. Over-limit → 403.

## Authentication & access control

- **Session-based, no API keys.** Login (Google or email/password) returns a
  signed JWT session token; org-scoped routes resolve the org from it via a
  single shared `require_org` dependency (404, not 403, on ownership misses).
- **Open free signup; premium by allowlist.** Anyone can self-register into the
  free tier. Emails in the `PREMIUM_EMAILS` env list — plus any added by the
  super-admin via `POST /admin/premium` — get the **club** plan, re-evaluated on
  every login so promote/demote takes effect on next sign-in.
- **Google OAuth** is optional (config-gated): the backend builds the consent
  URL with a signed CSRF state, exchanges the code server-side, and redirects
  the SPA back with a session token. If unconfigured, `/auth/google/*` returns
  `503` and email/password still works.
- Passwords are **bcrypt-hashed**; the super-admin uses constant-time
  credential comparison.

## Security highlights

- Per-IP rate limits via slowapi (login/signup/admin-login 10, draw 5,
  default 100 /min).
- Security headers on every response (CSP, `X-Frame-Options: DENY`, nosniff,
  Referrer-Policy). CORS pinned to the exact `FRONTEND_ORIGIN`.
- Pydantic validation on every body; `EmailStr`; name stripped + length-capped;
  UUID path params rejected before DB access.
- SQLAlchemy ORM throughout — no raw SQL string interpolation.
- Soft-delete on raffles; UI prompts to export CSV before destructive actions.

---

## Environment variables

See [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example). The backend **refuses to
start** if `SECRET_KEY` is shorter than 32 bytes.

## Deploy (Railway)

Two services + one Postgres plugin, in one project:

1. Add the **PostgreSQL** plugin; copy its `DATABASE_URL` to the backend service.
2. **Backend service** — root directory `backend/`. Start command (or Procfile):
   `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `SECRET_KEY` (generate
   with `python -c "import secrets; print(secrets.token_urlsafe(48))"`),
   `BASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FRONTEND_ORIGIN`, `API_ORIGIN`,
   `PREMIUM_EMAILS`, and (optional) `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` /
   `GOOGLE_REDIRECT_URI` (`https://yourapi.com/auth/google/callback`, which must
   match the Authorized Redirect URI in the Google Cloud console).
3. **Frontend service** — root directory `frontend/`. Build `npm run build`,
   start `npx serve -s dist -l $PORT`. Set build-time `VITE_API_BASE` and
   `VITE_BASE_URL` to the real domains.
4. Point `BASE_URL`/`FRONTEND_ORIGIN` (backend) and `VITE_*` (frontend) at the
   deployed domains so QR links and CORS line up.

Railway's free Postgres has no automated backups — **export entries to CSV after
registration closes and before any draw.**

## Tests

```bash
cd backend
pip install pytest httpx
pytest
```

## Out of scope (permanently)

Payment processing and price/sale tracking. Cash is always handled offline.
