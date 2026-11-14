from __future__ import annotations

from typing import Any

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, bool_option, normalize_text, unknown_options


class Exact:
    """Output text equals the expected string. ``normalize: true`` strips, casefolds, collapses whitespace."""

    name = "exact"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"normalize"}, self.name)
        if not isinstance(expected, str):
            raise ScorerConfigError("exact: expected must be a string")
        got = output.text
        if bool_option(options, "normalize", False):
            ok = normalize_text(got) == normalize_text(expected)
        else:
            ok = got == expected
        return Outcome.binary(ok, "" if ok else f"expected {expected!r}, got {got[:80]!r}")
