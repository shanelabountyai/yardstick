"""Injectable clock so run JSON can be made byte-identical in tests (YS-01)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class FixedClock:
    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        self._at = at

    def now(self) -> datetime:
        return self._at


def parse_fixed(value: str) -> FixedClock:
    """Build a ``FixedClock`` from an ISO-8601 string (``Z`` suffix accepted)."""
    return FixedClock(datetime.fromisoformat(value.replace("Z", "+00:00")))
