# Yardstick — PRD

Build-log item: **#26 Yardstick** (AI track). Repo: `shanelabountyai/yardstick` (public).
Base: **standalone Python 3.12 CLI** + static HTML report. No web server, no database.

## 1. Why this exists

"How do you know your AI output is any good — and that it didn't get worse last Tuesday?" is the question applied-AI
hiring managers ask. Each build-log AI project answers it locally: Footnote already has a golden set, a judge, a
judge-vs-human kappa and per-run result files in `eval/results/`. What's missing is the **layer above**: one
harness that reads any project's eval output in a common format, keeps baselines over time, compares model/prompt
changes side by side, and **fails CI on a regression**.

Yardstick is that layer. It does not replace a project's own eval scripts; it adapts to them.

## 2. Users

- Shane, in a terminal or a CI log.
- A reviewer of a PR, reading the Yardstick comment ("supported-sentence rate 92% → 88%, below the −2 pt gate").
- A hiring manager reading the README and an example HTML report.

## 3. Concepts

| Concept | What it is |
|---|---|
| **Suite** | a named set of items (`id`, `input`, `expected`, tags/slices), YAML or JSON, versioned by content hash |
| **Target** | how outputs are produced: `results-file` (read a project's existing result JSON), `command` (run a script that prints JSONL), `http` (POST each input) |
| **Scorer** | turns (item, output) into a score: `exact`, `regex`, `json-schema`, `numeric-tolerance`, `contains-all`, `refusal-expected`, `citation-grounded` (quote fragment appears in a cited source text), `llm-judge` (rubric, Phase 3) |
| **Run** | one execution: suite hash, target, model, prompt hash, git SHA, per-item scores, cost (USD, 6 dp), latency (ms, integer), timestamp |
| **Metric** | an aggregate over a run, optionally per slice (pass rate, mean, p50/p95 latency, cost per item) |
| **Baseline** | a pinned run per suite+target, stored as JSON in the target repo (`.yardstick/baselines/`) |
| **Gate** | per-metric rule: absolute floor and/or max drop vs baseline (e.g. `supported_rate >= 0.85`, `drop <= 0.02`), plus a minimum-item count so a tiny run can't pass |
| **Report** | markdown (for PR comments and CI logs) and a single static HTML file (charts inline, no CDN) |

Note (2026-11-22): as built, the registry has 10 scorers: the 8 above plus `field-equals` and `label-rate` (D-23,
D-26). Gate rules are written `metric: rate:<key>` or a fixed metric, with `floor`, `max`, `max_drop`, `max_rise`,
`min_items` and an optional `slice` (D-12, D-26), plus a `judge` block for YS-05 (D-40, D-79, D-80). See the README
"Pieces" section.

## 4. Scope v1

- CLI: `yardstick run`, `yardstick compare <runA> <runB>`, `yardstick gate`, `yardstick report`,
  `yardstick baseline pin <run>`.
- Adapters: `results-file` with a **Footnote** mapping (its `answers-*.json` rows → verdict rates per slice,
  refusal correctness, gate pass, `spentUsd`), plus generic `command` and `http`.
- Judge calibration (Phase 3): ingest human grades, compute Cohen's kappa per judge prompt hash, and refuse to use
  a judge whose kappa is below a configured floor as a gating metric (it is still reported).
- GitHub composite action (`action.yml`) that runs `yardstick gate` and posts the markdown report.

## 5. Out of scope v1

A hosted dashboard, a database, generating golden sets, red-teaming, running other projects' expensive evals on
every push (CI gates on committed or cheap runs; expensive runs are manual).

## 6. Architecture

`src/yardstick/` — `models.py` (pydantic: Suite, Item, Run, Score, Metric, Gate), `scorers/`, `adapters/`,
`metrics.py`, `gate.py`, `report/` (markdown + HTML via Jinja2), `cli.py` (Typer). Packaging: `pyproject.toml`
with pinned versions, `uv` for installs. Tests: pytest + hypothesis for the aggregators.

## 7. Invariants (`tests/invariants/`)

- YS-01 Scoring is deterministic for deterministic scorers: same suite + outputs → byte-identical run JSON
  (timestamps excluded by an injected clock).
- YS-02 A gate never passes with fewer items than its `min_items`.
- YS-03 A suite whose content hash differs from the baseline's cannot be compared without `--allow-suite-change`,
  and the report says so.
- YS-04 Cost and latency are never invented: a target that reports none shows "not reported", never 0.
- YS-05 An LLM-judge metric whose judge kappa is below the floor (or unknown) is report-only, never gating.

## 8. Phases and gates

| Phase | Scope | Gate |
|---|---|---|
| 1 | **Core, no network, no LLM:** models, deterministic scorers, metrics, baseline compare, gate, markdown report, `command` adapter against a fake target, synthetic suites | pytest green; YS-01..YS-04 green; example report committed |
| 2 | `results-file` adapter + Footnote mapping, run over Footnote's committed result files (copied as test fixtures with attribution), HTML report | Footnote runs reproduce the numbers its own scorecard reports (difference listed if not) |
| 3 | `llm-judge` scorer with budget cap, human-grade ingestion, kappa, YS-05 | kappa on Footnote's graded sentences matches its `eval:kappa` output |
| 4 | GitHub composite action; branch in Footnote adding a Yardstick gate step (PR unmerged); README case study | action runs green on the Footnote branch |
