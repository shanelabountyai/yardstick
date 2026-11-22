"""PRD-H: items scored only by report-only scorers are "not scored", excluded from pass_rate and mean_score
(review item 12, decision 9 (b))."""

from __future__ import annotations

import json

from tests.helpers import CLOCK, TARGET, run_from_passes
from yardstick import metrics
from yardstick.compare import compare
from yardstick.gate import evaluate
from yardstick.judge.budget import Budget
from yardstick.judge.recorded import ScriptedJudge
from yardstick.models import GateConfig, GateRule, Item, Output, Run, ScorerSpec, Suite
from yardstick.report.markdown import render
from yardstick.runner import build_run
from yardstick.scorers.llm_judge import JudgeSession
from yardstick.suite_io import run_to_json

JUDGE = ScorerSpec(
    name="llm-judge",
    key="j",
    report_only=True,
    options={"rubric": "r", "labels": ["good", "bad"], "positive": ["good"]},
)


def _judge_only(n: int = 10) -> Run:
    suite = Suite(
        name="jo", scorers=[JUDGE], items=[Item(id=f"i{k}", input=k, expected={"j": 1.0}) for k in range(n)]
    )
    outs = {f"i{k}": Output(text="ok") for k in range(n)}
    return build_run(
        suite, TARGET, outs, clock=CLOCK, judge=JudgeSession(ScriptedJudge(lambda r: "good"), Budget(0))
    )


def test_judge_only_suite_is_not_scored_not_zero() -> None:
    run = _judge_only()
    m = metrics.compute(run)
    assert m.pass_rate is None and m.mean_score is None
    assert m.n_not_scored == 10 and m.n_items == 10
    rm = m.rates["j"]
    assert (rm.hits, rm.total) == (10, 10)
    md = render(run)
    assert "## Failing items" not in md
    assert "10 not scored" in md and "Not scored (10)" in md


def test_mixed_suite_scores_only_scored_items() -> None:
    suite = Suite(
        name="mixed",
        scorers=[ScorerSpec(name="exact"), JUDGE],
        items=[Item(id=f"s{k}", input=k, expected={"exact": "ok"}) for k in range(4)]
        + [Item(id=f"u{k}", input=k, expected={"j": 1.0}) for k in range(6)],
    )
    outs = {f"s{k}": Output(text="ok" if k < 3 else "no") for k in range(4)} | {
        f"u{k}": Output(text="ok") for k in range(6)
    }
    run = build_run(
        suite, TARGET, outs, clock=CLOCK, judge=JudgeSession(ScriptedJudge(lambda r: "good"), Budget(0))
    )
    m = metrics.compute(run)
    assert m.pass_rate == 0.75 and m.n_not_scored == 6
    cfg = GateConfig(min_items=5, rules=[GateRule(metric="pass_rate", floor=0.5)])
    res = evaluate(cfg, run)
    assert res.rules[0].n_items == 4 and not res.passed  # YS-02 on what the value is computed from
    assert [i.item_id for i in run.items if i.not_scored] == [f"u{k}" for k in range(6)]


def test_not_scored_items_never_flip() -> None:
    a = _judge_only(3)
    b = _judge_only(3)
    c = compare(a, b)
    assert c.newly_failing == [] and c.newly_passing == []


def test_scored_runs_are_unchanged_on_disk() -> None:
    run = run_from_passes([True, False])
    assert "not_scored" not in json.loads(run_to_json(run))["items"][0]
    old = json.loads(run_to_json(run))
    again = Run.model_validate(old)
    assert all(not i.not_scored for i in again.items)
