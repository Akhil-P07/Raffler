# Privacy Policy (TEMPLATE — do not use as-is)

_Last updated: 2026-06-26_

> **This file is a TEMPLATE, not a live policy.** Raffler is open-source
> software, and this is a starting-point privacy policy for an organization that
> **deploys** Raffler to run its own raffles. Replace every `[bracketed]` value,
> review it against the laws that apply to you (e.g. GDPR, US state privacy laws,
> your local games-of-chance / raffle rules), and publish your filled-in version
> to your users. **It is not legal advice.** (For reference, the live policy for
> the official deployment is in [`PRIVACY.md`](PRIVACY.md).)

This policy explains how **[Organization Name]** ("we", "us") collects and uses
personal information in our Raffler instance at **[https://your-domain]**.

For this deployment, the data controller is **[Organization Name]**, contactable
at **[privacy@your-domain]**.

## Who this covers

- **Raffle entrants ("buyers")** — people who buy a ticket and are registered.
- **Account holders ("sellers / organizers")** — people who log in to run
  raffles for an organization.

## What we collect and why

| Data | From whom | Why | Legal basis* |
|------|-----------|-----|--------------|
| Name, email, phone (incl. country code) | Buyers | Identify the entry, contact winners, and email the ticket | Contract / legitimate interest |
| Email + password (stored only as a bcrypt hash), or Google account ID and name | Account holders | Authenticate logins and control org access | Contract |
| Organization membership and role | Account holders | Permission management | Contract |
| Raffle, ticket, and entry records | Created in-app | Run and audit the draw | Contract / legal obligation (raffle rules) |

\* _Adjust the basis to your jurisdiction._

**We never collect or process payment data.** All ticket sales and cash are
handled offline by the organization; no card or bank details touch this system.

Buyer details are entered by the **logged-in seller** at the point of sale —
buyers do not self-register. Personal data is **not written to plaintext
application logs**.

## How it is stored and protected

- Data is stored in a SQLite database file on a private server volume hosted by
  **[hosting provider, e.g. Railway]**.
- Passwords are hashed with bcrypt; we never store them in plaintext.
- Access requires an authenticated session; each organization can only see its
  own raffles and entries. Traffic is served over HTTPS, and sensitive actions
  are rate-limited.

## Who can see your data

- The sellers and owners of the organization that registered the ticket.
- The instance operator / super-admin (technical administration).
- The sub-processors listed below.

## Sub-processors (third parties)

- **[Hosting provider, e.g. Railway]** — stores the database at rest.
- **Brevo** — sends transactional email (a buyer's ticket PDF and organization
  invitations). The recipient's name, email, and ticket are shared to deliver
  the message. _Only if email is enabled by the operator._
- **Google** — used for "Sign in with Google" (account holders only). _Only if
  Google login is enabled by the operator._

## Email you may receive

- **Buyers:** a PDF copy of your ticket when your ticket is registered.
- **Account holders:** organization invitations.

These are transactional (not marketing) messages tied to using the service.

## Data retention

We keep entry data only as long as needed to run and audit the raffle and to
meet any record-keeping required by raffle regulations, then delete it.
**[State your retention period, e.g. "we delete entry data within 90 days after
the drawing."]**

## Your rights

Depending on where you live, you may have the right to access, correct, export,
or delete your personal data, and to object to or restrict processing.

- Organizers can **export** entries to CSV and **deregister/remove** entries from
  the dashboard.
- To exercise any right, or to ask us to delete your data, contact
  **[privacy@your-domain]**. We will respond within **[e.g. 30 days]**.

## Children

This service is intended for adults running and entering raffles. Do not use it
to collect data from anyone below the age required by your local raffle laws.

## Changes

We may update this policy; material changes will be posted at this page with a
new "Last updated" date.

## Contact

**[Organization Name]** — **[privacy@your-domain]** — **[postal address, if
required by your jurisdiction]**.
