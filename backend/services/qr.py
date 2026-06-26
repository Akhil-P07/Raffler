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
    # Short per-raffle code; printed as the serial prefix #<event_code>-<number>.
    event_code: str | None = None
    goc_id: str | None = None
    prizes: str | None = None
    ticket_price: str | None = None
    drawing_datetime: datetime | None = None
    drawing_location: str | None = None
    # "Special information" / terms printed small on every ticket face.
    ticket_notes: str | None = None
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


# --- layout: a single WIDE ticket (full A4 width) -----------------------
# A wide strip so the print sheet stacks tickets vertically across the full
# page width — you separate them with straight horizontal cuts and waste no
# paper. Rendered at the exact width it prints at, so no scaling is needed.
_TW = 1180  # full A4 content width at 150 DPI (1240 page - 2*30 margin)
_TH = 270
_STUB_W = 240  # left tear-off stub (kept by the seller: serial + QR + write-in)
_SERIAL_W = 48  # right serial strip
_WRITE_IN = "_" * 24  # blank pen write-in fallback


def _decode_logos(raw_list: list[bytes], target_h: int) -> list[Image.Image]:
    """Decode stored logo bytes, scale to target_h tall, and flatten onto white
    (the ticket is white). Flattening means a transparent background renders as
    clean white — never a black box — and removes alpha-edge halos. Bad bytes
    are skipped rather than failing the whole ticket."""
    out: list[Image.Image] = []
    for raw in raw_list:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        if img.height != target_h:
            scale = target_h / img.height
            img = img.resize(
                (max(1, int(img.width * scale)), target_h), Image.LANCZOS
            )
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        out.append(Image.alpha_composite(bg, img).convert("RGB"))
    return out


