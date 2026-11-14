from __future__ import annotations

from typing import Any

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, bool_option, normalize_text, unknown_options


class ContainsAll:
    """Every expected string appears in the output. Score = fraction found; pass only if all are found."""

    name = "contains-all"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"case_sensitive"}, self.name)
        if (
            not isinstance(expected, list)
            or not expected
            or not all(isinstance(x, str) and x for x in expected)
        ):
            raise ScorerConfigError("contains-all: expected must be a non-empty list of non-empty strings")
        if bool_option(options, "case_sensitive", False):
            hay = output.text
            missing = [x for x in expected if x not in hay]
        else:
            hay = normalize_text(output.text)
            missing = [x for x in expected if normalize_text(x) not in hay]
        found = len(expected) - len(missing)
        score = found / len(expected)
        return Outcome(score, not missing, "" if not missing else f"missing: {missing}")
