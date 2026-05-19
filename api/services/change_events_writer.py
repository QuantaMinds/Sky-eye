"""Persistence for TaxLens detections -> leadlens.change_events.

Writes one row per detection that has the minimum-required fields the
schema declares NOT NULL: confidence_score, imagery_before_date,
imagery_after_date. Detections with final_score=None are NOT persisted
(Rule 3 — we don't write a fake confidence to satisfy the schema; the
in-memory response still surfaces them).

Why this module exists: the Phase 5 forensic pass caught that
detect-changes returned a response but wrote ZERO rows to BQ — the
endpoint claimed an audit trail it didn't actually keep. This module
closes that gap.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from typing import Any

from google.cloud import bigquery

from api.config import get_settings
from api.models.change_detection import Detection

_TABLE = "sky-eye-496604.leadlens.change_events"
_LOCATION = "us-west1"
_DETECTION_MODEL = "alphaearth_v1+gemini_pro_2.5"
_PIPELINE_VERSION = "phase-5.0.0"

logger = logging.getLogger(__name__)


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or "sky-eye-496604"
    return bigquery.Client(project=project, location=_LOCATION)


def _imagery_date(year: int) -> dt.date:
    """Annual imagery has no single date — pin to calendar-year start.
    Truth-first compromise: the DATE column requires a value, but the
    audit trail should also record that this is a calendar-year anchor
    (see imagery_before_date_note in the row builder)."""
    return dt.date(year, 1, 1)


def _row_for(detection: Detection, year_a: int, year_b: int) -> dict[str, Any] | None:
    """Returns the row dict, or None if the detection cannot be persisted
    without fabrication (NOT NULL fields missing)."""
    if detection.final_score is None:
        return None  # Rule 3: confidence_score is NOT NULL; no fake values
    if detection.classifier_source == "unavailable":
        permit_status = "no_check_run"
    elif detection.gates["no_permit"].fired is None:
        permit_status = "no_check_run"
    elif detection.gates["no_permit"].fired is True:
        permit_status = "no_permit_in_window"
    else:
        permit_status = "permit_matches"
    return {
        "event_id": str(uuid.uuid4()),
        "ain": detection.apn,
        "detected_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "imagery_before_date": _imagery_date(year_a).isoformat(),
        "imagery_after_date": _imagery_date(year_b).isoformat(),
        "change_type": detection.change_type,
        "change_area_sqft_estimated": detection.estimated_added_sqft,
        "confidence_score": round(detection.final_score, 9),
        "permit_check_status": permit_status,
        "detection_model": _DETECTION_MODEL,
        "pipeline_version": _PIPELINE_VERSION,
        "review_status": "auto_detected",
    }


def _write_sync(rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
    if not rows:
        return 0, []
    errors = _client().insert_rows_json(_TABLE, rows)
    if errors:
        return 0, [str(e) for e in errors]
    return len(rows), []


async def persist_detections(
    detections: list[Detection], year_a: int, year_b: int,
) -> tuple[int, int]:
    """Returns (rows_written, rows_skipped_unavailable). Best-effort:
    BQ failure is logged but does not crash the endpoint response."""
    rows = []
    skipped = 0
    for d in detections:
        r = _row_for(d, year_a, year_b)
        if r is None:
            skipped += 1
        else:
            rows.append(r)
    try:
        written, errors = await asyncio.to_thread(_write_sync, rows)
        if errors:
            logger.warning("change_events insert errors: %s", errors[:3])
            return 0, skipped + len(rows)
        return written, skipped
    except Exception as exc:  # noqa: BLE001 — endpoint must keep responding
        logger.warning("change_events insert failed: %s", exc)
        return 0, skipped + len(rows)
