"""QR generation + legally-compliant raffle ticket rendering (qrcode + Pillow).

The printed ticket follows the RIT / NY "Raffle Rules and Approval Process"
ticket-face requirements:
  (i)   organization name + Games-of-Chance ID (if applicable)
  (ii)  drawing location / date / time
  (iii) consecutive serial number (printed on body + both stubs)
  (iv)  ticket price
  (v)   list of prizes
  (vi)  the statement "Ticket holders need not be present to win."
  (vii) a tear-off stub with blank Name / Address / Phone write-in lines

The QR (encoding the unguessable registration token, never the serial number)
is an addition on top of the legal layout: the seller scans it at point of
sale to register the buyer's details on the website.
"""
import io
from dataclasses import dataclass, field
from datetime import datetime

import qrcode
from PIL import Image, ImageDraw, ImageFont

from config import settings

NOT_PRESENT_STATEMENT = "Ticket holders need not be present to win."

# Cap decoded logo dimensions well below Pillow's ~89 Mpx default so a tiny,
# highly-compressed "decompression bomb" can't expand to gigabytes of RAM.
# Logos are downscaled to <=400px anyway; 25 Mpx (~5000x5000) is plenty.
Image.MAX_IMAGE_PIXELS = 25_000_000


@dataclass
class TicketSheetInfo:
    """Everything the ticket face needs that isn't per-ticket."""

    org_name: str
    raffle_name: str
    goc_id: str | None = None
    prizes: str | None = None
    ticket_price: str | None = None
    drawing_datetime: datetime | None = None
    drawing_location: str | None = None
    # Normalized PNG bytes for each co-hosting org logo, printed in a top row.
    logos: list[bytes] = field(default_factory=list)


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


def _looks_like_svg(raw: bytes) -> bool:
    head = raw[:512].lstrip().lower()
    return head.startswith(b"<?xml") and b"<svg" in raw[:1024].lower() or head.startswith(
        b"<svg"
    )


def _svg_to_png(raw: bytes, max_side: int) -> bytes:
    """Best-effort server-side SVG rasterization. Our web uploader rasterizes
    SVGs in the browser, so this is only the path for direct API callers. It
    uses cairosvg if it's importable (e.g. in a deployment with libcairo);
    otherwise we ask the caller to send a raster image."""
    try:
        import cairosvg  # type: ignore
    except (ImportError, OSError) as exc:
        raise ValueError(
            "SVG logos must be uploaded through the web app (which converts "
            "them automatically) or sent as PNG/JPG when calling the API "
            "directly."
        ) from exc
    return cairosvg.svg2png(bytestring=raw, output_width=max_side)


def normalize_logo(raw: bytes, max_side: int = 400) -> bytes:
    """Validate and normalize an uploaded logo to PNG, downscaled so the
    longest side is <= max_side. Raises ValueError if it isn't a valid image.
    Transparency is preserved (RGBA)."""
    if _looks_like_svg(raw):
        raw = _svg_to_png(raw, max_side)
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Image.DecompressionBombError as exc:
        raise ValueError("Image dimensions are too large") from exc
    except Exception as exc:  # Pillow raises various types on bad input
        raise ValueError("Not a valid image file") from exc

    img = img.convert("RGBA")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """A scalable font. Tries DejaVu, then Pillow's bundled default (which is
    scalable via the size arg on Pillow >= 10) so tickets render legibly even
    on a slim image without system fonts."""
    candidates = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf"]
        if bold
        else ["DejaVuSans.ttf", "arial.ttf"]
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _price_text(price: str | None) -> str | None:
    if not price:
        return None
    price = price.strip()
    return price if price.startswith("$") else f"${price}"


def _format_date(dt: datetime) -> str:
    # Avoid %-d / %#d (platform-specific); build the day without a leading zero.
    return f"{dt:%B} {dt.day}, {dt.year}"


def _format_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines() or [text]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_w:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _vertical_text(text: str, font) -> Image.Image:
    """Render `text` rotated 90° (reads bottom-to-top), transparent background."""
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("RGBA", (w + 4, h + 6), (255, 255, 255, 0))
    ImageDraw.Draw(img).text((2, 2 - bbox[1]), text, font=font, fill="black")
    return img.rotate(90, expand=True)


# --- layout constants -----------------------------------------------------
_W, _H = 940, 300
_MARGIN, _GAP = 24, 26
_STUB_W, _SERIAL_W = 150, 56
_WRITE_IN = "_" * 22  # blank pen write-in line in the stub
_LOGO_BAND = 70  # extra body height reserved for the logo row when present
_LOGO_H = 48  # rendered logo height in the band


def _decode_logos(raw_list: list[bytes]) -> list[Image.Image]:
    """Decode stored PNG logo bytes into RGBA images scaled to _LOGO_H tall.
    Bad bytes are skipped rather than failing the whole sheet."""
    out: list[Image.Image] = []
    for raw in raw_list:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        if img.height != _LOGO_H:
            scale = _LOGO_H / img.height
            img = img.resize((max(1, int(img.width * scale)), _LOGO_H))
        out.append(img)
    return out


