"""Footnote mapping (PRD §4): Footnote's ``eval/results/answers-*.json`` rows and ``eval/golden.json``.

Row fields used: ``id``, ``slice``, ``status`` (answered / partial / refused), ``refusal`` (code or null),
``gate.score`` (top dense cosine; null for fts), ``verdicts`` (judge label per sentence). File level:
``model``, ``spentUsd``. Mapped to:

- ``refused`` = ``status == "refused"`` (so "answered or partial" = not refused, as in Footnote's scorecard);
- fields ``status``, ``refusal_code``, ``gate_score``, ``verdicts`` and the derived ``pre_call`` = refused
  with ``NO_RELEVANT_PASSAGE``, the only code Footnote emits before a model call (its
  ``noRelevantPassage()``, D-28);
- run model and run-level cost (``spentUsd``; Footnote reports no per-item cost or latency, so those stay
  "not reported").

``theta_prime`` replays Footnote's scorecard ``atTheta``: a row whose stored gate score is below theta'
becomes a pre-call ``NO_RELEVANT_PASSAGE`` refusal with no sentences; rows without a score (fts) never change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from yardstick.adapters.results_file import RefusedRule, ResultsFileAdapter, ResultsMapping
from yardstick.models import Item, ScorerSpec, Suite

NO_RELEVANT_PASSAGE = "NO_RELEVANT_PASSAGE"
OUT_OF_SCOPE = "OUT_OF_SCOPE"

FOOTNOTE_MAPPING = ResultsMapping(
    rows="rows",
    id="id",
    refused=RefusedRule(path="status", values=["refused"]),
    fields={
        "status": "status",
        "refusal_code": "refusal",
        "gate_score": "gate.score",
        "verdicts": "verdicts",
    },
    model="model",
    run_cost_usd="spentUsd",
)

SUITE_NAME = "footnote-golden"
#: Slice groups the scorecard reports on, added beside each item's own slice.
GROUPS: dict[str, tuple[str, ...]] = {"A": ("A+M", "A+M+V"), "M": ("A+M", "A+M+V"), "V": ("A+M+V",)}

SCORERS = [
    ScorerSpec(name="refusal-expected", key="refusal"),
    ScorerSpec(name="field-equals", key="out-of-scope"),
    ScorerSpec(name="field-equals", key="refusal-code", report_only=True),
    ScorerSpec(name="field-equals", key="pre-call", report_only=True),
    ScorerSpec(
        name="label-rate",
        key="support",
        report_only=True,
        options={"field": "verdicts", "positive": ["supported"], "exclude": ["schema_invalid"]},
    ),
]


def text_of(row: dict[str, Any]) -> str:
    status = str(row.get("status"))
    code = row.get("refusal")
    return status if code is None else f"{status} ({code})"


class FootnoteAdapter(ResultsFileAdapter):
    def __init__(self, name: str, path: Path, theta_prime: float | None = None) -> None:
        label = "footnote" if theta_prime is None else f"footnote, theta' {theta_prime:g}"
        super().__init__(name, path, FOOTNOTE_MAPPING, label)
        self.theta_prime = theta_prime

    def transform_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return apply_theta(row, self.theta_prime)

    def derived_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"pre_call": row.get("status") == "refused" and row.get("refusal") == NO_RELEVANT_PASSAGE}


def apply_theta(row: dict[str, Any], theta_prime: float | None) -> dict[str, Any]:
    """Footnote's ``atTheta``: below theta' the answer is a refusal before any model call."""
    if theta_prime is None:
        return row
    gate = row.get("gate")
    score = gate.get("score") if isinstance(gate, dict) else None
    if not isinstance(score, int | float) or isinstance(score, bool) or score >= theta_prime:
        return row
    return {**row, "status": "refused", "refusal": NO_RELEVANT_PASSAGE, "verdicts": [], "droppedSentences": 0}


def suite_from_golden(golden: list[dict[str, Any]]) -> Suite:
    """Golden set -> suite ``footnote-golden`` (scorers per slice: see docs/PHASE2_PLAN.md)."""
    items = []
    for g in golden:
        slice_name = str(g["slice"])
        refusal = g["expected"].get("refusal")
        expected: dict[str, Any] = {"pre-call": {"pre_call": True}}
        if refusal == OUT_OF_SCOPE:
            expected["out-of-scope"] = {"refusal_code": OUT_OF_SCOPE}
        else:
            expected["refusal"] = refusal is not None
        if slice_name == "U" and refusal not in (None, OUT_OF_SCOPE):
            expected["refusal-code"] = {"refusal_code": refusal}
        if slice_name in {"A", "M", "V"}:
            expected["support"] = 1.0
        items.append(
            Item(
                id=str(g["id"]),
                input={"question": g["question"], "callerRole": g["callerRole"]},
                expected=expected,
                slices=[slice_name, *GROUPS.get(slice_name, ())],
            )
        )
    return Suite(
        name=SUITE_NAME,
        description="Footnote's golden set (eval/golden.json), mapped by `yardstick footnote suite`.",
        scorers=SCORERS,
        items=items,
    )


def suite_yaml(suite: Suite) -> str:
    """Stable YAML for the generated suite (exclude empty additive defaults, keep key order)."""
    data = suite.model_dump(mode="json")
    header = "# Generated from fixtures/footnote/golden.json by `yardstick footnote suite`. Do not edit.\n"
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
