"""Scorers over structured output fields (``Output.fields``), added in Phase 2 for results-file targets."""

from __future__ import annotations

from typing import Any

from yardstick.hashing import canonical_json
from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, unknown_options

_MISSING = object()


def _show(value: Any) -> str:
    return "not reported" if value is _MISSING else canonical_json(value)


class FieldEquals:
    """Pass iff every field named in ``expected`` (a mapping) equals its expected value in ``output.fields``.

    A field the target did not report fails ("not reported"); it is never treated as a match.
    """

    name = "field-equals"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, set(), self.name)
        if not isinstance(expected, dict) or not expected or not all(isinstance(k, str) for k in expected):
            raise ScorerConfigError("field-equals: expected must be a non-empty mapping of field -> value")
        misses = []
        for field in sorted(expected):
            got = output.fields.get(field, _MISSING)
            if got is _MISSING or got != expected[field]:
                misses.append(f"{field}: expected {_show(expected[field])}, got {_show(got)}")
        return Outcome.binary(not misses, "; ".join(misses))


class LabelRate:
    """Share of the labels in a list field that are positive, e.g. a judge's per-sentence verdicts.

    Options: ``field`` (the list field, required), ``positive`` (labels that count as hits, required),
    ``exclude`` (labels left out of the count entirely, e.g. ``schema_invalid``; default none).
    ``expected`` is the minimum share for the item to pass (0..1). Counts are labels, not items, so the
    ``rate:<key>`` metric pools them across items (49/51 sentences, not a mean of per-item shares).
    With no countable labels the scorer does not apply to the item.
    """

    name = "label-rate"
    counting = True

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, {"field", "positive", "exclude"}, self.name)
        field = options.get("field")
        if not isinstance(field, str) or not field:
            raise ScorerConfigError("label-rate: option 'field' must be a non-empty string")
        positive = _labels(options.get("positive"), "positive", required=True)
        exclude = _labels(options.get("exclude", []), "exclude", required=False)
        if positive & exclude:
            raise ScorerConfigError("label-rate: a label cannot be both positive and excluded")
        if isinstance(expected, bool) or not isinstance(expected, int | float) or not 0 <= expected <= 1:
            raise ScorerConfigError("label-rate: expected must be a number in [0, 1] (minimum share)")
        raw = output.fields.get(field)
        if raw is None:
            return Outcome.not_applicable(f"{field} not reported")
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            return Outcome(0.0, False, f"{field} is not a list of labels", hits=0, total=0)
        counted = [x for x in raw if x not in exclude]
        if not counted:
            return Outcome.not_applicable(f"no countable labels in {field}")
        hits = sum(1 for x in counted if x in positive)
        share = hits / len(counted)
        ok = round(share, 6) >= round(float(expected), 6)
        detail = f"{hits}/{len(counted)} positive" + ("" if ok else f", need >= {float(expected):g}")
        return Outcome(share, ok, detail, hits=hits, total=len(counted))


def _labels(value: Any, name: str, *, required: bool) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ScorerConfigError(f"label-rate: option {name!r} must be a list of non-empty strings")
    if required and not value:
        raise ScorerConfigError(f"label-rate: option {name!r} must not be empty")
    return set(value)
