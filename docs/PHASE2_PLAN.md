# Yardstick — Phase 2 plan

Scope, exactly as PRD §8 row 2 (and §4 "Adapters"): the **`results-file` adapter with a Footnote mapping**
(`answers-*.json` rows → verdict rates per slice, refusal correctness, gate pass, `spentUsd`), **run over Footnote's
committed result files** (copied as test fixtures with attribution, D-05), and the **HTML report** (one static file,
charts inline, no CDN). Branch `phase-2`, one PR against `main`, never merged by Claude.

Not in Phase 2 (Phase 3+): `llm-judge`, human-grade ingestion, kappa, YS-05, the `http` adapter, the GitHub action,
any Footnote branch. No network at runtime, no LLM calls.

**Gate (PRD §8):** Footnote runs reproduce the numbers its own scorecard reports; every number that is not reproduced
is listed with the reason. Plus the standing gates: ruff (lint + format), mypy `--strict`, pytest (unit, property,
invariants), examples regenerate byte-identically, GitHub CI green.

## What Footnote's files contain (read from `shanelabountyai/footnote` @ `3c9b0c7`)

- `eval/results/answers-<retriever>-<model>-theta-<on|off>-<snap>-<ts>.json`, 6 cells × 41 rows. File-level: `runId`,
  `retriever`, `model`, `judge`, `judgePromptHash`, `theta`, `unverified`, `estimateUsd`, `spentUsd`, `stopped`.
  Row: `id`, `slice` (A, M, V, P, U), `status` (answered / partial / refused), `refusal` (code or null),
  `gate` `{score, theta, pass}`, `droppedSentences`, `verdicts` (judge label per sentence; only the judged cell has any).
- `eval/golden.json`: 41 items with `question`, `callerRole`, `slice`, `expected.refusal` (null, `NO_RELEVANT_PASSAGE`,
  `OUT_OF_SCOPE`), `expected.citations`.
- `eval/results/scorecard-<snap>-2026-10-28.md`, written by `npm run eval:scorecard` from **database rows** (Answer,
  ModelCall, SentenceJudgment) and other result files. The answers files are what Yardstick can read; anything the
  scorecard derives from citations, ModelCall outcomes or other files cannot be reproduced from them and is listed.

## Tasks

1. **Fixtures** `fixtures/footnote/`: the 6 answers files, `golden.json`, the scorecard, `ATTRIBUTION.md` (source repo,
   commit, paths, what was changed: nothing).
2. **Core additions** (all additive; Phase 1 runs, run ids and suite hashes stay byte-identical; the example report gains Rates sections, D-26):
   - `Output.fields`: structured values a target reports (status, refusal code, verdicts, gate score).
   - `ScorerSpec.report_only` / `Score.report_only`: the score is recorded and feeds rate metrics, but never decides
     item pass or mean score.
   - Counted scores: `Score.hits` / `Score.total`. Every applicable score counts (1/1 or 0/1 by default; a counting
     scorer such as `label-rate` reports its own counts). A scorer can also say "not applicable" (nothing to count).
   - Rate metric `rate:<scorer key>` = Σhits / Σtotal over the items where that scorer applied, run-level and per slice;
     "not reported" when Σtotal is 0. Usable in gates (`floor`, `max_drop`, ...) and shown in compare and reports.
   - `Run.reported_cost_usd`: a run-level cost the target reported. Cost metrics use per-item costs when every item has
     one, else the run-level total, else "not reported" (YS-04 still holds: nothing is invented).
   - Scorers `field-equals` (every listed field equals the expected value) and `label-rate` (share of a list field's
     labels that are positive, with excluded labels; counts are the labels).
3. **`results-file` adapter** (`adapters/results_file.py`): a declarative mapping (dotted paths for rows, id, text,
   refused flag, telemetry, fields, run-level model and cost). Missing paths stay `None`; malformed files fail with
   exit 2. Duplicate or unknown ids fail the run like the `command` adapter.
