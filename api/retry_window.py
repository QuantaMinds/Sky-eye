"""Retry window helper. Added on 2026-11-17 as a live test of the review pipeline; safe to delete."""


def attempts_left(limit: int, used: int) -> int:
    """How many attempts remain before the window closes."""
    return limit - used