def _draw_ticket(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    h: int,
    number: int,
    token: str,
    info: TicketSheetInfo,
    logos: list[Image.Image],
) -> None:
    f_stub = _load_font(15)
    f_org = _load_font(22, bold=True)
    f_goc = _load_font(13)
    f_title = _load_font(30, bold=True)
    f_sub = _load_font(16)
    f_label = _load_font(14, bold=True)
    f_body = _load_font(16)
    f_price = _load_font(24, bold=True)
    f_stmt = _load_font(15, bold=True)
    f_serial = _load_font(17, bold=True)

    # Outer border.
    draw.rectangle([ox, oy, ox + _W, oy + h], outline="black", width=2)

    body_x0 = ox + _STUB_W
    body_x1 = ox + _W - _SERIAL_W

    # Perforation lines (stub | body | serial).
    for px in (body_x0, body_x1):
        for yy in range(oy + 6, oy + h - 6, 10):
            draw.line([px, yy, px, yy + 5], fill="black", width=1)

    # --- left stub: serial + blank write-in columns (filled by hand) ---
    serial = f"Ticket #{number}"
    stub_cols = [serial, f"Name: {_WRITE_IN}", f"Address: {_WRITE_IN}", f"Phone: {_WRITE_IN}"]
    col_w = _STUB_W // len(stub_cols)
    for i, txt in enumerate(stub_cols):
        v = _vertical_text(txt, f_stub)
        cx = ox + i * col_w + (col_w - v.width) // 2
        cy = oy + (h - v.height) // 2
        sheet.paste(v, (cx, max(oy + 6, cy)), v)

    # --- right strip: serial number repeated (vertical) ---
    v = _vertical_text(serial, f_serial)
    sheet.paste(
        v,
        (body_x1 + (_SERIAL_W - v.width) // 2, oy + (h - v.height) // 2),
        v,
    )

    # --- body ---
    bx = body_x0 + 16
    bw = body_x1 - body_x0 - 32

    # Logo row (co-hosting orgs), centered across the top of the body.
    if logos:
        gap = 18
        total_w = sum(im.width for im in logos) + gap * (len(logos) - 1)
        lx = body_x0 + (body_x1 - body_x0 - total_w) // 2
        ly = oy + (_LOGO_BAND - _LOGO_H) // 2
        for im in logos:
            sheet.paste(im, (max(body_x0 + 4, lx), ly), im)
            lx += im.width + gap
        cy = oy + _LOGO_BAND
    else:
        cy = oy + 14

    def centered(text: str, font, y: int, fill: str = "black") -> int:
        w = draw.textlength(text, font=font)
        draw.text((body_x0 + (body_x1 - body_x0 - w) / 2, y), text, font=font, fill=fill)
        return y + (font.size + 6)

    cy = centered(info.org_name, f_org, cy)
    if info.goc_id:
        cy = centered(
            f"*Games of Chance Identification Number {info.goc_id}", f_goc, cy
        )
    cy = centered("RAFFLE", f_title, cy + 2)
    cy = centered(info.raffle_name, f_sub, cy)

    # Two columns: prizes (left) and drawing details (right).
    col_y = cy + 10
    left_w = int(bw * 0.5)
    right_x = bx + left_w + 16

    # Prizes (left)
    py = col_y
    draw.text((bx, py), "Enter to win:", font=f_label, fill="black")
    py += f_label.size + 4
    prize_lines = _wrap(draw, info.prizes or _WRITE_IN, f_body, left_w)
    for line in prize_lines[:3]:
        draw.text((bx, py), line, font=f_body, fill="black")
        py += f_body.size + 3

    # Drawing details (right)
    dy = col_y
    draw.text((right_x, dy), "Drawing held:", font=f_label, fill="black")
    dy += f_label.size + 4
    if info.drawing_datetime is not None:
        draw.text((right_x, dy), _format_date(info.drawing_datetime), font=f_body, fill="black")
        dy += f_body.size + 3
        draw.text((right_x, dy), _format_time(info.drawing_datetime), font=f_body, fill="black")
        dy += f_body.size + 3
    else:
        draw.text((right_x, dy), _WRITE_IN, font=f_body, fill="black")
        dy += f_body.size + 3
    if info.drawing_location:
        for line in _wrap(draw, info.drawing_location, f_body, bw - left_w - 16)[:2]:
            draw.text((right_x, dy), line, font=f_body, fill="black")
            dy += f_body.size + 3

    # Price (right-aligned, upper area)
    price = _price_text(info.ticket_price)
    if price:
        pw = draw.textlength(price, font=f_price)
        draw.text((body_x1 - 16 - pw, col_y - 2), price, font=f_price, fill="black")

    # QR (bottom-left of body) + caption
    qr = _qr_image(token, box_size=4, border=1).resize((96, 96))
    qy = oy + h - 96 - 12
    sheet.paste(qr, (bx, qy))
    draw.text((bx + 100, qy + 34), "Scan to register", font=f_body, fill="black")

    # "Need not be present" statement (bottom, centered in body)
    sw = draw.textlength(NOT_PRESENT_STATEMENT, font=f_stmt)
    draw.text(
        (body_x0 + (body_x1 - body_x0 - sw) / 2, oy + h - f_stmt.size - 12),
        NOT_PRESENT_STATEMENT,
        font=f_stmt,
        fill="black",
    )


def print_sheet_png(tickets: list[tuple[int, str]], info: TicketSheetInfo) -> bytes:
    """Render every (ticket_number, token) as a full compliant ticket, stacked
    one per row. Returns a single PNG of the whole sheet."""
    logos = _decode_logos(info.logos)
    ticket_h = _H + (_LOGO_BAND if logos else 0)

    count = max(len(tickets), 1)
    sheet_w = _W + _MARGIN * 2
    sheet_h = _MARGIN * 2 + count * ticket_h + (count - 1) * _GAP

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)

    for idx, (number, token) in enumerate(tickets):
        oy = _MARGIN + idx * (ticket_h + _GAP)
        _draw_ticket(sheet, draw, _MARGIN, oy, ticket_h, number, token, info, logos)

    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()
