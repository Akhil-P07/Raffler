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
AT EVENT Seller takes cash offline → hands over ticket → QR is scanned →
         buyer submits name + email → entry linked to that ticket's token.
AFTER    Admin opens dashboard → Draw → winner selected with `secrets`,
         recorded immutably, shown with email to contact offline.
```

## Quick start (local, zero setup)

```bash
# Backend — defaults to a local SQLite file, no Postgres needed
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
uvicorn main:app --reload
```

On first start with an empty database, the backend **seeds the founding org
"RIT AI Club" (Club plan)** and prints its API key **once** to the server log.
Copy that key — you'll paste it into the admin UI.

```bash
# Frontend — Vite proxies /api to the backend, so no CORS/env setup in dev
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Open http://localhost:5173, paste the seeded API key, and you're in.

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

All endpoints except `/register/{token}` require `X-API-Key: <your_key>`.
Admin/platform endpoints (`/orgs*`) require a JWT from `POST /auth/login`.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/login` | Admin JWT (15 min). Rate-limited 10/min. |
| POST | `/orgs` | Create org + return API key once (JWT). |
| POST | `/orgs/{org_id}/rotate-key` | Rotate API key (JWT). |
| POST | `/raffles` | Create raffle (enforces plan limit → 403). |
| GET | `/raffles` | List active raffles for your org. |
| GET | `/raffles/{id}` | Detail + entry/ticket counts. |
| PATCH | `/raffles/{id}` | Update name/status (409 if drawn). |
| DELETE | `/raffles/{id}` | Soft delete (sets `deleted_at`). |
| POST | `/raffles/{id}/tickets` | Generate N tickets + tokens (plan limit → 403). |
| GET | `/raffles/{id}/tickets` | List tickets. |
| GET | `/raffles/{id}/tickets/sheet` | PNG print sheet. |
| GET | `/tickets/{ticket_id}/qr` | Single-ticket QR PNG (ownership-checked). |
| GET | `/register/{token}` | **Public.** Token info (number + raffle name). |
| POST | `/register/{token}` | **Public.** Submit name + email. 20/min. |
| GET | `/raffles/{id}/entries` | List entries. |
| GET | `/raffles/{id}/entries/export` | CSV download. |
| POST | `/raffles/{id}/draw` | Draw winner(s). Idempotent. 5/min. |
| GET | `/raffles/{id}/winners` | Recorded winners. |

Interactive docs at `/docs` when the backend is running.

---

## The three integrity rules (enforced, not documented)

1. **Unguessable registration tokens.** The QR encodes a 32-char
   `secrets.token_urlsafe` token, never the sequential ticket number. The token
   path param is validated against its charset/length *before* any DB lookup.
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

| Plan | Active raffles | Tickets per raffle |
|------|----------------|--------------------|
| Free | 1 | 50 |
| Club | unlimited | unlimited |

"Active" = `status != 'drawn'` AND `deleted_at IS NULL`. Over-limit → 403.

## Security highlights

- API keys are **bcrypt-hashed**; the plaintext is shown once. Keys are
  `rk_<org_id>.<secret>` — the embedded org id gives an O(1) lookup so we never
  have to bcrypt-verify against every org (salted hashes aren't queryable).
- JWT admin auth (15 min), constant-time credential comparison on login.
- Per-IP rate limits via slowapi (login 10, register 20, draw 5, default 100 /min).
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
   `BASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FRONTEND_ORIGIN`, `API_ORIGIN`.
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
