# Yardstick

An eval harness that sits on top of AI projects' own evals: one run format, baselines, side-by-side compare, and CI gates that fail on regressions.

Build-log #26. Status: **Phase 3** (`llm-judge` with a budget cap, human grades, kappa, YS-05) on branch `phase-3`; Phases 1-2 (core; results-file adapter, Footnote mapping, HTML report) are on `main`. Spec in `docs/PRD.md`, plans in `docs/PHASE1_PLAN.md`, `docs/PHASE2_PLAN.md` and `docs/PHASE3_PLAN.md`, defaults in `docs/DECISIONS.md`.

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

## Footnote: reading a real project's eval results

Footnote's committed `eval/results/answers-*.json` files (copied into `fixtures/footnote/` with attribution) run through
the `results-file` adapter with the built-in `footnote` mapping:

```bash
uv run yardstick footnote suite fixtures/footnote/golden.json -o fixtures/footnote/suite.yaml
uv run yardstick run -s fixtures/footnote/suite.yaml --mapping footnote --target-name dense-sonnet \
  --results fixtures/footnote/results/answers-dense-claude-sonnet-5-5-theta-off-cd1252c6a407-2026-10-28T0102.json \
  -o runs/dense-sonnet.json
uv run yardstick gate runs/dense-sonnet.json -c fixtures/gates/footnote.yaml --html-report runs/report.html
# replay Footnote's theta gate at another threshold, as its scorecard's θ′ axis does
uv run yardstick run ... --theta-prime 0.52
# check every number in Footnote's own scorecard that the answers files can support
uv run yardstick footnote reproduce --results-dir fixtures/footnote/results --golden fixtures/footnote/golden.json \
  --scorecard fixtures/footnote/results/scorecard-cd1252c6a407-2026-10-28.md
```

Result: [`examples/footnote/reproduction.md`](examples/footnote/reproduction.md): 74 scorecard numbers match, 0 differ,
49 are listed as not reproducible with the reason (they come from database rows or other result files). The gate
report against Footnote's own targets: [`report.md`](examples/footnote/report.md) and
[`report.html`](examples/footnote/report.html) (one static file, inline SVG, no scripts).

## Judges and calibration (Phase 3)

An `llm-judge` scorer labels each unit of an output (a sentence, or the whole text) against a rubric. Its scores are
report-only per item; a gate rule on its rate (`rate:<key>`) **gates only when the judge's Cohen's kappa against human
grades clears the floor** (YS-05; default 0.6). Below the floor, or with no calibration, the rule is shown as
"report-only" and never changes the verdict. Every run that uses a judge needs a spend cap.

```bash
# replay Footnote's committed Opus verdicts through the llm-judge scorer: zero calls, $0 under a $0 cap
uv run yardstick run -s fixtures/footnote/judge-suite.yaml --mapping footnote --target-name hybrid-sonnet \
  --results fixtures/footnote/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json \
  --judge replay:fixtures/footnote/judge/verdicts-opus-1646.json --judge-budget-usd 0 -o runs/judged.json
# kappa per grade set and pooled -> a calibration file a gate can use
uv run yardstick kappa --grades fixtures/footnote/grades/sheet-1.yaml --grades fixtures/footnote/grades/sheet-2.yaml \
  --run runs/judged.json --key judge -o runs/calibration.json
uv run yardstick gate runs/judged.json -c fixtures/gates/footnote-judged.yaml   # judge rule: report-only (κ 0.17 < 0.6)
# the Phase 3 gate: Footnote's eval:kappa figures, reproduced
uv run yardstick footnote kappa --golden fixtures/footnote/golden.json \
  --answers fixtures/footnote/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json \
  --sheet fixtures/footnote/grades/grades.md --sheet fixtures/footnote/grades/grades-2.md \
  --reference fixtures/footnote/kappa-reference.yaml
```

Result: [`examples/footnote/kappa.md`](examples/footnote/kappa.md): sheet 1 κ 0.44 (n 20), sheet 2 κ 0.00 (n 20),
pooled κ 0.17 (n 40, raw agreement 83%), all 19 recorded Opus figures match, 0 differ; the 5 Sonnet re-judge figures are
not reproducible because Footnote never committed those verdicts. The gate report with the judge rule demoted:
[`judged-report.md`](examples/footnote/judged-report.md).

**Live judge (not run in this repo):** `--judge anthropic:MODEL --judge-price-in USD_PER_MTOK --judge-price-out
USD_PER_MTOK --judge-budget-usd CAP` with `ANTHROPIC_API_KEY` set. Before each call the worst-case cost must fit
under the cap; after it the actual cost from token usage is charged. Tests exercise this client only against a fake
transport.

Any other project's result JSON works with a mapping file (dotted paths):

```yaml
rows: rows
id: id
text: answer
refused: {path: status, values: [refused]}
fields: {status: status, refusal_code: refusal}
model: model
run_cost_usd: spentUsd
```

## Pieces

- **Scorers** (deterministic): `exact`, `regex`, `json-schema`, `numeric-tolerance`, `contains-all`, `refusal-expected`, `citation-grounded`, `field-equals`, `label-rate`. Any scorer can be `report_only` (measured, never decides pass). **`llm-judge`** (always report-only per item) labels units through a judge behind an interface: replay, or the Anthropic Messages API, under a run-level budget cap.
- **Calibration**: human grade sets, Cohen's kappa per judge (model + prompt hash), per set and pooled; gates honour YS-05.
- **Metrics**: pass rate, mean score, per-slice, `rate:<scorer key>` (pooled hits/total, e.g. supported sentences), p50/p95 latency (integer ms), total and per-item cost (USD, 6 dp; a run-level total when the target only reports that). Unreported telemetry is "not reported", never 0.
- **Gates**: `floor`, `max`, `max_drop` / `max_rise` vs baseline, `min_items`, on any metric including `rate:<key>` per slice. Fail closed. A judge rate gates only when its kappa clears `judge.kappa_floor`.
- **Targets**: `command` (JSONL over stdin/stdout) and `results-file` (declarative mapping, or the built-in `footnote` mapping). `http` is not built yet.
- **Reports**: markdown (PR comments, CI logs) and static HTML (`report --format html`, `gate --html-report`).

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
