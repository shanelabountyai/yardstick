"""YS-05 through ``label-rate`` (review item 4, D-79) and the calibration minimum ``min_graded`` (D-80)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tests.helpers import CLOCK, ROOT, TARGET
from tests.invariants.test_ys05_judge_report_only import calibration, gate, judged_run
from yardstick.adapters.base import RunMeta
from yardstick.cli import app
from yardstick.gate import evaluate
from yardstick.kappa import Calibration, KappaStat
from yardstick.models import GateConfig, GateRule, Item, JudgePolicy, Output, ScorerSpec, Suite
from yardstick.runner import build_run

LABEL_JUDGE = ScorerSpec(
    name="label-rate", key="sup", report_only=True, judge=True, options={"field": "v", "positive": ["good"]}
)
SUITE = Suite(
    name="labels",
    scorers=[ScorerSpec(name="exact"), LABEL_JUDGE],
    items=[Item(id=f"i{k}", input=k, expected={"exact": "ok", "sup": 1.0}) for k in range(10)],
)
OUTS = {f"i{k}": Output(text="ok", fields={"v": ["good"]}) for k in range(10)}
META = RunMeta(judge_model="judge-m", judge_prompt_hash="abc123")
RULES = GateConfig(rules=[GateRule(metric="pass_rate", floor=0.9), GateRule(metric="rate:sup", floor=0.9)])


def test_judge_derived_label_rate_is_report_only_without_a_calibration() -> None:
    run = build_run(SUITE, TARGET, OUTS, clock=CLOCK, label_judge=META)
    assert run.label_judges["sup"].model == "judge-m"
    res = evaluate(RULES, run)
    assert res.rules[1].report_only and "no calibration for judge-m prompt abc123" in res.rules[1].note


def test_judge_derived_label_rate_gates_with_a_good_calibration() -> None:
    run = build_run(SUITE, TARGET, OUTS, clock=CLOCK, label_judge=META)
    res = evaluate(RULES, run, calibrations=[calibration(0.8)])
    assert not res.rules[1].report_only and res.passed


def test_unreported_judge_identity_is_unknown() -> None:
    run = build_run(SUITE, TARGET, OUTS, clock=CLOCK)
    assert run.label_judges["sup"].model is None
    res = evaluate(RULES, run, calibrations=[calibration(0.8)])
    assert res.rules[1].report_only and "not reported by the target" in res.rules[1].note


def test_unmarked_label_rate_keeps_gating_and_hashes() -> None:
    plain = ScorerSpec(
        name="label-rate", key="sup", report_only=True, options={"field": "v", "positive": ["g"]}
    )
    assert "judge" not in plain.model_dump(mode="json")  # additive: no other suite hash moves


@pytest.mark.parametrize(
    "spec",
    [
        ScorerSpec(name="exact", judge=True, report_only=True),
        ScorerSpec(name="label-rate", key="s", judge=True, options={"field": "v", "positive": ["g"]}),
    ],
)
def test_judge_flag_only_on_report_only_label_rate(spec: ScorerSpec) -> None:
    with pytest.raises(ValidationError):
        Suite(name="x", scorers=[spec], items=[Item(id="a", input=1, expected={spec.expected_key: 1.0})])


def _small(n: int, kappa: float = 1.0) -> Calibration:
    stat = KappaStat(
        name="pooled",
        n=n,
        missing=0,
        observed=1.0,
        expected=0.5,
        kappa=kappa,
        human_counts={},
        judge_counts={},
        disagreements=[],
    )
    return Calibration(
        judge_model="judge-m", prompt_hash="abc123", judge_source="t", labels=["a"], sets=[stat], pooled=stat
    )


def test_a_calibration_below_min_graded_is_unknown() -> None:
    res = evaluate(gate(), judged_run(10), calibrations=[_small(3)])
    assert res.rules[1].report_only
    assert "from n 3 graded units < min_graded 30, treated as unknown" in res.rules[1].note


def test_min_graded_boundary_and_override() -> None:
    assert JudgePolicy().min_graded == 30
    assert not evaluate(gate(), judged_run(10), calibrations=[_small(30)]).rules[1].report_only
    cfg = GateConfig(rules=gate().rules, judge=JudgePolicy(min_graded=3))
    assert not evaluate(cfg, judged_run(10), calibrations=[_small(3)]).rules[1].report_only
    with pytest.raises(ValidationError):
        JudgePolicy(min_graded=0)


FN = ROOT / "fixtures" / "footnote"
JUDGED_CELL = FN / "results" / "answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json"


def test_footnote_support_rule_is_report_only_on_the_judged_cell(tmp_path: Path) -> None:
    """The review's reproduction: the committed Footnote gate no longer lets the Opus verdicts gate."""
    runner = CliRunner()
    out = tmp_path / "fn.json"
    r = runner.invoke(
        app,
        [
            "run", "--suite", str(FN / "suite.yaml"), "--mapping", "footnote", "--results", str(JUDGED_CELL),
            "--target-name", "hybrid", "--no-git", "--fixed-clock", "2026-11-14T00:00:00Z", "--out", str(out),
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    run = json.loads(out.read_text())
    assert run["label_judges"]["support"]["model"] == "claude-opus-5-5"
    g = runner.invoke(app, ["gate", str(out), "-c", str(ROOT / "fixtures" / "gates" / "footnote.yaml")])
    line = next(x for x in g.output.splitlines() if "rate:support[A+M+V]" in x)
    assert line.startswith("(pass)")
    assert "report-only (YS-05): judge kappa 0.17 (n 40) < floor 0.6" in line