4. **Footnote mapping** (`adapters/footnote.py`): the built-in preset `footnote` (refused = `status == "refused"`;
   fields `status`, `refusal_code`, `pre_call`, `gate_score`, `verdicts`; model; `spentUsd` as run cost), an optional
   θ′ what-if (Footnote's `atTheta`), and a suite builder from `golden.json` → `fixtures/footnote/suite.yaml`.
5. **CLI**: `yardstick run --results FILE --mapping footnote|mapping.yaml [--theta-prime X]`;
   `yardstick footnote suite`; `yardstick footnote reproduce`; `yardstick report --format html`;
   `yardstick gate --html-report`.
6. **Reproduction** (`footnote_scorecard.py`): build Yardstick runs for each cell, compute each scorecard number from
   Yardstick metrics and item results, parse the same number out of Footnote's committed scorecard, and write a table
   of match / differs / not reproducible (with the reason). Output committed as `examples/footnote/reproduction.md`.
7. **HTML report** (`report/html.py` + template): run facts, summary, rates, slices, gate, item changes, failing items;
   inline SVG bar charts (slice pass rates and rates, baseline beside current); autoescaped; light/dark via CSS;
   no scripts, no external URLs. Example committed as `examples/footnote/report.html` (+ `.md`).
8. **Docs**: README, DECISIONS rows, this plan.

## Suite mapping (golden → Yardstick suite `footnote-golden`)

| Golden item | Slices | Scorers (key: expected) |
|---|---|---|
| A, M | own slice, `A+M`, `A+M+V` | `refusal`: false; `support` (report-only `label-rate`): 1.0; `pre-call` (report-only): `{pre_call: true}` |
| V | `V`, `A+M+V` | same as A, M |
| P | `P` | `refusal`: expected refusal is non-null; `pre-call` |
| U, expected `NO_RELEVANT_PASSAGE` | `U` | `refusal`: true; `refusal-code` (report-only): `{refusal_code: NO_RELEVANT_PASSAGE}`; `pre-call` |
| U, expected `OUT_OF_SCOPE` | `U` | `out-of-scope`: `{refusal_code: OUT_OF_SCOPE}`; `pre-call` |

This mirrors `uCorrect` in Footnote's `scorecard.ts`: an `OUT_OF_SCOPE` item is right only with that code, any other
U item is right when refused. `pre_call` = refused with `NO_RELEVANT_PASSAGE`, the only code Footnote emits before a
model call (`noRelevantPassage()` in `src/lib/answer/gate.ts`).

## Scorecard numbers → Yardstick

| Scorecard row | Yardstick | Reproducible? |
|---|---|---|
| Answered or partial (A, M) | `rate:refusal[A+M]`; pre-call count = `rate:pre-call[A+M]` hits | yes; the schema_invalid / model split is not in the file |
| Refusal on unanswerable (U) | `pass_rate[U]`; false answers = failing U items; code mismatch = passing U items failing `refusal-code` | yes |
| Refused before any model call (U) | `rate:pre-call[U]` | yes |
| Outcome as expected (P) | `pass_rate[P]`; misses = failing P items (+ pre-call cause) | yes |
| Split (all) | tally of the mapped `status` field | yes, except the schema_invalid count |
| Sentence support (judged cell) | `rate:support[A+M+V]` (pooled over sentences); excluded `schema_invalid` labels | yes; "V edition stated by judge" is not in the file |
| θ′ axis (θ-off cells) | runs with `--theta-prime`; same three metrics | yes, except "A, M expected cited" |
| Citation verbatim, expected passage cited, edition labeled | — | no: citations are not in the answers files |
| Tier leaks, fabrication, κ, injection, build spend, retrieval | — | no: DB rows or other result files (κ is Phase 3) |

## Invariants and tests

| Acceptance item | Proof |
|---|---|
| results-file adapter maps rows faithfully | unit tests: dotted paths, missing → `None`, bad file / duplicate / unknown id → `AdapterError`; end-to-end CLI run |
| Footnote mapping | unit tests per field; θ′ transform equals Footnote's `atTheta` rule (property test: rows at/above θ′ unchanged, below become pre-call refusals, fts rows never change) |
| Scorecard reproduced | `tests/test_footnote_reproduction.py`: every reproducible cell equals the number parsed from the committed scorecard; the not-reproducible list equals an explicit expected list (nothing drops silently) |
| Suite file is the golden set | test: regenerating `suite.yaml` from `golden.json` is byte-identical |
| Rates | hypothesis: rate = Σhits/Σtotal, in [0, 1], `None` iff Σtotal = 0; report-only scores never change item pass or mean |
| YS-01..YS-04 still hold | existing invariant tests, plus YS-01 for results-file runs and YS-04 for run-level cost (none → "not reported") |
| Backward compatibility | Phase 1 run JSON carries none of the new keys and suite hashes are unchanged; a Phase 1 run JSON still loads; the example's run ids are unchanged |
| HTML report | test: one file, no `<script>`, no `http(s)://` references, values escaped, byte-identical on rerun, contains the SVG chart and "not reported" where telemetry is missing |

## Risks

- **Scorecard reads DB rows, Yardstick reads files.** If a file and the DB disagree, numbers differ; the reproduction
  table would show it. Footnote writes both from the same in-memory answer, so agreement is expected.
- **`pre_call` is inferred from the refusal code.** Holds for Footnote today (one emitter); documented in DECISIONS.
- **Percent rounding**: the scorecard uses JS `Math.round` (half up); the reproduction formats the same way.
