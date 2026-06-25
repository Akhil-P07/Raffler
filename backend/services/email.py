"""Sending the buyer their ticket PDF via the Brevo transactional email API.

Config-gated: if Brevo isn't configured (BREVO_API_KEY unset), `send_ticket_email`
is a no-op so registration still works without email. Failures are swallowed and
logged — emailing must never break registration.
"""
import base64
import logging

import httpx

from config import settings

logger = logging.getLogger("raffler.email")

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _send(payload: dict) -> None:
    """POST a Brevo email payload; swallow + log failures."""
    if not settings.email_enabled:
        return
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _BREVO_URL,
                json={
                    "sender": {
                        "email": settings.BREVO_SENDER_EMAIL,
                        "name": settings.BREVO_SENDER_NAME,
                    },
                    **payload,
                },
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
            )
        if resp.status_code >= 300:
            logger.warning("Brevo email failed: HTTP %s", resp.status_code)
    except Exception as exc:  # never break the request on a mail failure
        logger.warning("Brevo email error: %s", exc)


def send_invite_email(to_email: str, org_name: str, accept_url: str) -> None:
    """Email an organization invite with an accept link. No-op if unconfigured."""
    _send(
        {
            "to": [{"email": to_email}],
            "subject": f"You're invited to join {org_name} on Raffler",
            "htmlContent": (
                f"<p>You've been invited to join <b>{org_name}</b> on Raffler.</p>"
                f"<p><a href=\"{accept_url}\">Accept the invitation</a> to set a "
                f"password and join the team.</p>"
                f"<p>If you didn't expect this, you can ignore this email.</p>"
            ),
            "textContent": (
                f"You've been invited to join {org_name} on Raffler.\n\n"
                f"Accept here: {accept_url}\n\n"
                f"If you didn't expect this, ignore this email."
            ),
        }
    )


def send_ticket_email(
    to_email: str,
    buyer_name: str,
    raffle_name: str,
    ticket_number: int,
    pdf_bytes: bytes,
) -> None:
    """Email the buyer a PDF of their registered ticket via Brevo. No-op if
    Brevo is unconfigured. Intended to run in a background task."""
    _send(
        {
            "to": [{"email": to_email, "name": buyer_name}],
            "subject": f"Your raffle ticket #{ticket_number} — {raffle_name}",
            "textContent": (
                f"Hi {buyer_name},\n\n"
                f"You're registered for {raffle_name} with ticket #{ticket_number}. "
                f"Your ticket is attached as a PDF.\n\nGood luck!"
            ),
            "attachment": [
                {
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "name": f"ticket-{ticket_number}.pdf",
                }
            ],
        }
    )
