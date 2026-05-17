"""Phase 0 verification: every credential check in verify_credentials.py must PASS."""
from __future__ import annotations

import pytest

from verify_credentials import CHECKS, CheckFn


@pytest.mark.parametrize(
    "name,check_fn",
    CHECKS,
    ids=[name for name, _ in CHECKS],
)
def test_credential_check(name: str, check_fn: CheckFn) -> None:
    passed, elapsed, message = check_fn()
    assert passed, f"{name} failed after {elapsed * 1000:.0f}ms: {message}"
