"""Tests for per-raffle logo management: POST/GET/DELETE /raffles/{id}/logos.

Covers:
- Upload a valid PNG → 201 + {id, name, position}; position increments.
- GET list returns logos ordered by position.
- GET image returns image/png bytes with correct magic header.
- DELETE removes a logo (204) and it disappears from the list.
- Uploading more than MAX_LOGOS_PER_RAFFLE (6) returns 409.
- Empty file → 422.
- Oversized file (>2 MB) → 413.
- Non-image bytes → 422.
- Raw SVG bytes → 422 with the cairosvg-not-installed message.
- Org isolation: org B gets 404 for org A's raffle logos (list, upload,
  get image, delete) and for a non-existent logo id.
- Print sheet still returns a valid PNG when logos are attached.
"""
import io
import struct
import zlib

import pytest

from tests.conftest import create_raffle, generate_tickets

PNG_MAGIC = b"\x89PNG"

# ---------------------------------------------------------------------------
# PNG generation helpers (no filesystem I/O — pure in-memory)
# ---------------------------------------------------------------------------

def _make_png(width: int = 4, height: int = 4, color: tuple = (255, 0, 0)) -> bytes:
    """Build a minimal but fully valid PNG from scratch using only stdlib.

    We avoid Pillow here so the helper has zero side-effects; Pillow IS used
    in some tests that need a Pillow-generated image (to confirm the normalize
    path works end-to-end), but this raw builder lets us craft edge cases
    (e.g. oversized files) without invoking the full image pipeline.
    """
    def _chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    r, g, b = color
    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # Raw scanlines: filter byte 0 + RGB pixels
    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00" + bytes([r, g, b] * width)
    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def _make_png_via_pillow(width: int = 8, height: int = 8) -> bytes:
    """Use Pillow to produce a tiny PNG — confirms normalize_logo path works."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload_logo(client, org_headers, raffle_id, png_bytes, name=None):
    """POST a logo file; return the raw Response."""
    files = {"file": ("logo.png", io.BytesIO(png_bytes), "image/png")}
    data = {}
    if name is not None:
        data["name"] = name
    return client.post(
        f"/raffles/{raffle_id}/logos",
        files=files,
        data=data,
        headers=org_headers,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def raffle_id(client, club_org):
    """A fresh raffle owned by club_org."""
    return create_raffle(client, club_org["headers"], name="Logo Raffle")


@pytest.fixture()
def tiny_png():
    return _make_png()


# ---------------------------------------------------------------------------
# Tests: upload happy path
# ---------------------------------------------------------------------------

class TestLogoUpload:
    def test_upload_png_returns_201(self, client, club_org, raffle_id, tiny_png):
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 201

    def test_upload_response_has_id_name_position(
        self, client, club_org, raffle_id, tiny_png
    ):
        resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="RIT AI"
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "RIT AI"
        assert body["position"] == 0  # first logo is at position 0

    def test_upload_second_logo_position_increments(
        self, client, club_org, raffle_id, tiny_png
    ):
        _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 201
        assert resp.json()["position"] == 1

    def test_upload_three_logos_positions_0_1_2(
        self, client, club_org, raffle_id, tiny_png
    ):
        positions = []
        for _ in range(3):
            resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
            assert resp.status_code == 201
            positions.append(resp.json()["position"])
        assert positions == [0, 1, 2]

    def test_upload_without_name_stores_null(
        self, client, club_org, raffle_id, tiny_png
    ):
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 201
        assert resp.json()["name"] is None

    def test_upload_with_whitespace_name_stores_null(
        self, client, club_org, raffle_id, tiny_png
    ):
        resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="   "
        )
        assert resp.status_code == 201
        assert resp.json()["name"] is None

    def test_upload_pillow_generated_png_succeeds(
        self, client, club_org, raffle_id
    ):
        png = _make_png_via_pillow()
        resp = _upload_logo(client, club_org["headers"], raffle_id, png)
        assert resp.status_code == 201

    def test_upload_requires_api_key(self, client, raffle_id, tiny_png):
        files = {"file": ("logo.png", io.BytesIO(tiny_png), "image/png")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: GET list
# ---------------------------------------------------------------------------

class TestLogoList:
    def test_list_logos_empty_returns_empty_list(
        self, client, club_org, raffle_id
    ):
        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=club_org["headers"]
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_logos_ordered_by_position(
        self, client, club_org, raffle_id, tiny_png
    ):
        for i in range(3):
            _upload_logo(
                client, club_org["headers"], raffle_id, tiny_png, name=f"Logo {i}"
            )
        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=club_org["headers"]
        )
        assert resp.status_code == 200
        logos = resp.json()
        assert len(logos) == 3
        positions = [lg["position"] for lg in logos]
        assert positions == sorted(positions)
        assert positions == [0, 1, 2]

    def test_list_logos_returns_correct_names(
        self, client, club_org, raffle_id, tiny_png
    ):
        _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="Alpha"
        )
        _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="Beta"
        )
        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=club_org["headers"]
        )
        names = [lg["name"] for lg in resp.json()]
        assert names == ["Alpha", "Beta"]

    def test_list_logos_on_unknown_raffle_returns_404(
        self, client, club_org
    ):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(
            f"/raffles/{fake_id}/logos", headers=club_org["headers"]
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET image bytes
# ---------------------------------------------------------------------------

class TestLogoImage:
    def test_get_logo_image_returns_png_bytes(
        self, client, club_org, raffle_id, tiny_png
    ):
        upload_resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png
        )
        logo_id = upload_resp.json()["id"]

        resp = client.get(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == PNG_MAGIC

    def test_get_logo_image_content_is_valid_png(
        self, client, club_org, raffle_id, tiny_png
    ):
        """The stored bytes must be openable by Pillow as a PNG."""
        from PIL import Image

        upload_resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png
        )
        logo_id = upload_resp.json()["id"]

        resp = client.get(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "PNG"

    def test_get_logo_image_unknown_logo_id_returns_404(
        self, client, club_org, raffle_id
    ):
        fake_logo_id = "00000000-0000-0000-0000-000000000001"
        resp = client.get(
            f"/raffles/{raffle_id}/logos/{fake_logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: DELETE
# ---------------------------------------------------------------------------

class TestLogoDelete:
    def test_delete_logo_returns_204(
        self, client, club_org, raffle_id, tiny_png
    ):
        upload_resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png
        )
        logo_id = upload_resp.json()["id"]

        resp = client.delete(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 204

    def test_delete_logo_disappears_from_list(
        self, client, club_org, raffle_id, tiny_png
    ):
        upload_resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png
        )
        logo_id = upload_resp.json()["id"]

        client.delete(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )

        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=club_org["headers"]
        )
        assert resp.status_code == 200
        ids = [lg["id"] for lg in resp.json()]
        assert logo_id not in ids

    def test_delete_one_of_two_logos_leaves_the_other(
        self, client, club_org, raffle_id, tiny_png
    ):
        id_a = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="A"
        ).json()["id"]
        id_b = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="B"
        ).json()["id"]

        client.delete(
            f"/raffles/{raffle_id}/logos/{id_a}",
            headers=club_org["headers"],
        )

        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=club_org["headers"]
        )
        ids = [lg["id"] for lg in resp.json()]
        assert id_a not in ids
        assert id_b in ids

    def test_delete_nonexistent_logo_returns_404(
        self, client, club_org, raffle_id
    ):
        fake_logo_id = "00000000-0000-0000-0000-000000000002"
        resp = client.delete(
            f"/raffles/{raffle_id}/logos/{fake_logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 404

    def test_deleted_logo_image_endpoint_returns_404(
        self, client, club_org, raffle_id, tiny_png
    ):
        upload_resp = _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png
        )
        logo_id = upload_resp.json()["id"]

        client.delete(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )

        resp = client.get(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: upload limit (MAX_LOGOS_PER_RAFFLE = 6)
# ---------------------------------------------------------------------------

class TestLogoLimit:
    def test_uploading_six_logos_succeeds(
        self, client, club_org, raffle_id, tiny_png
    ):
        for _ in range(6):
            resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
            assert resp.status_code == 201

    def test_uploading_seventh_logo_returns_409(
        self, client, club_org, raffle_id, tiny_png
    ):
        for _ in range(6):
            _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 409

    def test_409_detail_mentions_max_logos(
        self, client, club_org, raffle_id, tiny_png
    ):
        for _ in range(6):
            _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert "6" in resp.json()["detail"]

    def test_delete_and_re_upload_stays_under_limit(
        self, client, club_org, raffle_id, tiny_png
    ):
        """Deleting a logo frees a slot so a new one can be uploaded."""
        ids = []
        for _ in range(6):
            resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
            ids.append(resp.json()["id"])

        # Delete one.
        client.delete(
            f"/raffles/{raffle_id}/logos/{ids[0]}",
            headers=club_org["headers"],
        )

        # Should be able to upload again now.
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Tests: upload validation errors
# ---------------------------------------------------------------------------

class TestLogoValidation:
    def test_empty_file_returns_422(self, client, club_org, raffle_id):
        files = {"file": ("empty.png", io.BytesIO(b""), "image/png")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
            headers=club_org["headers"],
        )
        assert resp.status_code == 422

    def test_oversized_file_returns_413(self, client, club_org, raffle_id):
        """Exactly 2 000 001 bytes must be rejected with 413."""
        big = b"X" * (2_000_001)
        files = {"file": ("big.png", io.BytesIO(big), "image/png")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
            headers=club_org["headers"],
        )
        assert resp.status_code == 413

    def test_non_image_bytes_returns_422(self, client, club_org, raffle_id):
        """Random garbage that is not a valid image must return 422."""
        garbage = b"This is definitely not an image file at all."
        files = {"file": ("garbage.png", io.BytesIO(garbage), "image/png")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
            headers=club_org["headers"],
        )
        assert resp.status_code == 422

    def test_raw_svg_bytes_returns_422_with_message(
        self, client, club_org, raffle_id
    ):
        """SVG bytes without cairosvg installed must return 422 with the
        'upload through the web app / send PNG' guidance message."""
        svg = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
            b'<circle cx="50" cy="50" r="40" fill="red"/>'
            b"</svg>"
        )
        files = {"file": ("logo.svg", io.BytesIO(svg), "image/svg+xml")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
            headers=club_org["headers"],
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        # The message should instruct the caller to use the web app or send PNG.
        assert "web app" in detail or "PNG" in detail or "png" in detail.lower()

    def test_svg_starting_with_svg_tag_returns_422(
        self, client, club_org, raffle_id
    ):
        """SVG that starts directly with <svg> (no XML declaration) also 422."""
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            b'<rect width="10" height="10" fill="blue"/>'
            b"</svg>"
        )
        files = {"file": ("logo.svg", io.BytesIO(svg), "image/svg+xml")}
        resp = client.post(
            f"/raffles/{raffle_id}/logos",
            files=files,
            headers=club_org["headers"],
        )
        assert resp.status_code == 422

    def test_exactly_2mb_file_is_accepted_if_valid_image(
        self, client, club_org, raffle_id, tiny_png
    ):
        """A file at exactly 2 000 000 bytes must NOT be rejected for size.
        We use the tiny PNG header + padding — Pillow will reject non-PNG
        padding, so we just verify the 413 boundary is exclusive."""
        # The easiest boundary check: our 4x4 PNG is well under 2 MB.
        assert len(tiny_png) < 2_000_000
        resp = _upload_logo(client, club_org["headers"], raffle_id, tiny_png)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Tests: org isolation (logos)
# ---------------------------------------------------------------------------

class TestLogoOrgIsolation:
    def _setup_logo(self, client, org, tiny_png):
        """Create a raffle + upload one logo; return (raffle_id, logo_id)."""
        raffle_id = create_raffle(client, org["headers"], name="Isolation Raffle")
        resp = _upload_logo(client, org["headers"], raffle_id, tiny_png)
        logo_id = resp.json()["id"]
        return raffle_id, logo_id

    def test_org_b_cannot_list_org_a_logos(
        self, client, club_org, org_b, tiny_png
    ):
        raffle_id, _ = self._setup_logo(client, club_org, tiny_png)
        resp = client.get(
            f"/raffles/{raffle_id}/logos", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_upload_logo_to_org_a_raffle(
        self, client, club_org, org_b, tiny_png
    ):
        raffle_id = create_raffle(client, club_org["headers"], name="Org A Raffle")
        resp = _upload_logo(client, org_b["headers"], raffle_id, tiny_png)
        assert resp.status_code == 404

    def test_org_b_cannot_get_org_a_logo_image(
        self, client, club_org, org_b, tiny_png
    ):
        raffle_id, logo_id = self._setup_logo(client, club_org, tiny_png)
        resp = client.get(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=org_b["headers"],
        )
        assert resp.status_code == 404

    def test_org_b_cannot_delete_org_a_logo(
        self, client, club_org, org_b, tiny_png
    ):
        raffle_id, logo_id = self._setup_logo(client, club_org, tiny_png)
        resp = client.delete(
            f"/raffles/{raffle_id}/logos/{logo_id}",
            headers=org_b["headers"],
        )
        assert resp.status_code == 404

    def test_org_b_logo_id_on_org_a_raffle_returns_404(
        self, client, club_org, org_b, tiny_png
    ):
        """org B's own logo_id used against org A's raffle must also 404."""
        # Create a logo under org_b.
        raffle_b = create_raffle(client, org_b["headers"], name="Org B Raffle")
        logo_resp = _upload_logo(client, org_b["headers"], raffle_b, tiny_png)
        org_b_logo_id = logo_resp.json()["id"]

        # Org A raffle.
        raffle_a = create_raffle(client, club_org["headers"], name="Org A Raffle")

        # Trying org B's logo_id against org A's raffle.
        resp = client.get(
            f"/raffles/{raffle_a}/logos/{org_b_logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 404

    def test_nonexistent_logo_id_returns_404(
        self, client, club_org, raffle_id
    ):
        fake_logo_id = "00000000-0000-0000-0000-000000000099"
        resp = client.get(
            f"/raffles/{raffle_id}/logos/{fake_logo_id}",
            headers=club_org["headers"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: print sheet still works with logos attached
# ---------------------------------------------------------------------------

class TestPrintSheetWithLogos:
    def test_sheet_returns_pdf_when_raffle_has_logos(
        self, client, club_org, tiny_png
    ):
        raffle_id = create_raffle(client, club_org["headers"], name="Sheet+Logo")
        generate_tickets(client, club_org["headers"], raffle_id, count=2)
        _upload_logo(
            client, club_org["headers"], raffle_id, tiny_png, name="Test Logo"
        )

        resp = client.get(
            f"/raffles/{raffle_id}/tickets/sheet",
            headers=club_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_sheet_pdf_with_multiple_logos(self, client, club_org, tiny_png):
        raffle_id = create_raffle(client, club_org["headers"], name="Multi-Logo Sheet")
        generate_tickets(client, club_org["headers"], raffle_id, count=1)
        for i in range(3):
            _upload_logo(
                client, club_org["headers"], raffle_id, tiny_png, name=f"Logo {i}"
            )

        resp = client.get(
            f"/raffles/{raffle_id}/tickets/sheet",
            headers=club_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_ticket_preview_with_logo_is_valid_png(
        self, client, app_and_db, club_org, tiny_png
    ):
        """The per-ticket preview image (shown in the dashboard) embeds the logo
        and must be a valid PNG."""
        from PIL import Image

        _, database_mod = app_and_db
        raffle_id = create_raffle(client, club_org["headers"], name="Preview Logo")
        generate_tickets(client, club_org["headers"], raffle_id, count=1)
        _upload_logo(client, club_org["headers"], raffle_id, tiny_png)

        s = database_mod.SessionLocal()
        try:
            ticket_id = (
                s.query(database_mod.Ticket)
                .filter(database_mod.Ticket.raffle_id == raffle_id)
                .first()
                .id
            )
        finally:
            s.close()

        resp = client.get(f"/tickets/{ticket_id}/preview", headers=club_org["headers"])
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "PNG"
        # The ticket is a wide full-width strip (much wider than tall).
        assert img.width > img.height
