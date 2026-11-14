"""Rate metrics, report-only scores and the Phase 2 field scorers."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from tests.helpers import CLOCK, TARGET
from yardstick import gate as gate_mod
from yardstick import metrics
from yardstick.compare import compare
from yardstick.models import GateConfig, GateRule, Item, Output, Score, ScorerSpec, Suite
from yardstick.runner import build_run
from yardstick.scorers import ScorerConfigError, get_scorer

LABELS = ["supported", "partial", "unsupported", "schema_invalid"]
LR_OPTS = {"field": "verdicts", "positive": ["supported"], "exclude": ["schema_invalid"]}


def _suite(n: int, *, report_only: bool) -> Suite:
    return Suite(
        name="r",
        scorers=[
            ScorerSpec(name="exact"),
            ScorerSpec(name="label-rate", key="support", options=LR_OPTS, report_only=report_only),
        ],
        items=[
            Item(id=f"i{k}", input=k, expected={"exact": "ok", "support": 1.0}, slices=["s"])
            for k in range(n)
        ],
    )


_item = st.tuples(st.booleans(), st.lists(st.sampled_from(LABELS), max_size=5))


@given(st.lists(_item, min_size=1, max_size=12))
def test_rate_pools_label_counts(rows: list[tuple[bool, list[str]]]) -> None:
    suite = _suite(len(rows), report_only=True)
    outputs = {
        f"i{k}": Output(text="ok" if ok else "no", fields={"verdicts": v}) for k, (ok, v) in enumerate(rows)
    }
    m = metrics.compute(build_run(suite, TARGET, outputs, clock=CLOCK))
    counted = [x for _, v in rows for x in v if x != "schema_invalid"]
    hits = sum(1 for x in counted if x == "supported")
    rm = m.rate("support")
    if not counted:
        assert rm is None and m.value("rate:support") is None
    else:
        assert rm is not None and (rm.hits, rm.total) == (hits, len(counted))
        assert rm.value == round(hits / len(counted), 6) and 0 <= rm.value <= 1
        assert m.value("rate:support", "s") == rm.value
    # exact applies to every item: its rate equals the item pass rate (report-only support is ignored).
    assert m.value("rate:exact") == m.pass_rate


@given(st.lists(_item, min_size=1, max_size=12))
def test_report_only_scores_never_change_item_pass_or_score(rows: list[tuple[bool, list[str]]]) -> None:
    outputs = {
        f"i{k}": Output(text="ok" if ok else "no", fields={"verdicts": v}) for k, (ok, v) in enumerate(rows)
    }
    with_ro = build_run(_suite(len(rows), report_only=True), TARGET, outputs, clock=CLOCK)
    for item, (ok, _) in zip(with_ro.items, rows, strict=True):
        assert item.passed is ok
        assert item.score == (1.0 if ok else 0.0)


def test_gating_label_rate_does_decide_pass() -> None:
    outputs = {"i0": Output(text="ok", fields={"verdicts": ["supported", "partial"]})}
    run = build_run(_suite(1, report_only=False), TARGET, outputs, clock=CLOCK)
    assert run.items[0].passed is False
    assert run.items[0].score == 0.75


def test_target_error_counts_no_phantom_labels() -> None:
    run = build_run(_suite(2, report_only=True), TARGET, {"i0": Output(error="boom")}, clock=CLOCK)
    m = metrics.compute(run)
    assert m.rate("support") is not None
    assert (m.rate("support").hits, m.rate("support").total) == (0, 0)  # type: ignore[union-attr]
    assert m.value("rate:support") is None
    assert m.value("rate:exact") == 0.0


def test_score_counts_validation() -> None:
    with pytest.raises(ValidationError):
        Score(key="k", scorer="s", score=1, passed=True, hits=1)
    with pytest.raises(ValidationError):
        Score(key="k", scorer="s", score=1, passed=True, hits=3, total=2)
    assert Score(key="k", scorer="s", score=0, passed=False).counts() == (0, 1)


def _fe(expected: Any, fields: dict[str, Any]) -> tuple[bool, str]:
    o = get_scorer("field-equals")(expected, Output(fields=fields), {})
    return o.passed, o.detail


def test_field_equals() -> None:
    assert _fe({"a": 1, "b": "x"}, {"a": 1, "b": "x", "c": 2}) == (True, "")
    ok, detail = _fe({"a": 1}, {"a": 2})
    assert not ok and "expected 1, got 2" in detail
    ok, detail = _fe({"a": None}, {})
    assert not ok and "not reported" in detail  # a missing field never matches, not even null
    bad: object
    for bad in ({}, [], "x"):
        with pytest.raises(ScorerConfigError):
            _fe(bad, {})
    with pytest.raises(ScorerConfigError):
        get_scorer("field-equals")({"a": 1}, Output(), {"x": 1})


def test_label_rate_options_and_edge_cases() -> None:
    lr = get_scorer("label-rate")
    assert not lr(1.0, Output(), LR_OPTS).applicable
    assert not lr(1.0, Output(fields={"verdicts": ["schema_invalid"]}), LR_OPTS).applicable
    o = lr(1.0, Output(fields={"verdicts": "supported"}), LR_OPTS)
    assert o.applicable and not o.passed
    o = lr(0.5, Output(fields={"verdicts": ["supported", "partial"]}), LR_OPTS)
    assert o.passed and (o.hits, o.total) == (1, 2)
    for opts in ({}, {"field": "v"}, {"field": "v", "positive": []}, {**LR_OPTS, "exclude": ["supported"]}):
        with pytest.raises(ScorerConfigError):
            lr(1.0, Output(), opts)
    for expected in (True, 2, "1"):
        with pytest.raises(ScorerConfigError):
            lr(expected, Output(), LR_OPTS)


def test_gate_rules_accept_rate_metrics() -> None:
    GateRule(metric="rate:support", slice="s", floor=0.9)
    with pytest.raises(ValidationError):
        GateRule(metric="rate:", floor=0.9)
    with pytest.raises(ValidationError):
        GateRule(metric="nope", floor=0.9)
    with pytest.raises(ValidationError):
        GateRule(metric="cost_total_usd", slice="s", max=1)


def test_rate_gate_counts_only_items_the_scorer_applied_to() -> None:
    """YS-02 for rates: min_items counts items with a score for that key, not the whole run."""
    suite = _suite(10, report_only=True)
    outputs = {
        f"i{k}": Output(text="ok", fields={"verdicts": ["supported"] if k < 3 else []}) for k in range(10)
    }
    run = build_run(suite, TARGET, outputs, clock=CLOCK)
    cfg = GateConfig(min_items=5, rules=[GateRule(metric="rate:support", floor=0.5)])
    res = gate_mod.evaluate(cfg, run)
    assert not res.passed
    assert res.rules[0].n_items == 3 and res.rules[0].current == 1.0


def test_rate_max_drop_against_baseline_and_compare() -> None:
    suite = _suite(4, report_only=True)
    good = {f"i{k}": Output(text="ok", fields={"verdicts": ["supported"] * 2}) for k in range(4)}
    worse = {f"i{k}": Output(text="ok", fields={"verdicts": ["supported", "partial"]}) for k in range(4)}
    base = build_run(suite, TARGET, good, clock=CLOCK)
    cur = build_run(suite, TARGET, worse, clock=CLOCK)
    cfg = GateConfig(rules=[GateRule(metric="rate:support", max_drop=0.02)])
    res = gate_mod.evaluate(cfg, cur, base)
    assert not res.passed and res.rules[0].baseline == 1.0 and res.rules[0].current == 0.5
    c = compare(base, cur)
    d = {(x.metric, x.slice): x for x in c.deltas}
    assert d[("rate:support", None)].direction == "worse" and d[("rate:support", None)].delta == -0.5
    assert d[("rate:support", "s")].delta == -0.5
