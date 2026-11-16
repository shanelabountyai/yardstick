"""Scorers: deterministic (Phase 1; ``field-equals``, ``label-rate`` in Phase 2), ``llm-judge`` (Phase 3)."""

from __future__ import annotations

from yardstick.scorers.base import Outcome, Scorer, ScorerConfigError
from yardstick.scorers.citation import CitationGrounded
from yardstick.scorers.contains_all import ContainsAll
from yardstick.scorers.exact import Exact
from yardstick.scorers.fields import FieldEquals, LabelRate
from yardstick.scorers.json_schema import JsonSchema
from yardstick.scorers.llm_judge import LlmJudge
from yardstick.scorers.numeric import NumericTolerance
from yardstick.scorers.refusal import RefusalExpected
from yardstick.scorers.regex import Regex

_REGISTRY: dict[str, Scorer] = {
    s.name: s
    for s in (
        Exact(),
        Regex(),
        JsonSchema(),
        NumericTolerance(),
        ContainsAll(),
        RefusalExpected(),
        CitationGrounded(),
        FieldEquals(),
        LabelRate(),
        LlmJudge(),
    )
}


def get_scorer(name: str) -> Scorer:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ScorerConfigError(f"unknown scorer {name!r}; known: {sorted(_REGISTRY)}") from None


def scorer_names() -> list[str]:
    return sorted(_REGISTRY)


__all__ = ["Outcome", "Scorer", "ScorerConfigError", "get_scorer", "scorer_names"]
