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
