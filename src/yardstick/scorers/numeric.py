from __future__ import annotations

import json
import math
import re
from typing import Any

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, unknown_options

_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def first_number(text: str) -> float | None:
    m = _NUMBER.search(text)
    if m is None:
        return None
    return float(m.group(0).replace(",", ""))


class NumericTolerance:
    """First number in the output is within ``abs_tol`` or ``rel_tol`` of the expected number.

    Defaults: ``abs_tol: 0``, ``rel_tol: 0`` (exact numeric equality). ``field``: if set, the output is
    parsed as JSON and the number is read from that top-level key instead.
    """

    name = "numeric-tolerance"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"abs_tol", "rel_tol", "field"}, self.name)
        if isinstance(expected, bool) or not isinstance(expected, int | float):
            raise ScorerConfigError("numeric-tolerance: expected must be a number")
        abs_tol = options.get("abs_tol", 0)
        rel_tol = options.get("rel_tol", 0)
        for k, v in (("abs_tol", abs_tol), ("rel_tol", rel_tol)):
            if isinstance(v, bool) or not isinstance(v, int | float) or v < 0:
                raise ScorerConfigError(f"numeric-tolerance: {k} must be a number >= 0")
        got = self._extract(output.text, options.get("field"))
        if got is None:
            return Outcome.binary(False, "no number found in output")
        ok = math.isclose(got, float(expected), rel_tol=float(rel_tol), abs_tol=float(abs_tol))
        return Outcome.binary(ok, "" if ok else f"expected {expected}, got {got}")

    @staticmethod
    def _extract(text: str, field: Any) -> float | None:
        if field is None:
            return first_number(text)

        if not isinstance(field, str):
            raise ScorerConfigError("numeric-tolerance: field must be a string")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict):
            return None
        v = value.get(field)
        if isinstance(v, bool):
            return None
        if isinstance(v, int | float):
            return float(v)
        if isinstance(v, str):
            return first_number(v)
        return None
