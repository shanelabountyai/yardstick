"""Gate evaluation (PRD §3 "Gate", plan §"Gate semantics").

A rule fails closed: missing baseline for a ``max_drop``/``max_rise`` check, a metric that is not reported,
or fewer items than ``min_items`` all fail the rule (YS-02).
"""

from __future__ import annotations

from yardstick import metrics as metrics_mod
from yardstick.models import CheckResult, GateConfig, GateResult, GateRule, MetricSet, RuleResult, Run
from yardstick.suite_check import check_same_suite

#: Values are compared after rounding to this many decimals, so 0.92 - 0.90 counts as exactly 0.02.
PRECISION = 6


def _r(x: float) -> float:
    return round(x, PRECISION)


def _fmt(x: float | int | None) -> str:
    if x is None:
        return "not reported"
    if isinstance(x, int):
        return str(x)
    return f"{x:.6g}"


def evaluate_rule(
    rule: GateRule, current: MetricSet, baseline: MetricSet | None, default_min_items: int
) -> RuleResult:
    min_items = rule.min_items if rule.min_items is not None else default_min_items
    n = current.count(rule.slice)
    cur = current.value(rule.metric, rule.slice)
    base = baseline.value(rule.metric, rule.slice) if baseline is not None else None
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(check="min_items", passed=n >= min_items, detail=f"{n} item(s), need >= {min_items}")
    )
    if cur is None:
        checks.append(CheckResult(check="reported", passed=False, detail=f"{rule.label} not reported"))
    else:
        if rule.floor is not None:
            ok = _r(cur) >= _r(rule.floor)
            checks.append(CheckResult(check="floor", passed=ok, detail=f"{_fmt(cur)} >= {_fmt(rule.floor)}"))
        if rule.max is not None:
            ok = _r(cur) <= _r(rule.max)
            checks.append(CheckResult(check="max", passed=ok, detail=f"{_fmt(cur)} <= {_fmt(rule.max)}"))
        for name, limit, sign in (("max_drop", rule.max_drop, 1), ("max_rise", rule.max_rise, -1)):
            if limit is None:
                continue
            if baseline is None:
                checks.append(CheckResult(check=name, passed=False, detail="no baseline"))
            elif base is None:
                checks.append(CheckResult(check=name, passed=False, detail="baseline value not reported"))
            else:
                change = _r((base - cur) * sign)  # drop: base - cur ; rise: cur - base
                ok = change <= _r(limit)
                word = "drop" if sign == 1 else "rise"
                checks.append(
                    CheckResult(check=name, passed=ok, detail=f"{word} {_fmt(change)} <= {_fmt(limit)}")
                )
    return RuleResult(
        rule=rule,
        current=cur,
        baseline=base,
        n_items=n,
        min_items=min_items,
        passed=all(c.passed for c in checks),
        checks=checks,
    )


def evaluate(
    config: GateConfig,
    run: Run,
    baseline: Run | None = None,
    *,
    allow_suite_change: bool = False,
) -> GateResult:
    warnings: list[str] = []
    suite_changed = False
    if baseline is not None:
        warnings = check_same_suite(baseline, run, allow_suite_change)
        suite_changed = bool(warnings)
    current_m = metrics_mod.compute(run)
    base_m = metrics_mod.compute(baseline) if baseline is not None else None
    results = [evaluate_rule(r, current_m, base_m, config.min_items) for r in config.rules]
    return GateResult(
        passed=bool(results) and all(r.passed for r in results),
        rules=results,
        baseline_run_id=baseline.run_id if baseline is not None else None,
        suite_changed=suite_changed,
        warnings=warnings,
    )
