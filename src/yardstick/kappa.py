"""Cohen's kappa and judge calibration (PRD §4 "Judge calibration", Phase 3; D-39).

``cohen_kappa`` follows Footnote's ``cohenKappa`` (its D-36): unweighted over a given label set, p_e from
each rater's marginals, and ``None`` (not 0 or 1) when p_e = 1, because kappa is 0/0 there.

``calibrate`` joins human grade sets to a judge's labels by unit key and reports kappa per set and pooled
over all sets. A calibration is for one judge identity (model + prompt hash); the gate uses the pooled kappa
(YS-05).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from yardstick.grades import GradeSet, labels_of
from yardstick.judge.base import JudgeIdentity
from yardstick.models import LLM_JUDGE, Run


@dataclass(frozen=True)
class KappaResult:
    kappa: float | None
    observed: float
    expected: float
    n: int


def cohen_kappa(a: Sequence[str], b: Sequence[str], labels: Sequence[str]) -> KappaResult:
    if len(a) != len(b):
        raise ValueError(f"kappa: {len(a)} vs {len(b)} ratings")
    if not a:
        raise ValueError("kappa: no ratings")
    for x in (*a, *b):
        if x not in labels:
            raise ValueError(f"kappa: label {x} not in [{', '.join(labels)}]")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return KappaResult(kappa, observed, expected, n)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Disagreement(_Frozen):
    key: str
    ref: str
    human: str
    judge: str


class KappaStat(_Frozen):
    name: str
    #: Graded units with a usable judge label.
    n: int
    #: Graded units the judge has no usable label for (not in the run, invalid, or skipped by the budget).
    missing: int
    observed: float | None
    expected: float | None
    kappa: float | None
    human_counts: dict[str, int]
    judge_counts: dict[str, int]
    disagreements: list[Disagreement]


class Calibration(_Frozen):
    """Kappa of one judge (model + prompt hash) against human grades. ``pooled`` covers every set given."""

    judge_model: str
    prompt_hash: str
    judge_source: str
    labels: list[str]
    sets: list[KappaStat]
    pooled: KappaStat

    def matches(self, model: str, prompt_hash: str) -> bool:
        return self.judge_model == model and self.prompt_hash == prompt_hash


def _stat(
    name: str, grade_sets: Sequence[GradeSet], verdicts: Mapping[str, str | None], labels: list[str]
) -> KappaStat:
    pairs: list[tuple[str, str, str, str]] = []  # key, ref, human, judge
    missing = 0
    for gs in grade_sets:
        for g in gs.grades:
            v = verdicts.get(g.key)
            if v is None:
                missing += 1
                continue
            pairs.append((g.key, g.ref, g.label, v))
    if not pairs:
        return KappaStat(
            name=name,
            n=0,
            missing=missing,
            observed=None,
            expected=None,
            kappa=None,
            human_counts={lab: 0 for lab in labels},
            judge_counts={lab: 0 for lab in labels},
            disagreements=[],
        )
    k = cohen_kappa([p[2] for p in pairs], [p[3] for p in pairs], labels)
    return KappaStat(
        name=name,
        n=k.n,
        missing=missing,
        observed=k.observed,
        expected=k.expected,
        kappa=k.kappa,
        human_counts={lab: sum(1 for p in pairs if p[2] == lab) for lab in labels},
        judge_counts={lab: sum(1 for p in pairs if p[3] == lab) for lab in labels},
        disagreements=[
            Disagreement(key=p[0], ref=p[1], human=p[2], judge=p[3]) for p in pairs if p[2] != p[3]
        ],
    )


def calibrate(
    grade_sets: Sequence[GradeSet], verdicts: Mapping[str, str | None], identity: JudgeIdentity
) -> Calibration:
    if not grade_sets:
        raise ValueError("calibrate: no grade sets")
    labels = labels_of(grade_sets)
    names = [gs.name for gs in grade_sets]
    if len(set(names)) != len(names):
        raise ValueError(f"grade set names must be unique: {names}")
    sets = [_stat(gs.name, [gs], verdicts, labels) for gs in grade_sets]
    return Calibration(
        judge_model=identity.model,
        prompt_hash=identity.prompt_hash,
        judge_source=identity.source,
        labels=labels,
        sets=sets,
        pooled=_stat("pooled", grade_sets, verdicts, labels),
    )


def verdicts_from_run(run: Run, key: str) -> tuple[JudgeIdentity, dict[str, str | None]]:
    """The judge identity and per-unit labels an ``llm-judge`` scorer key stored in a run."""
    rec = run.judges.get(key)
    if rec is None:
        raise ValueError(f"run {run.run_id} has no llm-judge record for key {key!r}")
    out: dict[str, str | None] = {}
    for item in run.items:
        for s in item.scores:
            if s.key == key and s.scorer == LLM_JUDGE and s.labels is not None:
                for idx, label in enumerate(s.labels):
                    out[f"{item.item_id}:{idx}"] = label
    return JudgeIdentity(model=rec.model, prompt_hash=rec.prompt_hash, source=rec.source), out


def calibration_json(c: Calibration) -> str:
    return json.dumps(c.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def load_calibration(path: Path) -> Calibration:
    return Calibration.model_validate(json.loads(path.read_text(encoding="utf-8")))


def fmt_stat(s: KappaStat) -> str:
    """One line for terminals and reports."""
    if s.n == 0:
        return f"{s.name}: n 0 ({s.missing} without a usable verdict), kappa not computed"
    kappa = "undefined (p_e = 1)" if s.kappa is None else f"{s.kappa:.2f}"
    assert s.observed is not None and s.expected is not None
    return (
        f"{s.name}: n {s.n} ({s.missing} without a usable verdict), raw agreement {s.observed:.0%}, "
        f"p_e {s.expected:.3f}, kappa {kappa}"
    )
