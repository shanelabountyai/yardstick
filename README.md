# Yardstick

An eval harness that sits on top of AI projects' own evals: one run format, baselines, side-by-side compare, and CI gates that fail on regressions.

Build-log #26. Status: **Phase 1 (core, offline)** on branch `kickoff`. Spec in `docs/PRD.md`, plan in `docs/PHASE1_PLAN.md`, defaults in `docs/DECISIONS.md`.

## Quick start

```bash
uv sync
# run a suite against a command target (any program that reads JSONL items and prints JSONL outputs)
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py" \
  --target-name fake -o runs/healthy.json
uv run yardstick baseline pin runs/healthy.json            # -> .yardstick/baselines/support-bot__fake.json
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py --degrade" \
  --target-name fake -o runs/degraded.json
uv run yardstick gate runs/degraded.json -c fixtures/gates/support-bot.yaml --report runs/report.md   # exit 1
uv run yardstick compare runs/healthy.json runs/degraded.json
```

Example output: [`examples/report-example.md`](examples/report-example.md) (regenerate with `examples/make-example.sh`).

## Pieces

- **Scorers** (deterministic): `exact`, `regex`, `json-schema`, `numeric-tolerance`, `contains-all`, `refusal-expected`, `citation-grounded`.
- **Metrics**: pass rate, mean score, per-slice, p50/p95 latency (integer ms), total and per-item cost (USD, 6 dp). Unreported telemetry is "not reported", never 0.
- **Gates**: `floor`, `max`, `max_drop` / `max_rise` vs baseline, `min_items`. Fail closed.
- **Targets**: `command` (Phase 1). `results-file` with a Footnote mapping arrives in Phase 2.

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
