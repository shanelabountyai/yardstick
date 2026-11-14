"""Gate semantics: the examples table in docs/PHASE1_PLAN.md, plus fail-closed cases."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.helpers import run_from_passes
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule


def passes(n_pass: int, n: int) -> list[bool]:
    return [True] * n_pass + [False] * (n - n_pass)


DROP_RULE = GateConfig(min_items=10, rules=[GateRule(metric="pass_rate", floor=0.85, max_drop=0.02)])


@pytest.mark.parametrize(
    ("base_pass", "n_pass", "n", "expected", "failing_check"),
    [
        (46, 45, 50, True, None),  # 0.92 -> 0.90: drop exactly 0.02 passes (float rounding must not flip it)
        (23, 22, 25, False, "max_drop"),  # 0.92 -> 0.88: drop 0.04
        (3, 3, 3, False, "min_items"),  # 1.00 but only 3 items
        (23, 20, 25, False, "floor"),  # 0.80 < 0.85
    ],
)
def test_plan_examples(
    base_pass: int, n_pass: int, n: int, expected: bool, failing_check: str | None
) -> None:
    baseline = run_from_passes(passes(base_pass, n))
    run = run_from_passes(passes(n_pass, n))
    res = evaluate(DROP_RULE, run, baseline)
    assert res.passed is expected
    if failing_check:
        failed = {c.check for c in res.rules[0].checks if not c.passed}
        assert failing_check in failed


def test_not_reported_metric_fails() -> None:
    run = run_from_passes(passes(12, 12))  # no telemetry
    cfg = GateConfig(min_items=10, rules=[GateRule(metric="latency_p95_ms", max=2000)])
    res = evaluate(cfg, run)
    assert not res.passed
    assert any(c.check == "reported" and not c.passed for c in res.rules[0].checks)


def test_max_drop_without_baseline_fails_closed() -> None:
    run = run_from_passes(passes(12, 12))
    cfg = GateConfig(rules=[GateRule(metric="pass_rate", max_drop=0.02)])
    res = evaluate(cfg, run, None)
    assert not res.passed
    assert res.rules[0].checks[-1].detail == "no baseline"


def test_max_rise_for_latency() -> None:
    base = run_from_passes([True] * 10, latency=[100] * 10)
    slow = run_from_passes([True] * 10, latency=[100] * 5 + [400] * 5)
    cfg = GateConfig(rules=[GateRule(metric="latency_p95_ms", max_rise=100)])
    assert evaluate(cfg, base, base).passed
    assert not evaluate(cfg, slow, base).passed


def test_slice_rule_uses_slice_count() -> None:
    run = run_from_passes(passes(10, 10))
    cfg = GateConfig(min_items=1, rules=[GateRule(metric="pass_rate", slice="missing", floor=0.5)])
    res = evaluate(cfg, run)
    assert not res.passed
    assert res.rules[0].n_items == 0


def test_empty_rules_never_pass() -> None:
    run = run_from_passes(passes(10, 10))
    assert not evaluate(GateConfig(rules=[]), run).passed


def test_rule_validation() -> None:
    with pytest.raises(ValidationError):
        GateRule(metric="pass_rate")
    with pytest.raises(ValidationError):
        GateRule(metric="latency_p95_ms", slice="x", max=1)
    with pytest.raises(ValidationError):
        GateRule(metric="pass_rate", floor=0.5, min_items=0)
    with pytest.raises(ValidationError):
        GateConfig(min_items=0, rules=[])
