"""Retry window helper. Added on 2026-11-17 as a live test of the review pipeline; safe to delete."""


def attempts_left(limit: int, used: int) -> int:
    """How many attempts remain before the window closes."""
    return limit - used


def window_closed(limit: int, used: int) -> bool:
    """Whether every attempt has been used."""
    return attempts_left(limit, used) <= 0
