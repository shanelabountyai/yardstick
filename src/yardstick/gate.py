"""Gate evaluation (PRD §3 "Gate", plan §"Gate semantics").

A rule fails closed: missing baseline for a ``max_drop``/``max_rise`` check, a metric that is not reported,
or fewer items than ``min_items`` all fail the rule (YS-02).

YS-05 (Phase 3, D-40): a rule on ``rate:<key>`` where ``<key>`` is an ``llm-judge`` score, or a
``label-rate`` score marked ``judge: true`` (D-79), gates only when a calibration for that judge (same model
and prompt hash) has a pooled kappa at or above the gate's ``judge.kappa_floor``, computed from at least
``judge.min_graded`` graded units (D-80). Otherwise it is still evaluated and shown, marked report-only with
the reason, and never changes the verdict. A gate with no gating rule left fails closed (D-11).
"""

from __future__ import annotations

from collections.abc import Sequence

from yardstick import metrics as metrics_mod
from yardstick.kappa import Calibration, js_fixed
from yardstick.models import (
    LLM_JUDGE,
    CheckResult,
    GateConfig,
    GateResult,
    GateRule,
    JudgePolicy,
    MetricSet,
    RuleResult,
    Run,
    is_rate_metric,
    rate_key,
)
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
    n = current.count(rule.slice, rule.metric)
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


def judge_keys(run: Run) -> set[str]:
    """Scorer keys in a run that come from a judge: ``llm-judge`` scorers, and ``label-rate`` scorers marked
    ``judge: true`` (D-79)."""
    keys = set(run.judges) | set(run.label_judges)
    for item in run.items:
        keys.update(s.key for s in item.scores if s.scorer == LLM_JUDGE)
    return keys


def judge_status(
    run: Run, key: str, policy: JudgePolicy, calibrations: Sequence[Calibration]
) -> tuple[bool, str]:
    """``(gating, note)`` for a judge metric under YS-05."""
    floor = policy.kappa_floor
    rec = run.judges.get(key)
    lj = run.label_judges.get(key)
    if rec is not None:
        model, phash = rec.model, rec.prompt_hash
    elif lj is not None and lj.model is not None and lj.prompt_hash is not None:
        model, phash = lj.model, lj.prompt_hash
    elif lj is not None:
        return False, f"report-only (YS-05): judge behind {key!r} not reported by the target, kappa unknown"
    else:
        return False, f"report-only (YS-05): judge for {key!r} not recorded in the run, kappa unknown"
    who = f"{model} prompt {phash}"
    found = [c for c in calibrations if c.matches(model, phash)]
    if not found:
        return False, f"report-only (YS-05): no calibration for {who}, kappa unknown"
    if len(found) > 1:
        return False, f"report-only (YS-05): {len(found)} calibrations for {who}; give exactly one"
    pooled = found[0].pooled
    if pooled.kappa is None:
        return False, f"report-only (YS-05): kappa undefined for {who} (n {pooled.n})"
    if pooled.n < policy.min_graded:
        return (
            False,
            f"report-only (YS-05): judge kappa {js_fixed(pooled.kappa, 2)} from n {pooled.n} graded units "
            f"< min_graded {policy.min_graded}, treated as unknown",
        )
    if round(pooled.kappa, 6) < round(floor, 6):
        return (
            False,
            f"report-only (YS-05): judge kappa {js_fixed(pooled.kappa, 2)} (n {pooled.n}) < floor {floor:g}",
        )
    return True, f"judge kappa {js_fixed(pooled.kappa, 2)} (n {pooled.n}) >= floor {floor:g}"


def evaluate(
    config: GateConfig,
    run: Run,
    baseline: Run | None = None,
    *,
    allow_suite_change: bool = False,
    calibrations: Sequence[Calibration] = (),
) -> GateResult:
    warnings: list[str] = []
    suite_changed = False
    if baseline is not None:
        warnings = check_same_suite(baseline, run, allow_suite_change)
        suite_changed = bool(warnings)
    current_m = metrics_mod.compute(run)
    base_m = metrics_mod.compute(baseline) if baseline is not None else None
    policy = config.judge or JudgePolicy()
    keys = judge_keys(run)
    results = []
    for rule in config.rules:
        rr = evaluate_rule(rule, current_m, base_m, config.min_items)
        if is_rate_metric(rule.metric) and rate_key(rule.metric) in keys:
            gating, note = judge_status(run, rate_key(rule.metric), policy, calibrations)
            rr = rr.model_copy(update={"report_only": not gating, "note": note})
        results.append(rr)
    gating_results = [r for r in results if not r.report_only]
    if results and not gating_results:
        warnings.append("every rule is report-only (YS-05), so nothing gates: the gate fails closed")
    return GateResult(
        passed=bool(gating_results) and all(r.passed for r in gating_results),
        rules=results,
        baseline_run_id=baseline.run_id if baseline is not None else None,
        suite_changed=suite_changed,
        warnings=warnings,
    )
