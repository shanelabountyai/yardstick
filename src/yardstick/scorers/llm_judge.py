"""``llm-judge`` scorer (PRD §3, Phase 3): a judge labels each unit of an output against a rubric.

Options:

- ``rubric`` (required): what the judge grades against.
- ``labels`` (required): the label set, e.g. ``[supported, partial, unsupported]``.
- ``positive`` (required): labels that count as hits.
- ``units_field`` (optional): a list field in ``Output.fields``; each element is one unit (key
  ``<item id>:<index>``). Without it the whole output text is one unit (index 0).

``expected`` is the minimum share of positive units for the item (like ``label-rate``). Counts are units, so
``rate:<key>`` pools them across items. A unit with no valid label, or one the budget cap stopped, is left out of
the count and named in the detail. The scorer needs a :class:`JudgeSession` (the runner passes one); it is always
report-only at item level (D-36), and a gate rule on its rate is governed by YS-05.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from yardstick.hashing import canonical_json
from yardstick.judge.base import Judge, JudgeIdentity, JudgeRequest
from yardstick.judge.budget import Budget
from yardstick.models import LLM_JUDGE, Item, JudgeRecord, Output
from yardstick.scorers.base import Outcome, ScorerConfigError, unknown_options

_OPTIONS = {"rubric", "labels", "positive", "units_field"}


@dataclass(frozen=True)
class JudgeOptions:
    rubric: str
    labels: tuple[str, ...]
    positive: frozenset[str]
    units_field: str | None


def parse_options(options: dict[str, Any]) -> JudgeOptions:
    unknown_options(options, _OPTIONS, LLM_JUDGE)
    rubric = options.get("rubric")
    if not isinstance(rubric, str) or not rubric.strip():
        raise ScorerConfigError("llm-judge: option 'rubric' must be a non-empty string")
    labels = options.get("labels")
    if (
        not isinstance(labels, list)
        or not labels
        or not all(isinstance(x, str) and x for x in labels)
        or len(set(labels)) != len(labels)
    ):
        raise ScorerConfigError("llm-judge: option 'labels' must be a non-empty list of distinct strings")
    positive = options.get("positive")
    if not isinstance(positive, list) or not positive or not all(isinstance(x, str) for x in positive):
        raise ScorerConfigError("llm-judge: option 'positive' must be a non-empty list of labels")
    if not set(positive) <= set(labels):
        raise ScorerConfigError("llm-judge: every 'positive' label must be in 'labels'")
    units_field = options.get("units_field")
    if units_field is not None and (not isinstance(units_field, str) or not units_field):
        raise ScorerConfigError("llm-judge: option 'units_field' must be a non-empty string")
    return JudgeOptions(rubric, tuple(labels), frozenset(positive), units_field)


class LlmJudge:
    """Registry entry. Scoring goes through :meth:`JudgeSession.score`; called directly it refuses."""

    name = LLM_JUDGE
    counting = True

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        raise ScorerConfigError("llm-judge needs a judge: pass --judge and --judge-budget-usd to `run` (D-34)")


@dataclass
class _Tally:
    identity: JudgeIdentity
    calls: int = 0
    judged: int = 0
    invalid: int = 0
    skipped: int = 0


@dataclass
class JudgeSession:
    """One judge and one budget for a whole run, shared by every ``llm-judge`` scorer key in the suite."""

    judge: Judge
    budget: Budget
    _tallies: dict[str, _Tally] = field(default_factory=dict)

    def score(
        self, key: str, item: Item, expected: Any, output: Output, options: dict[str, Any]
    ) -> tuple[Outcome, list[str | None]]:
        opts = parse_options(options)
        if isinstance(expected, bool) or not isinstance(expected, int | float) or not 0 <= expected <= 1:
            raise ScorerConfigError("llm-judge: expected must be a number in [0, 1] (minimum share)")
        tally = self._tally(key, opts)
        units = _units(output, opts.units_field)
        if units is None:
            return Outcome.not_applicable(f"{opts.units_field} not reported"), []
        if not units:
            return Outcome.not_applicable("no units to judge"), []
        labels: list[str | None] = []
        invalid = skipped = 0
        for idx, text in enumerate(units):
            req = JudgeRequest(item.id, idx, text, item.input, opts.rubric, opts.labels)
            estimate = self.judge.estimate_usd(req)
            if not self.budget.allows(estimate):
                labels.append(None)
                skipped += 1
                continue
            reply = self.judge.judge(req)
            self.budget.charge(estimate, reply.cost_usd)
            tally.calls += 1
            label = reply.label if reply.label in opts.labels else None
            labels.append(label)
            if label is None:
                invalid += 1
        tally.invalid += invalid
        tally.skipped += skipped
        counted = [x for x in labels if x is not None]
        tally.judged += len(counted)
        notes = []
        if invalid:
            notes.append(f"{invalid} without a valid label")
        if skipped:
            notes.append(f"{skipped} not judged: budget cap reached")
        if not counted:
            return Outcome(0.0, False, "; ".join(notes) or "nothing judged", hits=0, total=0), labels
        hits = sum(1 for x in counted if x in opts.positive)
        share = hits / len(counted)
        ok = round(share, 6) >= round(float(expected), 6)
        detail = f"{hits}/{len(counted)} positive" + ("" if ok else f", need >= {float(expected):g}")
        if notes:
            detail += f" ({'; '.join(notes)})"
        return Outcome(share, ok, detail, hits=hits, total=len(counted)), labels

    def _tally(self, key: str, opts: JudgeOptions) -> _Tally:
        if key not in self._tallies:
            self._tallies[key] = _Tally(self.judge.identity(opts.rubric, opts.labels))
        return self._tallies[key]

    def records(self) -> dict[str, JudgeRecord]:
        return {
            key: JudgeRecord(
                model=t.identity.model,
                prompt_hash=t.identity.prompt_hash,
                source=t.identity.source,
                cap_usd=round(self.budget.cap_usd, 6),
                spent_usd=round(self.budget.spent_usd, 6),
                calls=t.calls,
                units_judged=t.judged,
                units_invalid=t.invalid,
                units_skipped_budget=t.skipped,
                overrun=self.budget.overrun,
            )
            for key, t in sorted(self._tallies.items())
        }


def _units(output: Output, units_field: str | None) -> list[str] | None:
    if units_field is None:
        return [output.text] if output.text.strip() else []
    raw = output.fields.get(units_field)
    if raw is None:
        return None
    if not isinstance(raw, list):
        return [canonical_json(raw)]
    return [x if isinstance(x, str) else canonical_json(x) for x in raw]
