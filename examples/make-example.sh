#!/usr/bin/env bash
# Regenerates examples/report-example.md with the CLI, offline: the fake target's healthy run is pinned as the
# baseline, then a degraded run is gated against it (and fails, which is the point of the example).
set -euo pipefail
cd "$(dirname "$0")/.."
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

common=(--suite fixtures/suites/support-bot.yaml --target-name fake --no-git --fixed-clock 2026-11-14T00:00:00Z
        --model fake-model-v1 --prompt-hash sha256:example)
uv run yardstick run "${common[@]}" --cmd "python3 fixtures/targets/fake_target.py" --out "$work/healthy.json"
uv run yardstick run "${common[@]}" --cmd "python3 fixtures/targets/fake_target.py --degrade" --out "$work/degraded.json"
uv run yardstick baseline pin "$work/healthy.json" --baselines-dir "$work/baselines"
# The gate is expected to fail here; the report is the artefact.
uv run yardstick gate "$work/degraded.json" -c fixtures/gates/support-bot.yaml \
  --baselines-dir "$work/baselines" --report examples/report-example.md || test $? -eq 1

# Phase 2: Footnote's committed result files through the results-file adapter (footnote mapping).
fn=fixtures/footnote/results
mkdir -p examples/footnote
uv run yardstick footnote suite fixtures/footnote/golden.json -o "$work/footnote-suite.yaml"
cmp "$work/footnote-suite.yaml" fixtures/footnote/suite.yaml
uv run yardstick footnote reproduce --results-dir "$fn" --golden fixtures/footnote/golden.json \
  --scorecard "$fn/scorecard-cd1252c6a407-2026-10-28.md" \
  --source "shanelabountyai/footnote @ 3c9b0c7 (eval/results, eval/golden.json)" \
  -o examples/footnote/reproduction.md
fcommon=(--suite fixtures/footnote/suite.yaml --mapping footnote --no-git --fixed-clock 2026-11-14T00:00:00Z)
uv run yardstick run "${fcommon[@]}" --target-name footnote-hybrid-sonnet-theta-on \
  --results "$fn/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json" --out "$work/fn-base.json"
uv run yardstick run "${fcommon[@]}" --target-name footnote-dense-sonnet-theta-off \
  --results "$fn/answers-dense-claude-sonnet-5-5-theta-off-cd1252c6a407-2026-10-28T0102.json" --out "$work/fn-cand.json"
# Footnote's cells miss its own targets, so this gate fails too; the reports are the artefacts.
uv run yardstick gate "$work/fn-cand.json" -c fixtures/gates/footnote.yaml --baseline "$work/fn-base.json" \
  --report examples/footnote/report.md --html-report examples/footnote/report.html || test $? -eq 1
