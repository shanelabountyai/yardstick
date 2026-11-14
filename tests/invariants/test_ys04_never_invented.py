"""YS-04: cost and latency are never invented: unreported shows "not reported", never 0."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import SUITES, fake_adapter, run_from_passes
from yardstick import metrics
from yardstick.report.markdown import render
from yardstick.runner import run_suite
from yardstick.suite_io import load_suite

TELEMETRY = ("latency_p50_ms", "latency_p95_ms", "cost_total_usd", "cost_per_item_usd")


def test_target_without_telemetry() -> None:
    run = run_suite(load_suite(SUITES / "support-bot.yaml"), fake_adapter("--no-telemetry"))
    assert all(i.output.latency_ms is None and i.output.cost_usd is None for i in run.items)
    m = metrics.compute(run)
    for name in TELEMETRY:
        assert m.value(name) is None
    text = render(run)
    for label in ("Latency p50", "Latency p95", "Cost total", "Cost per item"):
        assert re.search(rf"\| {label} \| not reported \|", text), label
    assert "$0.000000" not in text
    assert "| 0 ms" not in text


@given(st.lists(st.booleans(), min_size=2, max_size=30), st.data())
def test_partial_telemetry_is_not_reported(present: list[bool], data: st.DataObject) -> None:
    """If any item lacks a value the aggregate is None, never computed from a subset or zero-filled."""
    if all(present):
        present = [*present[:-1], False]
    lat = [data.draw(st.integers(1, 5000)) if p else None for p in present]
    cost = [data.draw(st.floats(0.000001, 1.0)) if p else None for p in present]
    run = run_from_passes([True] * len(present), latency=lat, cost=cost)
    m = metrics.compute(run)
    for name in TELEMETRY:
        assert m.value(name) is None
    assert m.latency_reported == sum(present)
    text = render(run)
    if any(present):
        assert f"not reported ({sum(present)}/{len(present)} items)" in text


def test_real_zero_cost_is_shown_as_zero() -> None:
    """A target that *reports* 0 cost (e.g. a cache hit) is shown as $0, distinct from not reported."""
    run = run_from_passes([True, True], latency=[5, 7], cost=[0.0, 0.0])
    m = metrics.compute(run)
    assert m.cost_total_usd == 0.0
    assert "| Cost total | $0.000000 |" in render(run)
