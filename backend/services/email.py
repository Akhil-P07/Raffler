"""Sending emails via the Brevo transactional email API.

Config-gated: if Brevo isn't configured (BREVO_API_KEY unset), all send
functions are no-ops so registration/invite flows still work without email.
Failures are swallowed and logged — emailing must never break a request.
"""
import base64
import logging
from datetime import datetime

import httpx

from config import settings

logger = logging.getLogger("raffler.email")

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"

_BRAND = "#f76902"
_BRAND_LIGHT = "#fff7f2"
_BRAND_DARK = "#c95400"


def _fmt_date(dt: datetime) -> str:
    return f"{dt:%B} {dt.day}, {dt.year}"


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


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
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;max-width:600px;box-shadow:0 2px 8px rgba(0,0,0,.08)">

      <!-- Header -->
      <tr>
        <td style="background:{_BRAND};padding:28px 32px">
          <p style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px">You're invited to join</p>
          <p style="margin:6px 0 0;color:#ffe0cc;font-size:26px;font-weight:700">{org_name}</p>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:32px">
          <p style="margin:0 0 16px;color:#111111;font-size:16px;line-height:1.6">
            You've been invited to join <strong>{org_name}</strong> on Raffler as an admin.
            Accept below to set a password and start managing raffles.
          </p>

          <table width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0">
            <tr>
              <td align="center">
                <a href="{accept_url}"
                   style="display:inline-block;background:{_BRAND};color:#ffffff;padding:14px 36px;border-radius:8px;font-weight:700;font-size:16px;text-decoration:none;letter-spacing:0.2px">
                  Accept Invitation
                </a>
              </td>
            </tr>
          </table>

          <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.6">
            Or copy and paste this link into your browser:<br>
            <span style="color:{_BRAND_DARK};word-break:break-all">{accept_url}</span>
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 32px;text-align:center">
          <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.6">
            If you didn't expect this invitation you can safely ignore this email.<br>
            This invitation was sent to {to_email}.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body></html>"""

    _send(
        {
            "to": [{"email": to_email}],
            "subject": f"You're invited to join {org_name} on Raffler",
            "htmlContent": html,
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
    org_name: str = "",
    drawing_datetime: datetime | None = None,
    event_code: str | None = None,
) -> None:
    """Email the buyer a PDF of their registered ticket via Brevo. No-op if
    Brevo is unconfigured. Intended to run in a background task."""
    serial = f"#{event_code}-{ticket_number}" if event_code else f"#{ticket_number}"

    drawing_row = ""
    if drawing_datetime is not None:
        when = f"{_fmt_date(drawing_datetime)} at {_fmt_time(drawing_datetime)}"
        drawing_row = f"""
          <p style="margin:0 0 20px;color:#374151;font-size:14px;line-height:1.6">
            🗓&nbsp; Drawing: <strong>{when}</strong>
          </p>"""

    org_sub = (
        f'<p style="margin:6px 0 0;color:#ffe0cc;font-size:13px">{org_name}</p>'
        if org_name
        else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;max-width:600px;box-shadow:0 2px 8px rgba(0,0,0,.08)">

      <!-- Header -->
      <tr>
        <td style="background:{_BRAND};padding:28px 32px">
          <p style="margin:0;color:#ffffff;font-size:11px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase">Raffle Ticket Confirmation</p>
          <p style="margin:8px 0 0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.3px">{raffle_name}</p>
          {org_sub}
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:32px">
          <p style="margin:0 0 20px;color:#111111;font-size:16px;line-height:1.6">
            Hi <strong>{buyer_name}</strong>,
          </p>
          <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.7">
            You're all set — your ticket for <strong>{raffle_name}</strong> has been registered.
            Your ticket PDF is attached; keep it safe, you'll need it for the drawing.
          </p>

          <!-- Ticket number highlight -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
            <tr>
              <td style="background:{_BRAND_LIGHT};border:2px solid {_BRAND};border-radius:10px;padding:20px;text-align:center">
                <p style="margin:0 0 6px;color:#9ca3af;font-size:11px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase">Your Ticket Number</p>
                <p style="margin:0;color:{_BRAND};font-size:40px;font-weight:700;letter-spacing:-1px">{serial}</p>
              </td>
            </tr>
          </table>

          {drawing_row}

          <!-- Attachment callout -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
            <tr>
              <td style="background:#f9fafb;border-left:4px solid {_BRAND};border-radius:0 6px 6px 0;padding:14px 16px">
                <p style="margin:0;color:#374151;font-size:14px;line-height:1.6">
                  📎&nbsp; Your ticket is attached as <strong>ticket-{ticket_number}.pdf</strong>.
                  Open it to see your full ticket face with the registration QR code.
                </p>
              </td>
            </tr>
          </table>

          <p style="margin:0;color:#374151;font-size:15px;line-height:1.6">
            Good luck! 🍀
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 32px;text-align:center">
          <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.7">
            This ticket was registered by a verified seller on your behalf.<br>
            Ticket holders need not be present to win.<br>
            This email was sent to {to_email} because a ticket was registered using this address.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body></html>"""

    text = (
        f"Hi {buyer_name},\n\n"
        f"You're registered for {raffle_name} with ticket {serial}.\n"
        f"Your ticket is attached as a PDF.\n\n"
        f"Good luck!"
    )

    _send(
        {
            "to": [{"email": to_email, "name": buyer_name}],
            "subject": f"Your raffle ticket {serial} — {raffle_name}",
            "htmlContent": html,
            "textContent": text,
            "attachment": [
                {
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "name": f"ticket-{ticket_number}.pdf",
                }
            ],
        }
    )
