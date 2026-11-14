"""Suite + adapter + scorers -> Run."""

from __future__ import annotations

from collections.abc import Mapping

from yardstick.adapters.base import Adapter
from yardstick.clock import Clock, SystemClock
from yardstick.models import Item, ItemResult, Output, Run, Score, Suite, TargetInfo
from yardstick.scorers import get_scorer

NO_OUTPUT = "no output from target"


def score_item(suite: Suite, item: Item, output: Output) -> ItemResult:
    scores: list[Score] = []
    for spec in suite.scorers:
        key = spec.expected_key
        if key not in item.expected:
            continue
        if output.error is not None:
            scores.append(
                Score(key=key, scorer=spec.name, score=0.0, passed=False, detail=f"error: {output.error}")
            )
            continue
        outcome = get_scorer(spec.name)(item.expected[key], output, spec.options)
        scores.append(
            Score(
                key=key, scorer=spec.name, score=outcome.score, passed=outcome.passed, detail=outcome.detail
            )
        )
    passed = bool(scores) and all(s.passed for s in scores)
    mean = sum(s.score for s in scores) / len(scores) if scores else 0.0
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
) -> Run:
    clock = clock or SystemClock()
    started = clock.now().isoformat().replace("+00:00", "Z")
    results = [score_item(suite, item, outputs.get(item.id, Output(error=NO_OUTPUT))) for item in suite.items]
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
    )


def run_suite(
    suite: Suite,
    adapter: Adapter,
    *,
    clock: Clock | None = None,
    model: str | None = None,
    prompt_hash: str | None = None,
    git_sha: str | None = None,
) -> Run:
    outputs = adapter.produce(suite.items)
    return build_run(
        suite, adapter.info, outputs, clock=clock, model=model, prompt_hash=prompt_hash, git_sha=git_sha
    )
