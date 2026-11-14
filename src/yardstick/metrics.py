"""Aggregates over a run.

Rules (YS-04): latency and cost are *never invented*. If any item lacks a value, the metric is ``None``
("not reported") rather than computed over a subset or defaulted to 0. Coverage counts are kept so the report
can say "not reported (7/12 items)".
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from yardstick.models import ItemResult, MetricSet, Run, SliceMetrics


def nearest_rank(values: Sequence[int], pct: float) -> int:
    """Nearest-rank percentile: always an observed value, so integers stay integers."""
    if not values:
        raise ValueError("percentile of empty sequence")
    if not 0 < pct <= 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def pass_rate(results: Sequence[ItemResult]) -> float | None:
    if not results:
        return None
    return round(sum(1 for r in results if r.passed) / len(results), 6)


def mean_score(results: Sequence[ItemResult]) -> float | None:
    if not results:
        return None
    return round(math.fsum(r.score for r in results) / len(results), 6)


def compute(run: Run) -> MetricSet:
    items = run.items
    n = len(items)

    latencies = [r.output.latency_ms for r in items if r.output.latency_ms is not None]
    lat_complete = n > 0 and len(latencies) == n
    costs = [r.output.cost_usd for r in items if r.output.cost_usd is not None]
    cost_complete = n > 0 and len(costs) == n
    cost_total = round(math.fsum(costs), 6) if cost_complete else None

    slice_names = sorted({s for r in items for s in r.slices})
    slices: dict[str, SliceMetrics] = {}
    for name in slice_names:
        members = [r for r in items if name in r.slices]
        slices[name] = SliceMetrics(
            n_items=len(members), pass_rate=pass_rate(members), mean_score=mean_score(members)
        )

    return MetricSet(
        n_items=n,
        n_errors=sum(1 for r in items if r.output.error is not None),
        pass_rate=pass_rate(items),
        mean_score=mean_score(items),
        latency_p50_ms=nearest_rank(latencies, 50) if lat_complete else None,
        latency_p95_ms=nearest_rank(latencies, 95) if lat_complete else None,
        latency_reported=len(latencies),
        cost_total_usd=cost_total,
        cost_per_item_usd=round(cost_total / n, 6) if cost_total is not None else None,
        cost_reported=len(costs),
        slices=slices,
    )
