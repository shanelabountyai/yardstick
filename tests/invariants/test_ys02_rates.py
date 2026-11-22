"""YS-02 for ``rate:<key>`` rules: items that contributed nothing to the rate (a target error on a counting
scorer, a judge unit skipped by the budget) do not count toward ``min_items`` (D-26, review item 1)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import CLOCK, TARGET
from yardstick import metrics
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule, Item, Output, ScorerSpec, Suite
from yardstick.runner import build_run

LABEL_SUITE_SCORERS = [
    ScorerSpec(name="exact"),
    ScorerSpec(name="label-rate", key="sup", options={"field": "v", "positive": ["good"]}),
]


def _suite(n: int) -> Suite:
    return Suite(
        name="rates",
        scorers=LABEL_SUITE_SCORERS,
        items=[Item(id=f"i{k}", input=k, expected={"exact": "ok", "sup": 0.5}) for k in range(n)],
    )


def _output(kind: str) -> Output | None:
    if kind == "error":
        return Output(error="boom")
    if kind == "missing":
        return None  # no row from the target -> "no output from target", an error
    if kind == "unreported":
        return Output(text="ok")
    return Output(text="ok", fields={"v": ["good"] if kind == "hit" else ["bad"]})


def test_errored_items_do_not_count_toward_rate_min_items() -> None:
    kinds = ["hit"] + ["error"] * 9
    suite = _suite(len(kinds))
    outs = {f"i{k}": o for k, kind in enumerate(kinds) if (o := _output(kind)) is not None}
    run = build_run(suite, TARGET, outs, clock=CLOCK)
    rm = metrics.compute(run).rates["sup"]
    assert (rm.hits, rm.total, rm.n_items) == (1, 1, 1)
    cfg = GateConfig(min_items=8, rules=[GateRule(metric="rate:sup", floor=0.9)])
    res = evaluate(cfg, run)
    assert not res.passed
    assert res.rules[0].n_items == 1


@given(
    kinds=st.lists(
        st.sampled_from(["hit", "miss", "error", "missing", "unreported"]), min_size=1, max_size=30
    ),
    min_items=st.integers(min_value=1, max_value=30),
)
def test_rate_gate_never_passes_below_min_items(kinds: list[str], min_items: int) -> None:
    suite = _suite(len(kinds))
    outs = {f"i{k}": o for k, kind in enumerate(kinds) if (o := _output(kind)) is not None}
    run = build_run(suite, TARGET, outs, clock=CLOCK)
    contributed = sum(1 for k in kinds if k in {"hit", "miss"})
    cfg = GateConfig(min_items=min_items, rules=[GateRule(metric="rate:sup", floor=0.0)])
    res = evaluate(cfg, run)
    assert res.rules[0].n_items == contributed
    if contributed < min_items:
        assert not res.passed


def test_budget_skipped_judge_items_do_not_count_toward_rate_min_items() -> None:
    """The review's case: 10 items, the cap allows 1 call, 9 items are not judged at all."""
    from yardstick.judge.budget import Budget
    from yardstick.judge.recorded import ScriptedJudge
    from yardstick.scorers.llm_judge import JudgeSession

    opts = {"rubric": "r", "labels": ["good", "bad"], "positive": ["good"]}
    suite = Suite(
        name="judged",
        scorers=[
            ScorerSpec(name="exact"),
            ScorerSpec(name="llm-judge", key="j", options=opts, report_only=True),
        ],
        items=[Item(id=f"i{k}", input=k, expected={"exact": "ok", "j": 1.0}) for k in range(10)],
    )
    judge = ScriptedJudge(lambda req: "good", estimate_usd=0.6, cost_usd=0.6)
    outs = {f"i{k}": Output(text="ok") for k in range(10)}
    run = build_run(suite, TARGET, outs, clock=CLOCK, judge=JudgeSession(judge, Budget(1.0)))
    rm = metrics.compute(run).rates["j"]
    assert (rm.hits, rm.total, rm.n_items) == (1, 1, 1)
    res = evaluate(GateConfig(min_items=8, rules=[GateRule(metric="rate:j", floor=0.9)]), run)
    assert res.rules[0].n_items == 1 and not res.rules[0].passed
