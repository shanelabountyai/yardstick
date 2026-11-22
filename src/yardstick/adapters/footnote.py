"""Footnote mapping (PRD §4): Footnote's ``eval/results/answers-*.json`` rows and ``eval/golden.json``.

Row fields used: ``id``, ``slice``, ``status`` (answered / partial / refused), ``refusal`` (code or null),
``gate.score`` (top dense cosine; null for fts), ``verdicts`` (judge label per sentence). File level:
``model``, ``spentUsd``, and on judged files ``judge`` and ``judgePromptHash``. Mapped to:

- ``refused`` = ``status == "refused"`` (so "answered or partial" = not refused, as in Footnote's scorecard);
- fields ``status``, ``refusal_code``, ``gate_score``, ``verdicts`` and the derived ``pre_call`` = refused
  with ``NO_RELEVANT_PASSAGE``, the only code Footnote emits before a model call (its
  ``noRelevantPassage()``, D-28);
- run model and run-level cost (``spentUsd``; Footnote reports no per-item cost or latency, so those stay
  "not reported");
- the judge identity behind ``verdicts`` (``judge``, ``judgePromptHash``), recorded for the judge-derived
  ``support`` key so YS-05 applies to it (D-79).

``theta_prime`` replays Footnote's scorecard ``atTheta``: a row whose stored gate score is below theta'
becomes a pre-call ``NO_RELEVANT_PASSAGE`` refusal with no sentences; rows without a score (fts) never change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from yardstick.adapters.results_file import RefusedRule, ResultsFileAdapter, ResultsMapping
from yardstick.judge.recorded import VerdictFile
from yardstick.models import Descriptions, Item, ScorerSpec, Suite

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
    judge_model="judge",
    judge_prompt_hash="judgePromptHash",
)

SUITE_NAME = "footnote-golden"
JUDGED_SUITE_NAME = "footnote-golden-judged"
JUDGE_KEY = "judge"
#: The grading rubric Footnote's grade sheets give the human grader (eval/grades.md). Footnote's own judge
#: prompt (JUDGE_SYSTEM_PROMPT, hash 071689f33855) is not in the answers files; a replayed judge keeps that
#: hash.
JUDGE_RUBRIC = (
    "supported: every claim in the sentence is stated by the cited quotes \u2014 each number, year, date, "
    "threshold, condition and exception, and the edition or year the sentence attributes it to. "
    "partial: some claims are stated by the quotes and at least one is not. "
    "unsupported: the main claim is not stated by the quotes, or the quotes contradict it."
)
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
        judge=True,  # the verdicts are Footnote's sentence judge's labels: YS-05 applies (D-79)
        options={"field": "verdicts", "positive": ["supported"], "exclude": ["schema_invalid"]},
    ),
]


#: The report's Key (decision 5 (b), D-89). The `refusal` key stays as generated (D-23); its label says what a
#: hit means, because "refusal 86%" otherwise reads as a refusal rate.
SCORER_DESCRIPTIONS = {
    "refusal": "hit = the expected outcome: answered or partial where the golden set expects an answer, "
    "refused where it expects a refusal. On A+M a hit means answered or partial; it is not a refusal rate.",
    "out-of-scope": "hit = refused with code OUT_OF_SCOPE, on the item that expects it.",
    "refusal-code": "report-only. hit = refused with the refusal code the golden set expects (U items).",
    "pre-call": "report-only. hit = refused before any model call (NO_RELEVANT_PASSAGE, D-28).",
    "support": "report-only, judge-derived. Share of answer sentences Footnote's judge labelled supported "
    "(schema_invalid left out); it gates only when that judge is calibrated (YS-05).",
    JUDGE_KEY: "report-only llm-judge. Footnote's committed sentence verdicts, replayed; it gates only when "
    "the judge is calibrated (YS-05).",
}
SLICE_DESCRIPTIONS = {
    "A": "answerable (golden slice A): the expected outcome is an answer.",
    "M": "answerable (golden slice M): the expected outcome is an answer.",
    "V": "edition questions (golden slice V): the answer must label the edition it cites.",
    "P": "golden slice P: answer-or-refusal cases asked under different caller roles "
    "(callerRole in the input).",
    "U": "unanswerable (golden slice U): the expected outcome is a refusal.",
    "A+M": 'A and M together: Footnote\'s scorecard row "Answered or partial (A, M)".',
    "A+M+V": "A, M and V together: the slices the sentence-support rate is reported on.",
}


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


#: Phase 3: the judge as an ``llm-judge`` scorer. Footnote's answers files hold no sentence text, only the
#: judge's verdict per sentence, so the units are the positions in ``verdicts`` and only a replayed judge can
#: label them (D-41). Every item gets it, because graded sentences include P-slice answers; refused answers
#: have no units.
JUDGE_SCORER = ScorerSpec(
    name="llm-judge",
    key=JUDGE_KEY,
    report_only=True,
    options={
        "rubric": JUDGE_RUBRIC,
        "labels": ["supported", "partial", "unsupported"],
        "positive": ["supported"],
        "units_field": "verdicts",
    },
)


def suite_from_golden(golden: list[dict[str, Any]], *, judged: bool = False) -> Suite:
    """Golden set -> suite ``footnote-golden`` (scorers per slice: see docs/PHASE2_PLAN.md). ``judged`` adds
    the ``llm-judge`` scorer as suite ``footnote-golden-judged`` (Phase 3)."""
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
        if judged:
            expected[JUDGE_KEY] = 1.0
        items.append(
            Item(
                id=str(g["id"]),
                input={"question": g["question"], "callerRole": g["callerRole"]},
                expected=expected,
                slices=[slice_name, *GROUPS.get(slice_name, ())],
            )
        )
    if judged:
        return Suite(
            name=JUDGED_SUITE_NAME,
            description="Footnote's golden set with its sentence judge as llm-judge "
            "(`yardstick footnote suite --judged`).",
            scorers=[*SCORERS, JUDGE_SCORER],
            items=items,
            descriptions=Descriptions(scorers=SCORER_DESCRIPTIONS, slices=SLICE_DESCRIPTIONS),
        )
    return Suite(
        name=SUITE_NAME,
        description="Footnote's golden set (eval/golden.json), mapped by `yardstick footnote suite`.",
        scorers=SCORERS,
        items=items,
        descriptions=Descriptions(
            scorers={k: v for k, v in SCORER_DESCRIPTIONS.items() if k != JUDGE_KEY},
            slices=SLICE_DESCRIPTIONS,
        ),
    )


def verdicts_from_answers(answers: dict[str, Any], source: str) -> VerdictFile:
    """Footnote's committed judge verdicts as a replayable verdict file: unit key ``<golden id>:<sentence
    index>``; ``schema_invalid`` (a judgment with no usable verdict) becomes ``null``."""
    model = answers.get("judge")
    phash = answers.get("judgePromptHash")
    if not isinstance(model, str) or not isinstance(phash, str):
        raise ValueError("answers file has no judge / judgePromptHash: it was not judged")
    labels = ["supported", "partial", "unsupported"]
    verdicts: dict[str, str | None] = {}
    for row in answers["rows"]:
        for idx, v in enumerate(row.get("verdicts") or []):
            if v != "schema_invalid" and v not in labels:
                raise ValueError(f"{row['id']} sentence {idx}: unknown verdict {v!r}")
            verdicts[f"{row['id']}:{idx}"] = None if v == "schema_invalid" else v
    if not verdicts:
        raise ValueError("answers file has no judge verdicts")
    return VerdictFile(model=model, prompt_hash=phash, source=source, labels=labels, verdicts=verdicts)


def suite_yaml(suite: Suite) -> str:
    """Stable YAML for the generated suite (exclude empty additive defaults, keep key order)."""
    data = suite.model_dump(mode="json")
    cmd = (
        "yardstick footnote suite --judged" if suite.name == JUDGED_SUITE_NAME else "yardstick footnote suite"
    )
    header = f"# Generated by `{cmd}` from Footnote's eval/golden.json. Do not edit.\n"
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
