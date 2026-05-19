"""POST /api/v1/generate-report — produce a one-page PDF for a scored lead.

Default mode: returns the PDF bytes inline as application/pdf with
Content-Disposition: attachment. This is the right shape for "download
this report now" — the actual current use case.

Cloud-Storage mode: when env var USE_GCS_STORAGE=true, uploads the PDF
to gs://leadlens-reports/ and returns JSON with a 24h V4 signed URL.
Gated behind the flag because GCS adds three failure modes for zero
current value (bucket existence, IAM signBlob perm, expiration drift) —
see [[feedback-gcs-deferred-until-real-consumer]] and mirrors the
webhook deferral pattern [[project-webhook-deferred-phase21]]. Flip the
flag when a real consumer asks for "show me last week's report."
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, HttpUrl

from api.services import pdf_generator, report_data, report_storage

router = APIRouter(prefix="/api/v1", tags=["reports"])


class ReportRequest(BaseModel):
    apn: str = Field(min_length=1, max_length=32)
    installer_name: str = "Solar Installer"
    installer_logo_data_uri: str | None = None


class ReportResponse(BaseModel):
    """JSON response — only returned when USE_GCS_STORAGE=true."""
    apn: str
    pdf_url: HttpUrl
    expires_at: dt.datetime
    size_bytes: int


def _gcs_enabled() -> bool:
    return os.environ.get("USE_GCS_STORAGE", "false").lower() in ("1", "true", "yes")


async def _build_pdf_bytes(req: ReportRequest) -> bytes:
    view = await report_data.fetch_for_apn(req.apn)
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=f"APN {req.apn} has not been scored — submit it via /score-lead or /batch-score first",
        )
    return pdf_generator.render_pdf(
        view,
        installer={
            "name": req.installer_name,
            "logo_data_uri": req.installer_logo_data_uri,
        },
    )


@router.post("/generate-report")
async def generate_report(req: ReportRequest):
    pdf_bytes = await _build_pdf_bytes(req)

    if not _gcs_enabled():
        filename = f"lead_{req.apn}_{dt.date.today().isoformat()}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-PDF-Size-Bytes": str(len(pdf_bytes)),
            },
        )

    blob_name = f"{dt.date.today().isoformat()}/{req.apn}-{uuid.uuid4().hex[:8]}.pdf"
    try:
        url = await report_storage.upload_and_sign(pdf_bytes, blob_name, ttl_hours=24)
    except Exception as exc:  # noqa: BLE001 — surface every storage error as 502
        raise HTTPException(
            status_code=502,
            detail=f"PDF generated ({len(pdf_bytes)} bytes) but storage upload failed: {exc!s}",
        )
    expires = dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(hours=24)
    return ReportResponse(
        apn=req.apn,
        pdf_url=url,
        expires_at=expires,
        size_bytes=len(pdf_bytes),
    )
