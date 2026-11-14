from __future__ import annotations

import re
from typing import Any

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, normalize_text, unknown_options

#: Citation syntax in outputs: [[source-id: "quoted fragment"]]
CITATION = re.compile(r"\[\[\s*([A-Za-z0-9_.\-]+)\s*:\s*\"([^\"]*)\"\s*\]\]")

#: A quote shorter than this after normalization (empty, whitespace-only, one character) is a substring of
#: almost any source, so it can never count as grounded. See DECISIONS D-20.
MIN_QUOTE_CHARS = 2


def _norm(s: str) -> str:
    return normalize_text(s.replace("’", "'").replace("“", '"').replace("”", '"'))


class CitationGrounded:
    """Every citation ``[[id: "quote"]]`` names a known source and its quote appears in that source text.

    A quote shorter than ``MIN_QUOTE_CHARS`` after normalization is never grounded.
    ``expected`` is ``{"sources": {id: text}}``. Zero citations fails (``min_citations`` option, default 1).
    Score = grounded citations / citations.
    """

    name = "citation-grounded"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"min_citations"}, self.name)
        sources = expected.get("sources") if isinstance(expected, dict) else None
        if not isinstance(sources, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in sources.items()
        ):
            raise ScorerConfigError("citation-grounded: expected must be {sources: {id: text}}")
        min_c = options.get("min_citations", 1)
        if isinstance(min_c, bool) or not isinstance(min_c, int) or min_c < 0:
            raise ScorerConfigError("citation-grounded: min_citations must be an integer >= 0")
        cites = CITATION.findall(output.text)
        if len(cites) < min_c:
            return Outcome.binary(False, f"{len(cites)} citation(s), need at least {min_c}")
        if not cites:
            return Outcome.binary(True, "no citations required")
        bad: list[str] = []
        for sid, quote in cites:
            src = sources.get(sid)
            if src is None:
                bad.append(f"{sid}: unknown source")
            elif len(_norm(quote)) < MIN_QUOTE_CHARS:
                bad.append(f"{sid}: quote too short")
            elif _norm(quote) not in _norm(src):
                bad.append(f"{sid}: quote not found")
        score = (len(cites) - len(bad)) / len(cites)
        return Outcome(score, not bad, "; ".join(bad))
