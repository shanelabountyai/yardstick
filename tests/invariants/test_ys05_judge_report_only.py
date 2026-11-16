"""YS-05: an LLM-judge metric whose judge kappa is below the floor (or unknown) is report-only, never
gating."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import CLOCK, TARGET
from yardstick.gate import evaluate
from yardstick.judge.budget import Budget
from yardstick.judge.recorded import ScriptedJudge
from yardstick.kappa import Calibration, KappaStat
from yardstick.models import GateConfig, GateRule, Item, JudgePolicy, Output, Run, ScorerSpec, Suite
from yardstick.runner import build_run
from yardstick.scorers.llm_judge import JudgeSession

LABELS = ["supported", "partial", "unsupported"]
SUITE = Suite(
    name="ys05",
    scorers=[
        ScorerSpec(name="exact"),
        ScorerSpec(
            name="llm-judge",
            key="judge",
            report_only=True,
            options={"rubric": "r", "labels": LABELS, "positive": ["supported"]},
        ),
    ],
    items=[Item(id=f"i{k}", input=k, expected={"exact": "ok", "judge": 1.0}) for k in range(10)],
)


def judged_run(supported: int, model: str = "judge-m", prompt_hash: str = "abc123") -> Run:
    """10 items that all pass ``exact``; the judge labels the first ``supported`` outputs supported."""
    judge = ScriptedJudge(
        lambda req: "supported" if int(req.item_id[1:]) < supported else "unsupported",
        model=model,
        prompt_hash=prompt_hash,
    )
    outs = {f"i{k}": Output(text="ok") for k in range(10)}
    return build_run(SUITE, TARGET, outs, clock=CLOCK, judge=JudgeSession(judge, Budget(0)))


def calibration(kappa: float | None, model: str = "judge-m", prompt_hash: str = "abc123") -> Calibration:
    stat = KappaStat(
        name="pooled",
        n=40,
        missing=0,
        observed=0.8,
        expected=0.5 if kappa is not None else 1.0,
        kappa=kappa,
        human_counts={},
        judge_counts={},
        disagreements=[],
    )
    return Calibration(
        judge_model=model, prompt_hash=prompt_hash, judge_source="t", labels=LABELS, sets=[stat], pooled=stat
    )


def gate(floor: float = 0.6) -> GateConfig:
    return GateConfig(
        rules=[GateRule(metric="pass_rate", floor=0.9), GateRule(metric="rate:judge", floor=0.9)],
        judge=JudgePolicy(kappa_floor=floor),
    )


@given(
    supported=st.integers(min_value=0, max_value=10),
    kappa=st.one_of(st.none(), st.floats(min_value=-1, max_value=0.599)),
    calibrated=st.booleans(),
)
def test_below_floor_or_unknown_never_changes_the_verdict(
    supported: int, kappa: float | None, calibrated: bool
) -> None:
    run = judged_run(supported)
    cals = [calibration(kappa)] if calibrated else []
    res = evaluate(gate(0.6), run, calibrations=cals)
    judge_rule = res.rules[1]
    assert judge_rule.report_only and "report-only (YS-05)" in judge_rule.note
    # The verdict is exactly the verdict of the other rules, whether the judge rule passes or fails.
    assert res.passed == res.rules[0].passed
    assert res.passed  # every item passes exact, so only the judge could have failed it


@given(supported=st.integers(min_value=0, max_value=10), kappa=st.floats(min_value=0.6, max_value=1))
def test_at_or_above_floor_the_judge_gates(supported: int, kappa: float) -> None:
    res = evaluate(gate(0.6), judged_run(supported), calibrations=[calibration(kappa)])
    assert not res.rules[1].report_only
    assert res.passed == (supported >= 9)


def test_a_calibration_for_another_judge_or_prompt_does_not_count() -> None:
    run = judged_run(0)
    for cal in (calibration(0.9, model="other"), calibration(0.9, prompt_hash="zzz")):
        res = evaluate(gate(), run, calibrations=[cal])
        assert res.rules[1].report_only and "no calibration" in res.rules[1].note
        assert res.passed


def test_two_matching_calibrations_are_ambiguous_so_report_only() -> None:
    res = evaluate(gate(), judged_run(0), calibrations=[calibration(0.9), calibration(0.9)])
    assert res.rules[1].report_only and "give exactly one" in res.rules[1].note


def test_a_gate_with_only_a_demoted_judge_rule_fails_closed() -> None:
    cfg = GateConfig(rules=[GateRule(metric="rate:judge", floor=0.5)])
    res = evaluate(cfg, judged_run(10))
    assert res.rules[0].passed and res.rules[0].report_only
    assert not res.passed and any("nothing gates" in w for w in res.warnings)


def test_the_judge_never_moves_pass_rate_or_mean_score() -> None:
    # llm-judge scores are report-only at item level (D-36): pass rate is the same with any verdicts.
    assert {judged_run(s).items[0].passed for s in (0, 10)} == {True}
    assert evaluate(gate(), judged_run(0)).rules[0].current == 1.0


def test_default_floor_is_d06() -> None:
    assert JudgePolicy().kappa_floor == 0.6
    res = evaluate(
        GateConfig(rules=[GateRule(metric="rate:judge", floor=0.5)]),
        judged_run(10),
        calibrations=[calibration(0.59)],
    )
    assert res.rules[0].report_only and "< floor 0.6" in res.rules[0].note


def test_a_run_without_a_judge_record_is_unknown() -> None:
    run = judged_run(10)
    stripped = run.model_copy(update={"judges": {}})
    res = evaluate(gate(), stripped, calibrations=[calibration(0.9)])
    assert res.rules[1].report_only and "not recorded" in res.rules[1].note
