"""Aggregates over a run.

Rules (YS-04): latency and cost are *never invented*. If any item lacks a value, the metric is ``None``
("not reported") rather than computed over a subset or defaulted to 0. Coverage counts are kept so the report
can say "not reported (7/12 items)". A run-level cost the target reported is used only when items do not all
report one (D-27).

Rates (D-26): ``rate:<scorer key>`` pools ``hits / total`` over every score with that key, report-only scores
included; ``None`` when the pooled total is 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from yardstick.models import ItemResult, MetricSet, RateMetric, Run, SliceMetrics


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


def rates(results: Sequence[ItemResult]) -> dict[str, RateMetric]:
    acc: dict[str, list[int]] = {}
    for r in results:
        for s in r.scores:
            hits, total = s.counts()
            slot = acc.setdefault(s.key, [0, 0, 0])
            slot[0] += hits
            slot[1] += total
            slot[2] += 1
    return {
        key: RateMetric(hits=h, total=t, n_items=n, value=round(h / t, 6) if t else None)
        for key, (h, t, n) in sorted(acc.items())
    }


def compute(run: Run) -> MetricSet:
    items = run.items
    n = len(items)

    latencies = [r.output.latency_ms for r in items if r.output.latency_ms is not None]
    lat_complete = n > 0 and len(latencies) == n
    costs = [r.output.cost_usd for r in items if r.output.cost_usd is not None]
    cost_complete = n > 0 and len(costs) == n
    cost_source: Literal["items", "run"] | None = None
    cost_total: float | None = None
    if cost_complete:
        cost_total, cost_source = round(math.fsum(costs), 6), "items"
    elif n > 0 and run.reported_cost_usd is not None:
        cost_total, cost_source = run.reported_cost_usd, "run"

    slice_names = sorted({s for r in items for s in r.slices})
    slices: dict[str, SliceMetrics] = {}
    for name in slice_names:
        members = [r for r in items if name in r.slices]
        slices[name] = SliceMetrics(
            n_items=len(members),
            pass_rate=pass_rate(members),
            mean_score=mean_score(members),
            rates=rates(members),
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
        rates=rates(items),
        cost_source=cost_source,
    )