def render_ticket(
    number: int, token: str, info: TicketSheetInfo, logos: list[Image.Image],
    show_write_in: bool = True,
) -> Image.Image:
    """Render one legally-compliant raffle ticket as a WIDE full-width strip:

    - Left tear-off STUB (the seller keeps it after the sale): serial, a QR of
      the same registration token, and Name / Address / Phone write-in rules.
    - BODY: logo (top-left), title (centred), price (top-right), a full-width
      prize line, the drawing details + an (uncaptioned) registration QR along
      the bottom, and the 'need not be present' statement.
    - Right serial strip.
    """
    img = Image.new("RGB", (_TW, _TH), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, _TW - 1, _TH - 1], outline="black", width=3)

    body_x0 = _STUB_W
    body_x1 = _TW - _SERIAL_W

    f_stub = _load_font(14)
    f_org = _load_font(23, bold=True)
    f_goc = _load_font(12)
    f_title = _load_font(32, bold=True)
    f_sub = _load_font(17)
    f_label = _load_font(15, bold=True)
    f_body = _load_font(15)
    f_price = _load_font(30, bold=True)
    f_stmt = _load_font(14, bold=True)
    f_serial = _load_font(17, bold=True)

    qr_full = _qr_image(token, box_size=4, border=1)
    # Serial: #<event_code>-<number> (e.g. #SG01-7), falling back to #<number>
    # if the raffle predates event codes.
    serial = f"#{info.event_code}-{number}" if info.event_code else f"#{number}"

    # Perforation (dashed) separating stub | body | serial strip.
    for px in (body_x0, body_x1):
        for yy in range(6, _TH - 6, 11):
            draw.line([px, yy, px, yy + 5], fill="black", width=1)

    # --- left stub (seller keeps): serial, QR, write-in rules ---
    sw0 = draw.textlength(serial, font=f_serial)
    draw.text(((_STUB_W - sw0) / 2, 10), serial, font=f_serial, fill="black")
    sq = 78
    img.paste(qr_full.resize((sq, sq)), ((_STUB_W - sq) // 2, 32))
    if show_write_in:
        wy = 32 + sq + 12
        for label in ("Name:", "Address:", "Phone:"):
            draw.text((14, wy), label, font=f_stub, fill="black")
            lx = 14 + draw.textlength(label + " ", font=f_stub)
            rule_y = wy + f_stub.size
            draw.line([lx, rule_y, _STUB_W - 12, rule_y], fill="black", width=1)
            wy += f_stub.size + 16

    # --- right serial strip (vertical) ---
    v = _vertical_text(serial, f_serial)
    img.paste(v, (body_x1 + (_SERIAL_W - v.width) // 2, (_TH - v.height) // 2), v)

    # --- body: use the full width ---
    pad = 18
    bx = body_x0 + pad
    bw = body_x1 - body_x0 - 2 * pad

    def centered(text: str, font, y: int) -> int:
        w = draw.textlength(text, font=font)
        draw.text((body_x0 + (body_x1 - body_x0 - w) / 2, y), text, font=font, fill="black")
        return y + font.size + 4

    # Logo(s) top-left.
    logo_bottom = 12
    if logos:
        lx, ly = bx, 12
        for im in logos:
            img.paste(im, (lx, ly))
            lx += im.width + 12
        logo_bottom = ly + logos[0].height

    # Price top-right, large.
    price = _price_text(info.ticket_price)
    if price:
        pw = draw.textlength(price, font=f_price)
        draw.text((body_x1 - pad - pw, 14), price, font=f_price, fill="black")

    # Title block, centred.
    hy = 10
    hy = centered(info.org_name, f_org, hy)
    if info.goc_id:
        hy = centered(f"GOC ID {info.goc_id}", f_goc, hy)
    hy = centered("RAFFLE", f_title, hy + 1)
    hy = centered(info.raffle_name, f_sub, hy)

    # Prize line — full width, directly under the header (above the QR).
    py = max(hy, logo_bottom) + 8
    draw.text((bx, py), "Enter to win:", font=f_label, fill="black")
    label_w = draw.textlength("Enter to win:  ", font=f_label)
    prize_lines = _wrap(draw, info.prizes or _WRITE_IN, f_body, bw - label_w)
    if prize_lines:
        draw.text((bx + label_w, py + 1), prize_lines[0], font=f_body, fill="black")
    py += f_label.size + 8

    # Registration QR — bottom-right. No caption: only the org/admin scans it
    # (to register the buyer), so the ticket carries no "scan" prompt to buyers.
    bq = 92
    bq_x = body_x1 - bq - pad
    bq_y = _TH - bq - 28
    img.paste(qr_full.resize((bq, bq)), (bq_x, bq_y))

    # Drawing details — bottom-left, filling the width up to the QR.
    dy = py + 2
    draw_w = bq_x - bx - 20
    draw.text((bx, dy), "Drawing held:", font=f_label, fill="black")
    dy += f_label.size + 4
    when = (
        f"{_format_date(info.drawing_datetime)} · {_format_time(info.drawing_datetime)}"
        if info.drawing_datetime is not None
        else _WRITE_IN
    )
    for line in _wrap(draw, when, f_body, draw_w)[:1]:
        draw.text((bx, dy), line, font=f_body, fill="black")
        dy += f_body.size + 4
    if info.drawing_location:
        for line in _wrap(draw, info.drawing_location, f_body, draw_w)[:1]:
            draw.text((bx, dy), line, font=f_body, fill="black")
            dy += f_body.size + 4

    statement_y = _TH - f_stmt.size - 12

    # Special-information / terms — small print, between the drawing details and
    # the statement. Wraps to the width up to the QR; only draws lines that fit
    # above the statement so it never overlaps.
    if info.ticket_notes:
        f_note = _load_font(13)
        ny = dy + 3
        for line in _wrap(draw, info.ticket_notes, f_note, draw_w):
            if ny + f_note.size > statement_y - 2:
                break
            draw.text((bx, ny), line, font=f_note, fill="black")
            ny += f_note.size + 2

    # "Need not be present" statement — bottom-left.
    draw.text((bx, statement_y), NOT_PRESENT_STATEMENT, font=f_stmt, fill="black")

    return img


def single_ticket_full_png(number: int, token: str, info: TicketSheetInfo) -> bytes:
    """One full ticket as PNG (used by the admin on-screen preview)."""
    logos = _decode_logos(info.logos, target_h=40)
    buf = io.BytesIO()
    render_ticket(number, token, info, logos).save(buf, format="PNG")
    return buf.getvalue()


def single_ticket_pdf(number: int, token: str, info: TicketSheetInfo) -> bytes:
    """One full ticket as a single-page PDF (emailed to the buyer)."""
    logos = _decode_logos(info.logos, target_h=40)
    buf = io.BytesIO()
    render_ticket(number, token, info, logos, show_write_in=False).save(
        buf, format="PDF", resolution=150.0
    )
    return buf.getvalue()


# --- A4 print sheet (multi-page PDF) -------------------------------------
# A4 at 150 DPI. Wide tickets are stacked one per row at full page width, so
# they're separated with straight horizontal cuts and waste no paper.
_A4_W, _A4_H = 1240, 1754
_SHEET_MARGIN_Y, _ROW_GAP = 24, 10


def print_sheet_pdf(tickets: list[tuple[int, str]], info: TicketSheetInfo) -> bytes:
    """Stack full-width tickets vertically on A4 pages; return a multi-page PDF
    ready for bulk printing (cut horizontally between tickets)."""
    logos = _decode_logos(info.logos, target_h=40)

    x = (_A4_W - _TW) // 2  # center the full-width ticket horizontally
    per_page = max(
        1, (_A4_H - 2 * _SHEET_MARGIN_Y + _ROW_GAP) // (_TH + _ROW_GAP)
    )

    pages: list[Image.Image] = []
    page = None
    for idx, (number, token) in enumerate(tickets):
        slot = idx % per_page
        if slot == 0:
            page = Image.new("RGB", (_A4_W, _A4_H), "white")
            pages.append(page)
        y = _SHEET_MARGIN_Y + slot * (_TH + _ROW_GAP)
        page.paste(render_ticket(number, token, info, logos), (x, y))

    if not pages:
        pages.append(Image.new("RGB", (_A4_W, _A4_H), "white"))

    buf = io.BytesIO()
    pages[0].save(
        buf,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=150.0,
    )
    return buf.getvalue()
