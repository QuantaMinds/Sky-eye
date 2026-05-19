"""Earth Engine session management.

One module, one job: initialize the EE client exactly once per process and
hand it back. Auth picks one of two paths in this order:

  1. EARTH_ENGINE_SERVICE_ACCOUNT + EARTH_ENGINE_PRIVATE_KEY_FILE set
     -> ee.ServiceAccountCredentials. Used in prod / CI.
  2. Application Default Credentials (gcloud auth application-default
     login). Used in dev. Same credentials path as Vertex / BigQuery.

`EARTH_ENGINE_PROJECT` overrides `GOOGLE_CLOUD_PROJECT`; one of them MUST
be set (commercial-tier datasets like AlphaEarth are billed to that
project, and EE refuses to initialize without one on commercial tier).

Truth-first: callers that need EE but get an init failure should NOT
silently fall back to fake values. They surface `source='unavailable'`
upstream — see ee_naip.get_naip_chip and ee_sentinel2.get_sentinel2_chip.
"""
from __future__ import annotations

import threading

from api.config import get_settings

_lock = threading.Lock()
_initialized = False


def _project() -> str:
    s = get_settings()
    project = s.earth_engine_project or s.google_cloud_project
    if not project:
        raise RuntimeError(
            "Earth Engine requires EARTH_ENGINE_PROJECT or GOOGLE_CLOUD_PROJECT to be set"
        )
    return project


def init() -> None:
    """Idempotent EE init. Safe to call from multiple threads."""
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        import ee

        s = get_settings()
        project = _project()
        if s.earth_engine_service_account and s.earth_engine_private_key_file:
            creds = ee.ServiceAccountCredentials(
                s.earth_engine_service_account,
                s.earth_engine_private_key_file,
            )
            ee.Initialize(credentials=creds, project=project)
        else:
            ee.Initialize(project=project)
        _initialized = True


def ee_module():
    """Return the initialized `ee` module. Convenience for callers that
    don't want to remember to call `init()` before `import ee`."""
    init()
    import ee
    return ee


def project_id() -> str:
    return _project()


def _reset_for_tests() -> None:
    """Test-only — flip the singleton back to uninitialized so a fresh
    monkeypatched ee module can be installed."""
    global _initialized
    _initialized = False
