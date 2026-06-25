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


# --- layout: a single ~10:11 ticket -------------------------------------
# The ticket is rendered once at a fixed resolution, then scaled to fit the
# A4 print grid (or shown as-is in the admin preview), so the on-screen view
# matches the print exactly.
_TW = 620
_TH = round(_TW * 11 / 10)  # 10:11 width:height
_WRITE_IN = "_" * 26  # blank pen write-in line in the stub


def _decode_logos(raw_list: list[bytes], target_h: int) -> list[Image.Image]:
    """Decode stored PNG logo bytes into RGBA images scaled to target_h tall.
    Bad bytes are skipped rather than failing the whole ticket."""
    out: list[Image.Image] = []
    for raw in raw_list:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        if img.height != target_h:
            scale = target_h / img.height
            img = img.resize((max(1, int(img.width * scale)), target_h))
        out.append(img)
    return out


def render_ticket(
    number: int, token: str, info: TicketSheetInfo, logos: list[Image.Image]
) -> Image.Image:
    """Render one legally-compliant raffle ticket as a ~10:11 RGB image:
    logo row → org + GOC id → RAFFLE → prize → drawing → price → QR →
    'need not be present' statement → perforation → tear-off stub (serial +
    blank Name/Address/Phone write-in lines)."""
    img = Image.new("RGB", (_TW, _TH), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, _TW - 1, _TH - 1], outline="black", width=3)

    pad = 22
    cw = _TW - 2 * pad  # content width
    cy = pad

    f_org = _load_font(28, bold=True)
    f_goc = _load_font(14)
    f_title = _load_font(44, bold=True)
    f_sub = _load_font(19)
    f_label = _load_font(16, bold=True)
    f_body = _load_font(18)
    f_price = _load_font(26, bold=True)
    f_stmt = _load_font(15, bold=True)
    f_serial = _load_font(22, bold=True)
    f_stub = _load_font(17)

    def centered(text: str, font, y: int, fill: str = "black") -> int:
        w = draw.textlength(text, font=font)
        draw.text(((_TW - w) / 2, y), text, font=font, fill=fill)
        return y + font.size + 7

    def left(text: str, font, y: int) -> int:
        draw.text((pad, y), text, font=font, fill="black")
        return y + font.size + 5

    # Logo row (co-hosting organizations).
    if logos:
        gap = 18
        total = sum(im.width for im in logos) + gap * (len(logos) - 1)
        lx = max(pad, (_TW - total) // 2)
        for im in logos:
            img.paste(im, (lx, cy), im)
            lx += im.width + gap
        cy += (logos[0].height if logos else 0) + 10

    cy = centered(info.org_name, f_org, cy)
    if info.goc_id:
        cy = centered(f"GOC ID {info.goc_id}", f_goc, cy)
    cy = centered("RAFFLE", f_title, cy + 4)
    cy = centered(info.raffle_name, f_sub, cy)
    cy += 6

    # Prize.
    cy = left("Enter to win:", f_label, cy)
    for line in _wrap(draw, info.prizes or _WRITE_IN, f_body, cw)[:2]:
        cy = left(line, f_body, cy)
    cy += 4

    # Drawing details + price on the same band.
    price = _price_text(info.ticket_price)
    if price:
        pw = draw.textlength(price, font=f_price)
        draw.text((_TW - pad - pw, cy), price, font=f_price, fill="black")
    cy = left("Drawing held:", f_label, cy)
    if info.drawing_datetime is not None:
        when = f"{_format_date(info.drawing_datetime)} · {_format_time(info.drawing_datetime)}"
    else:
        when = _WRITE_IN
    cy = left(when, f_body, cy)
    if info.drawing_location:
        for line in _wrap(draw, info.drawing_location, f_body, cw)[:1]:
            cy = left(line, f_body, cy)

    # QR (centered) + caption.
    qr_size = 150
    qr = _qr_image(token, box_size=5, border=1).resize((qr_size, qr_size))
    img.paste(qr, ((_TW - qr_size) // 2, cy + 4))
    cy += qr_size + 8
    cy = centered("Scan to register", f_body, cy)

    # "Need not be present" statement.
    centered(NOT_PRESENT_STATEMENT, f_stmt, cy)

    # --- tear-off stub at the bottom (horizontal perforation) ---
    stub_top = _TH - 138
    for xx in range(pad, _TW - pad, 12):
        draw.line([xx, stub_top, xx + 6, stub_top], fill="black", width=1)
    sy = stub_top + 12
    draw.text((pad, sy), f"Ticket #{number}", font=f_serial, fill="black")
    sy += f_serial.size + 8
    for label in ("Name:", "Address:", "Phone:"):
        draw.text((pad, sy), f"{label} {_WRITE_IN}", font=f_stub, fill="black")
        sy += f_stub.size + 9

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
    render_ticket(number, token, info, logos).save(
        buf, format="PDF", resolution=150.0
    )
    return buf.getvalue()


# --- A4 print sheet (multi-page PDF) -------------------------------------
# A4 at 150 DPI. A 2x3 grid = 6 tickets per page (kept at 2 columns for
# legibility); each 10:11 ticket is scaled to fit its cell.
_A4_W, _A4_H = 1240, 1754
_SHEET_MARGIN, _CELL_GAP = 48, 24
_COLUMNS, _ROWS = 2, 3


def _grid_cell() -> tuple[int, int]:
    """Cell size (w, h) for a 10:11 ticket that fits the COLS x ROWS grid."""
    max_w = (_A4_W - 2 * _SHEET_MARGIN - (_COLUMNS - 1) * _CELL_GAP) // _COLUMNS
    max_h = (_A4_H - 2 * _SHEET_MARGIN - (_ROWS - 1) * _CELL_GAP) // _ROWS
    cell_w = min(max_w, round(max_h * 10 / 11))
    return cell_w, round(cell_w * 11 / 10)


def print_sheet_pdf(tickets: list[tuple[int, str]], info: TicketSheetInfo) -> bytes:
    """Lay every ticket out on A4 pages (2x3 grid) and return a multi-page PDF
    ready for bulk printing."""
    logos = _decode_logos(info.logos, target_h=40)

    cell_w, cell_h = _grid_cell()
    per_page = _COLUMNS * _ROWS
    # Center the whole grid on the page.
    grid_w = _COLUMNS * cell_w + (_COLUMNS - 1) * _CELL_GAP
    grid_h = _ROWS * cell_h + (_ROWS - 1) * _CELL_GAP
    x0 = (_A4_W - grid_w) // 2
    y0 = (_A4_H - grid_h) // 2

    pages: list[Image.Image] = []
    page = None
    for idx, (number, token) in enumerate(tickets):
        slot = idx % per_page
        if slot == 0:
            page = Image.new("RGB", (_A4_W, _A4_H), "white")
            pages.append(page)
        r, c = divmod(slot, _COLUMNS)
        x = x0 + c * (cell_w + _CELL_GAP)
        y = y0 + r * (cell_h + _CELL_GAP)
        ticket = render_ticket(number, token, info, logos).resize((cell_w, cell_h))
        page.paste(ticket, (x, y))

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
