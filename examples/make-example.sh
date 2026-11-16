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

# Phase 3: Footnote's grades and committed judge verdicts -> kappa reproduction (the Phase 3 gate), and a gate in
# which the judge's rule is report-only because its kappa is below the floor (YS-05). Zero model calls: the
# llm-judge scorer replays Footnote's committed verdicts under a $0 budget cap.
fa="$fn/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json"
src="shanelabountyai/footnote @ 3c9b0c7"
uv run yardstick footnote suite fixtures/footnote/golden.json --judged -o "$work/judge-suite.yaml"
cmp "$work/judge-suite.yaml" fixtures/footnote/judge-suite.yaml
uv run yardstick footnote verdicts "$fa" --source "$src: eval/results/$(basename "$fa")" -o "$work/verdicts.json"
cmp "$work/verdicts.json" fixtures/footnote/judge/verdicts-opus-1646.json
uv run yardstick footnote grades fixtures/footnote/grades/grades.md --answers "$fa" --name sheet-1 \
  --source "$src: eval/grades.md (enriched, Claude-assisted, Footnote D-39)" -o "$work/sheet-1.yaml"
cmp "$work/sheet-1.yaml" fixtures/footnote/grades/sheet-1.yaml
uv run yardstick footnote grades fixtures/footnote/grades/grades-2.md --answers "$fa" --name sheet-2 \
  --source "$src: eval/grades-2.md (unassisted, Footnote D-41)" -o "$work/sheet-2.yaml"
cmp "$work/sheet-2.yaml" fixtures/footnote/grades/sheet-2.yaml
uv run yardstick footnote kappa --golden fixtures/footnote/golden.json --answers "$fa" \
  --sheet fixtures/footnote/grades/grades.md --sheet fixtures/footnote/grades/grades-2.md \
  --reference fixtures/footnote/kappa-reference.yaml --source "$src" \
  --calibration-out "$work/calibration.json" -o examples/footnote/kappa.md
cmp "$work/calibration.json" fixtures/footnote/judge/calibration-opus-1646.json
uv run yardstick run --suite fixtures/footnote/judge-suite.yaml --mapping footnote --no-git \
  --fixed-clock 2026-11-16T00:00:00Z --target-name footnote-hybrid-sonnet-theta-on --results "$fa" \
  --judge replay:fixtures/footnote/judge/verdicts-opus-1646.json --judge-budget-usd 0 --out "$work/judged.json"
# The judge rule passes (96%) but is report-only (kappa 0.17 < 0.6); the A+M rule fails, so the gate fails.
uv run yardstick gate "$work/judged.json" -c fixtures/gates/footnote-judged.yaml \
  --report examples/footnote/judged-report.md --html-report examples/footnote/judged-report.html || test $? -eq 1
