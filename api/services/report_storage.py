"""Upload generated PDFs to Cloud Storage and return signed URLs.

Bucket defaults to leadlens-reports; override via env var
LEADLENS_REPORTS_BUCKET if the deploy uses a different bucket name.

Signed URLs default to 24-hour expiry (Phase 3 spec). They are V4
signed URLs, which work with both service-account and ADC token-based
credentials (the latter falls back to IAM credentials API for signing
when no private key is present locally).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os

from google.cloud import storage

_DEFAULT_BUCKET = "leadlens-reports"


def _bucket_name() -> str:
    return os.environ.get("LEADLENS_REPORTS_BUCKET") or _DEFAULT_BUCKET


def _upload_and_sign_sync(
    pdf_bytes: bytes, blob_name: str, *, ttl_hours: int = 24
) -> str:
    client = storage.Client()
    bucket = client.bucket(_bucket_name())
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return blob.generate_signed_url(
        version="v4",
        expiration=dt.timedelta(hours=ttl_hours),
        method="GET",
    )


async def upload_and_sign(
    pdf_bytes: bytes, blob_name: str, *, ttl_hours: int = 24
) -> str:
    return await asyncio.to_thread(
        _upload_and_sign_sync, pdf_bytes, blob_name, ttl_hours=ttl_hours
    )
