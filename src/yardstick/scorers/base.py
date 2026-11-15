"""Scorer protocol and shared helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from yardstick.models import Output


class ScorerConfigError(ValueError):
    """The suite gave a scorer an expected value or option it cannot use."""


@dataclass(frozen=True)
class Outcome:
    """A scorer's verdict. Counting scorers set ``hits``/``total``; ``applicable=False`` means there was
    nothing to score (e.g. no labels to count), so the runner records no score for that item."""

    score: float
    passed: bool
    detail: str = ""
    hits: int | None = None
    total: int | None = None
    applicable: bool = True

    @staticmethod
    def binary(passed: bool, detail: str = "") -> Outcome:
        return Outcome(1.0 if passed else 0.0, passed, detail)

    @staticmethod
    def not_applicable(detail: str = "") -> Outcome:
        return Outcome(0.0, False, detail, applicable=False)


class Scorer(Protocol):
    """``name`` is the registry name. A scorer whose counts are not items (e.g. sentence labels) also sets a
    class attribute ``counting = True``, so a target error counts as 0/0 rather than a phantom 0/1."""

    name: str

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome: ...


_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Strip, casefold and collapse whitespace."""
    return _WS.sub(" ", text.strip()).casefold()


def bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    v = options.get(key, default)
    if not isinstance(v, bool):
        raise ScorerConfigError(f"option {key!r} must be true or false")
    return v


def unknown_options(options: dict[str, Any], allowed: set[str], scorer: str) -> None:
    extra = set(options) - allowed
    if extra:
        raise ScorerConfigError(f"{scorer}: unknown options {sorted(extra)}")
