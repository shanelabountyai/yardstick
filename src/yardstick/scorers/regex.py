from __future__ import annotations

import re
from typing import Any

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, bool_option, unknown_options


class Regex:
    """``re.search`` the expected pattern in the output (``fullmatch: true`` for whole-output match)."""

    name = "regex"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"fullmatch", "ignore_case"}, self.name)
        if not isinstance(expected, str):
            raise ScorerConfigError("regex: expected must be a pattern string")
        flags = re.IGNORECASE if bool_option(options, "ignore_case", False) else 0
        try:
            pattern = re.compile(expected, flags)
        except re.error as exc:
            raise ScorerConfigError(f"regex: invalid pattern {expected!r}: {exc}") from exc
        if bool_option(options, "fullmatch", False):
            ok = pattern.fullmatch(output.text) is not None
        else:
            ok = pattern.search(output.text) is not None
        return Outcome.binary(ok, "" if ok else f"no match for /{expected}/")
