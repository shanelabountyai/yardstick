"""Hypothesis tests for the aggregators."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.helpers import run_from_passes
from yardstick import metrics
from yardstick.metrics import mean_score, nearest_rank, pass_rate
from yardstick.models import ItemResult, Output

latencies = st.lists(st.integers(min_value=0, max_value=600_000), min_size=1, max_size=200)


def _ir(passed: bool, score: float) -> ItemResult:
    return ItemResult(item_id="x", slices=[], output=Output(), scores=[], passed=passed, score=score)


@given(latencies, st.floats(min_value=0.01, max_value=100))
def test_nearest_rank_is_an_observed_integer(values: list[int], pct: float) -> None:
    p = nearest_rank(values, pct)
    assert isinstance(p, int)
    assert p in values
    assert min(values) <= p <= max(values)


@given(latencies)
def test_percentiles_monotonic(values: list[int]) -> None:
    assert nearest_rank(values, 50) <= nearest_rank(values, 95) <= nearest_rank(values, 100) == max(values)


@given(latencies, st.randoms())
def test_percentile_permutation_invariant(values: list[int], rnd: object) -> None:
    shuffled = list(values)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert nearest_rank(values, 95) == nearest_rank(shuffled, 95)


def test_nearest_rank_known_values() -> None:
    assert nearest_rank([1, 2, 3, 4], 50) == 2
    assert nearest_rank(list(range(1, 21)), 95) == 19
    with pytest.raises(ValueError):
        nearest_rank([], 50)


@given(st.lists(st.tuples(st.booleans(), st.floats(min_value=0, max_value=1)), min_size=1, max_size=300))
def test_pass_rate_and_mean_bounds(rows: list[tuple[bool, float]]) -> None:
    results = [_ir(p, sc) for p, sc in rows]
    pr = pass_rate(results)
    ms = mean_score(results)
    assert pr is not None and ms is not None
    assert 0.0 <= pr <= 1.0
    assert 0.0 <= ms <= 1.0
    assert math.isclose(pr, sum(p for p, _ in rows) / len(rows), abs_tol=1e-6)


def test_empty_is_none_not_zero() -> None:
    assert pass_rate([]) is None
    assert mean_score([]) is None


@given(st.lists(st.booleans(), min_size=1, max_size=60))
def test_slice_counts_sum_and_match(passes: list[bool]) -> None:
    run = run_from_passes(passes)
    m = metrics.compute(run)
    assert m.n_items == len(passes)
    assert m.slices["s"].n_items == len(passes)
    assert m.slices["s"].pass_rate == m.pass_rate


@given(
    st.lists(
        st.tuples(st.integers(0, 10_000), st.floats(min_value=0, max_value=1, allow_nan=False)),
        min_size=1,
        max_size=60,
    )
)
def test_cost_and_latency_complete(rows: list[tuple[int, float]]) -> None:
    run = run_from_passes([True] * len(rows), latency=[r[0] for r in rows], cost=[r[1] for r in rows])
    m = metrics.compute(run)
    assert m.latency_p50_ms is not None and m.latency_p95_ms is not None
    assert isinstance(m.latency_p50_ms, int) and isinstance(m.latency_p95_ms, int)
    assert m.latency_p50_ms <= m.latency_p95_ms
    total = math.fsum(round(c, 6) for _, c in rows)
    assert m.cost_total_usd is not None and m.cost_per_item_usd is not None
    assert math.isclose(m.cost_total_usd, round(total, 6), abs_tol=1e-6)
    assert math.isclose(m.cost_per_item_usd, round(total, 6) / len(rows), abs_tol=1e-6)
