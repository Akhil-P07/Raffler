"""Tests for raffle legal-metadata fields and org goc_id.

Covers:
- Creating a raffle with ticket_price / prizes / drawing_datetime /
  drawing_location persists and returns them.
- GET /raffles/{id} (detail) includes all metadata fields.
- PATCH updates metadata fields that are provided; leaves untouched fields
  unchanged (model_fields_set semantics).
- PATCH can clear a metadata field by sending it as null explicitly.
- Blank / whitespace strings are stored as null.
- POST /orgs accepts an optional goc_id and returns it in the response.
"""
import pytest

from tests.conftest import create_raffle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DRAWING_DT = "2026-12-31T19:00:00Z"


def _create_full_raffle(client, org_headers, name="Legal Raffle"):
    resp = client.post(
        "/raffles",
        json={
            "name": name,
            "ticket_price": "$5",
            "prizes": "1st: Trip to Hawaii\n2nd: $500 gift card",
            "drawing_datetime": DRAWING_DT,
            "drawing_location": "Main Auditorium, Building A",
        },
        headers=org_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests: raffle creation with legal metadata
# ---------------------------------------------------------------------------

class TestRaffleMetadataCreate:
    def test_create_raffle_with_all_metadata_persists(self, client, club_org):
        body = _create_full_raffle(client, club_org["headers"])
        assert body["ticket_price"] == "$5"
        assert "Trip to Hawaii" in body["prizes"]
        assert body["drawing_location"] == "Main Auditorium, Building A"
        assert body["drawing_datetime"] is not None

    def test_create_raffle_metadata_included_in_response(self, client, club_org):
        """Response must expose all four metadata fields at creation time."""
        body = _create_full_raffle(client, club_org["headers"])
        for field in ("ticket_price", "prizes", "drawing_datetime", "drawing_location"):
            assert field in body

    def test_create_raffle_without_metadata_returns_null_fields(
        self, client, free_org
    ):
        """Omitting metadata fields should return them as null."""
        resp = client.post(
            "/raffles",
            json={"name": "Minimal Raffle"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["ticket_price"] is None
        assert body["prizes"] is None
        assert body["drawing_datetime"] is None
        assert body["drawing_location"] is None

    def test_blank_ticket_price_stored_as_null(self, client, free_org):
        resp = client.post(
            "/raffles",
            json={"name": "Blank Price", "ticket_price": "   "},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["ticket_price"] is None

    def test_blank_prizes_stored_as_null(self, client, free_org):
        resp = client.post(
            "/raffles",
            json={"name": "Blank Prizes", "prizes": "\t\n"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["prizes"] is None

    def test_blank_drawing_location_stored_as_null(self, client, free_org):
        resp = client.post(
            "/raffles",
            json={"name": "Blank Location", "drawing_location": "  "},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["drawing_location"] is None

    def test_drawing_datetime_roundtrips_correctly(self, client, free_org):
        resp = client.post(
            "/raffles",
            json={"name": "Timed Raffle", "drawing_datetime": DRAWING_DT},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        # The serialized value contains the date — exact format may vary by
        # timezone handling but the date portion must be present.
        assert "2026-12-31" in resp.json()["drawing_datetime"]


# ---------------------------------------------------------------------------
# Tests: GET raffle detail includes metadata
# ---------------------------------------------------------------------------

class TestRaffleDetailMetadata:
    def test_get_raffle_detail_includes_all_metadata(self, client, club_org):
        body = _create_full_raffle(client, club_org["headers"])
        raffle_id = body["id"]

        resp = client.get(f"/raffles/{raffle_id}", headers=club_org["headers"])
        assert resp.status_code == 200
        detail = resp.json()

        assert detail["ticket_price"] == "$5"
        assert "Trip to Hawaii" in detail["prizes"]
        assert detail["drawing_location"] == "Main Auditorium, Building A"
        assert detail["drawing_datetime"] is not None
        # Detail also has entry/ticket counts.
        assert detail["entry_count"] == 0
        assert detail["ticket_count"] == 0

    def test_get_raffle_detail_null_metadata_when_not_set(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(f"/raffles/{raffle_id}", headers=free_org["headers"])
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["ticket_price"] is None
        assert detail["prizes"] is None
        assert detail["drawing_datetime"] is None
        assert detail["drawing_location"] is None


# ---------------------------------------------------------------------------
# Tests: PATCH — update, partial update, and clear metadata fields
# ---------------------------------------------------------------------------

class TestRaffleMetadataPatch:
    def test_patch_sets_ticket_price(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": "$10"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["ticket_price"] == "$10"

    def test_patch_sets_prizes(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"prizes": "Grand Prize: Laptop"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["prizes"] == "Grand Prize: Laptop"

    def test_patch_sets_drawing_datetime(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_datetime": DRAWING_DT},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["drawing_datetime"] is not None

    def test_patch_sets_drawing_location(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_location": "Room 101"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["drawing_location"] == "Room 101"

    def test_patch_omitted_field_is_unchanged(self, client, free_org):
        """Omitting a metadata field from PATCH must leave its value untouched
        (model_fields_set semantics — absent != null)."""
        raffle_id = create_raffle(client, free_org["headers"])

        # First set ticket_price.
        client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": "$5"},
            headers=free_org["headers"],
        )

        # PATCH only the name; ticket_price must still be $5.
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"name": "Updated Name"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Updated Name"
        assert body["ticket_price"] == "$5"  # untouched

    def test_patch_explicit_null_clears_ticket_price(self, client, free_org):
        """Sending ticket_price: null explicitly must clear the field."""
        raffle_id = create_raffle(client, free_org["headers"])

        # Set a price first.
        client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": "$5"},
            headers=free_org["headers"],
        )

        # Now clear it by sending null explicitly.
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": None},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["ticket_price"] is None

    def test_patch_explicit_null_clears_prizes(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        client.patch(
            f"/raffles/{raffle_id}",
            json={"prizes": "Grand Prize: Laptop"},
            headers=free_org["headers"],
        )
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"prizes": None},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["prizes"] is None

    def test_patch_explicit_null_clears_drawing_datetime(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_datetime": DRAWING_DT},
            headers=free_org["headers"],
        )
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_datetime": None},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["drawing_datetime"] is None

    def test_patch_explicit_null_clears_drawing_location(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_location": "Room 101"},
            headers=free_org["headers"],
        )
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"drawing_location": None},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["drawing_location"] is None

    def test_patch_blank_string_clears_field_via_validator(self, client, free_org):
        """The strip_optional validator treats whitespace-only as null even on PATCH."""
        raffle_id = create_raffle(client, free_org["headers"])
        client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": "$5"},
            headers=free_org["headers"],
        )
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"ticket_price": "   "},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["ticket_price"] is None

    def test_patch_multiple_fields_at_once(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={
                "ticket_price": "$20",
                "prizes": "TV",
                "drawing_location": "Gym",
            },
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticket_price"] == "$20"
        assert body["prizes"] == "TV"
        assert body["drawing_location"] == "Gym"


# ---------------------------------------------------------------------------
# Tests: org goc_id
# ---------------------------------------------------------------------------

class TestOrgGocId:
    def test_create_org_with_goc_id_returns_it(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "GOC Org", "plan": "club", "goc_id": "GOC-12345"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["goc_id"] == "GOC-12345"

    def test_create_org_without_goc_id_returns_null(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "No GOC Org", "plan": "free"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["goc_id"] is None

    def test_create_org_with_goc_id_null_returns_null(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "Null GOC Org", "plan": "free", "goc_id": None},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["goc_id"] is None

    def test_create_org_goc_id_max_length_60(self, client, admin_headers):
        """goc_id field has max_length=60; exactly 60 chars must succeed."""
        goc = "G" * 60
        resp = client.post(
            "/orgs",
            json={"name": "Long GOC Org", "plan": "free", "goc_id": goc},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["goc_id"] == goc

    def test_create_org_goc_id_too_long_returns_422(self, client, admin_headers):
        """goc_id longer than 60 chars must be rejected with 422."""
        goc = "G" * 61
        resp = client.post(
            "/orgs",
            json={"name": "Too Long GOC Org", "plan": "free", "goc_id": goc},
            headers=admin_headers,
        )
        assert resp.status_code == 422
