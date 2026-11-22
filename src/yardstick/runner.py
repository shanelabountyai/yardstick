"""Suite + adapter + scorers -> Run."""

from __future__ import annotations

from collections.abc import Mapping

from yardstick.adapters.base import Adapter, ReportsRunMeta, RunMeta
from yardstick.clock import Clock, SystemClock
from yardstick.models import (
    LLM_JUDGE,
    Item,
    ItemResult,
    LabelJudge,
    Output,
    Run,
    Score,
    Suite,
    TargetInfo,
)
from yardstick.scorers import ScorerConfigError, get_scorer
from yardstick.scorers.llm_judge import JudgeSession

NO_OUTPUT = "no output from target"


def score_item(suite: Suite, item: Item, output: Output, judge: JudgeSession | None = None) -> ItemResult:
    """Score one item. Report-only scores are recorded but do not decide ``passed`` or ``score`` (D-25).
    ``llm-judge`` scorers go through ``judge`` (Phase 3)."""
    scores: list[Score] = []
    for spec in suite.scorers:
        key = spec.expected_key
        if key not in item.expected:
            continue
        scorer = get_scorer(spec.name)
        if output.error is not None:
            counting = bool(getattr(scorer, "counting", False))
            scores.append(
                Score(
                    key=key,
                    scorer=spec.name,
                    score=0.0,
                    passed=False,
                    detail=f"error: {output.error}",
                    hits=0 if counting else None,
                    total=0 if counting else None,
                    report_only=spec.report_only,
                )
            )
            continue
        labels: list[str | None] | None = None
        if spec.name == LLM_JUDGE:
            if judge is None:
                raise ScorerConfigError(
                    f"scorer {key!r} is an llm-judge: pass --judge and --judge-budget-usd (D-34)"
                )
            outcome, labels = judge.score(key, item, item.expected[key], output, spec.options)
        else:
            outcome = scorer(item.expected[key], output, spec.options)
        if not outcome.applicable:
            continue
        scores.append(
            Score(
                key=key,
                scorer=spec.name,
                score=outcome.score,
                passed=outcome.passed,
                detail=outcome.detail,
                hits=outcome.hits,
                total=outcome.total,
                report_only=spec.report_only,
                labels=labels or None,
            )
        )
    gating = [s for s in scores if not s.report_only]
    passed = bool(gating) and all(s.passed for s in gating)
    mean = sum(s.score for s in gating) / len(gating) if gating else 0.0
    return ItemResult(
        item_id=item.id,
        slices=sorted(set(item.slices)),
        output=output,
        scores=scores,
        passed=passed,
        score=round(mean, 6),
    )


def build_run(
    suite: Suite,
    target: TargetInfo,
    outputs: Mapping[str, Output],
    *,
    clock: Clock | None = None,
    model: str | None = None,
    prompt_hash: str | None = None,
    git_sha: str | None = None,
    reported_cost_usd: float | None = None,
    judge: JudgeSession | None = None,
    label_judge: RunMeta | None = None,
) -> Run:
    """``label_judge`` is the run-level meta whose ``judge_model``/``judge_prompt_hash`` identify the judge
    behind judge-derived ``label-rate`` keys (D-79); without it their identity is recorded as unknown."""
    clock = clock or SystemClock()
    started = clock.now().isoformat().replace("+00:00", "Z")
    results = [
        score_item(suite, item, outputs.get(item.id, Output(error=NO_OUTPUT)), judge) for item in suite.items
    ]
    judges = judge.records() if judge is not None else {}
    meta = label_judge or RunMeta()
    reported = meta.judge_model is not None and meta.judge_prompt_hash is not None
    label_judges = {
        spec.expected_key: LabelJudge(
            model=meta.judge_model if reported else None,
            prompt_hash=meta.judge_prompt_hash if reported else None,
            source=f"reported by target {target.name!r}" if reported else "not reported by the target",
        )
        for spec in suite.scorers
        if spec.judge
    }
    payload = {
        "schema_version": 1,
        "suite_name": suite.name,
        "suite_hash": suite.content_hash,
        "target": target.model_dump(mode="json"),
        "model": model,
        "prompt_hash": prompt_hash,
        "git_sha": git_sha,
        "items": [r.model_dump(mode="json") for r in results],
    }
    cost = None if reported_cost_usd is None else round(reported_cost_usd, 6)
    if cost is not None:
        payload["reported_cost_usd"] = cost
    if judges:
        payload["judges"] = {k: v.model_dump(mode="json") for k, v in judges.items()}
    if label_judges:
        payload["label_judges"] = {k: v.model_dump(mode="json") for k, v in sorted(label_judges.items())}
    return Run(
        run_id=Run.compute_id(payload),
        started_at=started,
        target=target,
        items=results,
        suite_name=suite.name,
        suite_hash=suite.content_hash,
        model=model,
        prompt_hash=prompt_hash,
        git_sha=git_sha,
        reported_cost_usd=cost,
        judges=judges,
        label_judges=dict(sorted(label_judges.items())),
    )


def run_suite(
    suite: Suite,
    adapter: Adapter,
    *,
    clock: Clock | None = None,
    model: str | None = None,
    prompt_hash: str | None = None,
    git_sha: str | None = None,
    judge: JudgeSession | None = None,
) -> Run:
    outputs = adapter.produce(suite.items)
    meta = adapter.run_meta() if isinstance(adapter, ReportsRunMeta) else RunMeta()
    return build_run(
        suite,
        adapter.info,
        outputs,
        clock=clock,
        model=model if model is not None else meta.model,
        prompt_hash=prompt_hash,
        git_sha=git_sha,
        reported_cost_usd=meta.cost_usd,
        judge=judge,
        label_judge=meta,
    )
