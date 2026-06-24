"""QR code generation (qrcode + Pillow).

Each ticket's QR encodes the public registration URL built from the
unguessable token — never the sequential ticket number. We expose helpers for
a single ticket PNG and for a printable sheet laying out every ticket with its
human-readable number beside its QR.
"""
import io

import qrcode
from PIL import Image, ImageDraw, ImageFont

from config import settings


def registration_url(token: str) -> str:
    base = settings.BASE_URL.rstrip("/")
    return f"{base}/register/{token}"


def _qr_image(token: str, box_size: int = 8, border: int = 2) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(registration_url(token))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def single_ticket_png(token: str) -> bytes:
    img = _qr_image(token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_font(size: int) -> ImageFont.ImageFont:
    # Fall back to the bundled bitmap font if no TrueType font is available
    # (Railway's slim image may not ship DejaVu).
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def print_sheet_png(
    tickets: list[tuple[int, str]], raffle_name: str, columns: int = 3
) -> bytes:
    """Lay out (ticket_number, token) pairs in a grid, each cell showing the
    QR above its printed number. Returns a single PNG of the whole sheet."""
    cell_w, cell_h = 240, 300
    pad = 20
    header_h = 70
    label_font = _load_font(22)
    title_font = _load_font(30)

    rows = (len(tickets) + columns - 1) // columns if tickets else 1
    sheet_w = columns * cell_w + pad * 2
    sheet_h = header_h + rows * cell_h + pad * 2

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, pad), raffle_name, fill="black", font=title_font)

    for idx, (number, token) in enumerate(tickets):
        col = idx % columns
        row = idx // columns
        cx = pad + col * cell_w
        cy = header_h + pad + row * cell_h

        qr = _qr_image(token, box_size=5, border=1).resize((200, 200))
        sheet.paste(qr, (cx + (cell_w - 200) // 2, cy))

        label = f"#{number}"
        bbox = draw.textbbox((0, 0), label, font=label_font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (cx + (cell_w - text_w) // 2, cy + 210),
            label,
            fill="black",
            font=label_font,
        )

    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()
