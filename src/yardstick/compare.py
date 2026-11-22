"""Run A (usually the baseline) vs run B (usually the candidate)."""

from __future__ import annotations

from yardstick import metrics as metrics_mod
from yardstick.models import RATE_PREFIX, Comparison, MetricDelta, Run, higher_is_better
from yardstick.suite_check import check_same_suite

RUN_METRICS = (
    "pass_rate",
    "mean_score",
    "latency_p50_ms",
    "latency_p95_ms",
    "cost_total_usd",
    "cost_per_item_usd",
)


def _delta(metric: str, slice_name: str | None, a: float | int | None, b: float | int | None) -> MetricDelta:
    if a is None or b is None:
        return MetricDelta(metric=metric, slice=slice_name, a=a, b=b, delta=None, direction="n/a")
    d = round(b - a, 6)
    if d == 0:
        direction = "same"
    elif (d > 0) == higher_is_better(metric):
        direction = "better"
    else:
        direction = "worse"
    return MetricDelta(metric=metric, slice=slice_name, a=a, b=b, delta=d, direction=direction)


def compare(a: Run, b: Run, *, allow_suite_change: bool = False) -> Comparison:
    warnings = check_same_suite(a, b, allow_suite_change)
    ma, mb = metrics_mod.compute(a), metrics_mod.compute(b)
    deltas = [_delta(m, None, ma.value(m), mb.value(m)) for m in RUN_METRICS]
    rate_metrics = [RATE_PREFIX + k for k in sorted(set(ma.rates) | set(mb.rates))]
    deltas += [_delta(m, None, ma.value(m), mb.value(m)) for m in rate_metrics]
    for s in sorted(set(ma.slices) | set(mb.slices)):
        for m in ("pass_rate", "mean_score"):
            deltas.append(_delta(m, s, ma.value(m, s), mb.value(m, s)))
        slice_rates = sorted(
            set(ma.slices[s].rates if s in ma.slices else {})
            | set(mb.slices[s].rates if s in mb.slices else {})
        )
        for k in slice_rates:
            m = RATE_PREFIX + k
            deltas.append(_delta(m, s, ma.value(m, s), mb.value(m, s)))

    ra = {r.item_id: r for r in a.items}
    rb = {r.item_id: r for r in b.items}
    # A not-scored item (no gating score, D-88) neither passes nor fails, so it never flips.
    shared = [i for i in ra if i in rb and not ra[i].not_scored and not rb[i].not_scored]
    return Comparison(
        run_a=a.run_id,
        run_b=b.run_id,
        suite_changed=bool(warnings),
        deltas=deltas,
        newly_failing=sorted(i for i in shared if ra[i].passed and not rb[i].passed),
        newly_passing=sorted(i for i in shared if not ra[i].passed and rb[i].passed),
        only_in_a=sorted(set(ra) - set(rb)),
        only_in_b=sorted(set(rb) - set(ra)),
        warnings=warnings,
    )
