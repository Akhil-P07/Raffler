"""Per-raffle logo management.

A raffle can be co-hosted by several organizations, so logos are a collection
on the raffle (not the org). All routes are scoped through raffle → org
ownership. SVGs are rasterized to PNG in the browser before upload; the API
stores normalized PNG bytes.
"""
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Organization, Raffle, RaffleLogo, get_db
from middleware.ownership import _is_uuid, get_owned_raffle, require_org
from schemas import RaffleLogoResponse
from services.qr import normalize_logo

router = APIRouter(tags=["logos"])

MAX_LOGOS_PER_RAFFLE = 6
MAX_UPLOAD_BYTES = 2_000_000  # 2 MB raw upload cap

_LOGO_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found."
)


def _get_owned_logo(
    raffle_id: str, logo_id: str, org: Organization, db: Session
) -> RaffleLogo:
    # Confirm the raffle belongs to the org first (404 on any mismatch), then
    # resolve the logo within that raffle. Validate the id shape first so a
    # malformed id behaves like every other route (uniform 404).
    raffle = get_owned_raffle(raffle_id, org, db)
    if not _is_uuid(logo_id):
        raise _LOGO_NOT_FOUND
    logo = db.get(RaffleLogo, logo_id)
    if logo is None or logo.raffle_id != raffle.id:
        raise _LOGO_NOT_FOUND
    return logo


@router.get(
    "/raffles/{raffle_id}/logos", response_model=list[RaffleLogoResponse]
)
def list_logos(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[RaffleLogoResponse]:
    raffle = get_owned_raffle(raffle_id, org, db)
    logos = db.scalars(
        select(RaffleLogo)
        .where(RaffleLogo.raffle_id == raffle.id)
        .order_by(RaffleLogo.position)
    ).all()
    return [RaffleLogoResponse.model_validate(logo) for logo in logos]


@router.post(
    "/raffles/{raffle_id}/logos",
    response_model=RaffleLogoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_logo(
    raffle_id: str,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> RaffleLogoResponse:
    raffle = get_owned_raffle(raffle_id, org, db)

    # Read the body in chunks and abort as soon as it exceeds the cap, so an
    # oversized upload isn't buffered into memory in full.
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Logo file too large (max 2 MB).",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty file.",
        )

    # Lock the raffle row so concurrent uploads can't both pass the cap check
    # or grab the same position (mirrors the plan-limit lock pattern).
    db.execute(select(Raffle.id).where(Raffle.id == raffle.id).with_for_update())
    existing = db.scalar(
        select(func.count())
        .select_from(RaffleLogo)
        .where(RaffleLogo.raffle_id == raffle.id)
    ) or 0
    if existing >= MAX_LOGOS_PER_RAFFLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A raffle can have at most {MAX_LOGOS_PER_RAFFLE} logos.",
        )

    try:
        png = normalize_logo(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    label = (name or "").strip() or None
    logo = RaffleLogo(
        raffle_id=raffle.id, name=label, image=png, position=existing
    )
    db.add(logo)
    db.commit()
    db.refresh(logo)
    return RaffleLogoResponse.model_validate(logo)


@router.get(
    "/raffles/{raffle_id}/logos/{logo_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Logo PNG"}},
)
def get_logo_image(
    raffle_id: str,
    logo_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> Response:
    logo = _get_owned_logo(raffle_id, logo_id, org, db)
    return Response(content=logo.image, media_type="image/png")


@router.delete(
    "/raffles/{raffle_id}/logos/{logo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_logo(
    raffle_id: str,
    logo_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> None:
    logo = _get_owned_logo(raffle_id, logo_id, org, db)
    db.delete(logo)
    db.commit()
    return None
