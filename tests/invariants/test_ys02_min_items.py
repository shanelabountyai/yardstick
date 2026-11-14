"""YS-02: a gate never passes with fewer items than its ``min_items``."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import run_from_passes
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule


@given(
    passes=st.lists(st.booleans(), min_size=1, max_size=40),
    min_items=st.integers(min_value=1, max_value=60),
    rule_min=st.one_of(st.none(), st.integers(min_value=1, max_value=60)),
    floor=st.floats(min_value=0, max_value=1),
)
def test_gate_never_passes_below_min_items(
    passes: list[bool], min_items: int, rule_min: int | None, floor: float
) -> None:
    run = run_from_passes(passes)
    cfg = GateConfig(
        min_items=min_items, rules=[GateRule(metric="pass_rate", floor=floor, min_items=rule_min)]
    )
    res = evaluate(cfg, run, run)
    effective = rule_min if rule_min is not None else min_items
    if len(passes) < effective:
        assert not res.passed
    for rr in res.rules:
        if rr.passed:
            assert rr.n_items >= rr.min_items


@given(passes=st.lists(st.booleans(), min_size=1, max_size=30), extra=st.integers(min_value=1, max_value=30))
def test_perfect_but_small_run_fails(passes: list[bool], extra: int) -> None:
    perfect = run_from_passes([True] * len(passes))
    cfg = GateConfig(
        min_items=len(passes) + extra,
        rules=[GateRule(metric="pass_rate", floor=0.0), GateRule(metric="mean_score", max_drop=1.0)],
    )
    assert not evaluate(cfg, perfect, perfect).passed


def test_slice_min_items_counts_slice_not_run() -> None:
    run = run_from_passes([True] * 20)
    cfg = GateConfig(min_items=5, rules=[GateRule(metric="pass_rate", slice="nope", floor=0.0)])
    assert not evaluate(cfg, run).passed
