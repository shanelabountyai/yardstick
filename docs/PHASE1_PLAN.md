# Yardstick — Phase 1 plan

Scope: PRD §3, §4 and §6, core only. No network, no LLM calls. Branch `kickoff`, PR #1 against `main`, never merged by Claude.

## Modules (`src/yardstick/`)

| Module | Responsibility |
|---|---|
| `models.py` | pydantic v2 models: `Item`, `Suite` (content hash), `ScorerSpec`, `Output`, `Score`, `ItemResult`, `Run`, `Metric`, `MetricSet`, `GateRule`, `GateConfig`, `GateResult`, `Comparison` |
| `hashing.py` | canonical JSON (sorted keys, no whitespace, UTF-8) and `sha256:` content hashes |
| `suite_io.py` | load suites from YAML or JSON; load/save runs as canonical JSON |
| `clock.py` | injectable clock (`Clock` protocol, `SystemClock`, `FixedClock`) so YS-01 can freeze timestamps |
| `scorers/` | one module per scorer + a registry (`get_scorer(name)`) |
| `adapters/command.py` | `command` target: runs a local script, sends one JSON object per line on stdin, reads one JSON object per line from stdout |
| `runner.py` | suite + adapter + scorers → `Run` |
| `metrics.py` | pass rate, mean score, per-slice pass rate, p50/p95 latency (integer ms), cost per item (6 dp), or `None` = not reported |
| `compare.py` | run A vs run B: per-metric delta, per-item flips, suite-hash check (YS-03) |
| `gate.py` | evaluate `GateConfig` against a run (and optional baseline) |
| `baseline.py` | `baseline pin`: copy a run to `.yardstick/baselines/<suite>__<target>.json` |
| `report/markdown.py` | markdown report via Jinja2 (run summary, slices, compare, gate) |
| `cli.py` | Typer app: `run`, `compare`, `gate`, `report`, `baseline pin` |

## Scorers (all deterministic; score in [0, 1], `passed` boolean)

| Name | `expected` | Pass rule |
|---|---|---|
| `exact` | string | output text equals expected (option `normalize`: strip + casefold + collapse whitespace) |
| `regex` | pattern string | `re.search` (option `fullmatch`) |
| `json-schema` | JSON Schema object | output parses as JSON and validates (Draft 2020-12) |
| `numeric-tolerance` | number, option `abs_tol` / `rel_tol` | first number parsed from output within tolerance |
| `contains-all` | list of strings | every string appears (case-insensitive by default); score = fraction found, pass only if all |
| `refusal-expected` | bool | output looks like a refusal iff expected is true (configurable marker phrases) |
| `citation-grounded` | `{sources: {id: text}}` | every `[[id: "quote"]]` citation in the output names a known source and its quote appears in that source (whitespace/case-normalised); zero citations fails; score = grounded fraction |

## Synthetic suites (`fixtures/`)

- `suites/support-bot.yaml` — 12 support Q&A items, slices `faq`, `account`, `refusal`; scorers `contains-all` for answers and `refusal-expected` for out-of-policy asks, plus `citation-grounded` on a few items with source snippets.
- `suites/extraction.yaml` — 10 invoice/contact extraction items; scorers `json-schema` + `exact`-on-field via `regex`, `numeric-tolerance` on totals.
- `targets/fake_target.py` — reads JSONL items on stdin, writes canned outputs with fake latency/cost. `--degrade N` corrupts every Nth answer (wrong total, missing field, failed refusal) so a gate trips. `--no-telemetry` omits latency/cost (YS-04).

## Gate semantics

A gate file (YAML) lists rules. Each rule names a metric (optionally `slice`), and any of:

- `floor`: metric value must be `>= floor`.
- `max_drop`: `baseline - current <= max_drop`, in the metric's own units (pass rate drop of 0.02 = 2 points). Needs a baseline; with no baseline the rule **fails** with reason `no baseline` (never silently passes).
- `min_items`: the run (or slice) must have at least this many items or the rule fails (YS-02). Default top-level `min_items` applies to every rule.

Overall result passes only if every rule passes. Metrics that are "not reported" (e.g. latency from a target without telemetry) fail any rule that references them.

Examples (baseline pass rate 0.92, min_items 10):

| Current | Items | Rule | Result |
|---|---|---|---|
| 0.90 | 12 | `floor: 0.85, max_drop: 0.02` | pass (drop 0.02 ≤ 0.02) |
| 0.88 | 12 | same | fail: drop 0.04 > 0.02 |
| 1.00 | 3 | same | fail: 3 items < min_items 10 |
| 0.80 | 12 | `floor: 0.85` | fail: 0.80 < 0.85 |
| `latency_p95_ms` not reported | 12 | `max: 2000` | fail: not reported |

Floats are compared after rounding to 6 dp to avoid 0.92 − 0.90 = 0.020000000000000018 false failures.

Rules can also use `max` (upper bound, for latency/cost) and `max_rise` (vs baseline, for latency/cost).

## Invariant tests (`tests/invariants/`)

- YS-01 same suite + outputs + `FixedClock` → byte-identical run JSON.
- YS-02 gate never passes with fewer items than `min_items` (hypothesis over item counts and values).
- YS-03 compare/gate with a baseline whose suite hash differs raises unless `allow_suite_change`, and the report carries a warning line.
- YS-04 target with no cost/latency → metrics `None`, report shows "not reported", never `0`.

## Risks

- **Refusal detection is heuristic** (marker phrases). Fine for synthetic suites; real projects should emit an explicit `refused` flag, which the scorer prefers when present.
- **Percentiles on small runs** are coarse; nearest-rank is used so values are always real observations (integers).
- **Command adapter runs arbitrary local commands** from config — documented, never run with a shell.
- **Python 3.12 pin** while some machines default to 3.13; `requires-python = ">=3.12,<3.13"` and uv picks 3.12.
- **Gate drift**: tolerance rounding (6 dp) could hide sub-micro regressions; acceptable.
