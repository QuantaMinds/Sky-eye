"""Sanity test for address normalization (api/utils/address.py).

Covers what the function IS expected to handle (casing, punctuation,
suffix variants) and pins the cases it is NOT expected to handle
(directional spell-outs, half-house fractions, leading zeros) so any
future caller assuming broader coverage hits a clear contract boundary.
"""
from __future__ import annotations

import pytest

from api.utils.address import normalize_address


@pytest.mark.parametrize("a,b", [
    # situs string vs corresponding mailing string — must normalize equal
    ("1122 Bixby Rd, Long Beach, CA 90807", "1122 BIXBY RD LONG BEACH CA 90807"),
    ("4242 LIME AVE", "4242 LIME AV"),
    ("4242 Lime Avenue", "4242 LIME AV"),
    ("123 main street", "123 MAIN ST"),
    ("8700 Beverly Blvd.", "8700 BEVERLY BLVD"),
    ("8700 BEVERLY BOULEVARD", "8700 BEVERLY BLVD"),
    ("100 Long Beach Boulevard", "100 LONG BEACH BLVD"),
    ("555 Sunset Drive", "555 SUNSET DR"),
    ("99 Vista Place", "99 VISTA PL"),
    ("12 Forest Lane",  "12 FOREST LN"),
    ("888 Pacific Coast Highway", "888 PACIFIC COAST HWY"),
    ("777 OAK ROAD", "777 OAK RD"),
    ("321 ELM COURT", "321 ELM CT"),
    # Punctuation + whitespace handling
    ("100  Long-Beach  Blvd",  "100 LONG BEACH BLVD"),
    ("4242, LIME, AV",         "4242 LIME AV"),
    ("4242_LIME_AV",           "4242 LIME AV"),
    ("4242#LIME#AV",           "4242 LIME AV"),
    ("4242 LIME AV.",          "4242 LIME AV"),
])
def test_normalizes_equal(a: str, b: str) -> None:
    assert normalize_address(a) == normalize_address(b), \
        f"{a!r} -> {normalize_address(a)!r}  !=  {b!r} -> {normalize_address(b)!r}"


@pytest.mark.parametrize("inp,expected", [
    ("", ""),
    (None, ""),
    ("   ", ""),
])
def test_empty_and_none(inp: str, expected: str) -> None:
    assert normalize_address(inp) == expected


def test_suffix_idempotent() -> None:
    """Running normalize twice produces the same output as once — important
    for caller code that might normalize a string that's already normalized."""
    a = normalize_address("4242 Lime Avenue")
    b = normalize_address(a)
    assert a == b == "4242 LIME AV"


def test_unsupported_cases_documented() -> None:
    """These are NOT normalized — documented contract limits."""
    # Directional spell-outs not canonicalized
    assert normalize_address("123 N MAIN ST") != normalize_address("123 NORTH MAIN ST")
    # Half-house fractions not handled
    assert normalize_address("123 1/2 MAIN ST") != normalize_address("123 MAIN ST")
    # Leading zeros not normalized
    assert normalize_address("0123 MAIN ST") != normalize_address("123 MAIN ST")
    # Unit markers not canonicalized (APT/UNIT/#)
    assert normalize_address("4242 LIME AV APT 5") != normalize_address("4242 LIME AV UNIT 5")
