# PRD-A: Invariants hold (YS-02, YS-05)

Review items 1 and 4. Decisions 2 (a) and 3 (a).

## Problem

1. **YS-02 hole.** `metrics.rates` counts every score toward a rate's `n_items`, including a counting score of
   0/0 (a target error on a `label-rate` key, or an `llm-judge` unit skipped by the budget). Ten items with one
   judged and nine skipped give `hits=1 total=1 n_items=10`, and a `min_items: 8` rate rule passes on a sample
   of one. D-26 says a rate gate counts "only items the scorer applied to".
2. **Tests named for YS-02 and D-24 assert less than they claim.** The YS-02 invariant covers only
   `pass_rate`/`mean_score`; `test_report_only_false_does_not_change_suite_hash` compares a hash with itself.
3. **YS-05 bypass.** Judge verdicts that arrive through a `label-rate` scorer (`support` over Footnote's
   `verdicts`) gate with no kappa check: `fixtures/gates/footnote.yaml` passes `rate:support[A+M+V]` on the
   judged cell at the same 96.1% that `footnote-judged.yaml` demotes to report-only at κ 0.17.
4. **No minimum n for a calibration.** A calibration from 3 graded units (`kappa 1.00 (n 3)`) makes a judge
   rule gate.

## Decisions applied

- **2 (a):** a `label-rate` scorer can be marked judge-derived, so YS-05 applies to its `rate:<key>` rules.
  This makes `rate:support` report-only at κ 0.17. Check whether the Footnote suite hash moves; if it does,
  re-pin in this repo and list the Footnote-side re-pin as Shane's hand step.
- **3 (a):** `judge.min_graded`, default 30. A calibration whose pooled n is below it counts as unknown.

## Scope

- `metrics.rates`: an item counts toward `n_items` only when its score has `total > 0`. Non-counting scorers
  always have total 1, so nothing changes for them.
- `ScorerSpec.judge: true` (additive, omitted when false so no other suite hash moves; allowed on
  `label-rate` only). The run records each judge-derived key with the judge identity the target reported:
  a new additive `Run.label_judges: {key: {model, prompt_hash, source}}`, with `model`/`prompt_hash` null when
  the target did not report them. Identity comes from two new optional `ResultsMapping` paths,
  `judge_model` and `judge_prompt_hash`; the built-in `footnote` mapping reads Footnote's file-level `judge`
  and `judgePromptHash` (the same fields `footnote verdicts` already reads).
- `gate.judge_keys` and `gate.judge_status` treat a judge-derived key like an `llm-judge` key. An unreported
  identity is "kappa unknown", so the rule is report-only.
- The Footnote suites (`footnote suite`, `footnote suite --judged`) mark `support` as `judge: true`.
  `fixtures/gates/footnote.yaml` gains the same `judge` block as `footnote-judged.yaml` (floor 0.6, the
  committed Opus calibration), so the demotion reads "κ 0.17 < floor 0.6" rather than "no calibration".
- `JudgePolicy.min_graded: int = 30` (must be >= 1). Pooled n below it gives
  `report-only (YS-05): judge kappa X from n N graded units < min_graded M, treated as unknown`.
- Tests: YS-02 property test extended to `rate:*` with errored and budget-skipped items; the D-24 test pins
  literal hashes (support-bot suite hash and one Phase 1 run id).

## Out of scope

Item 12 (items scored only by report-only scorers, PRD-H); the run-file checks of item 16 (Later).

## Acceptance

- A1. The review's reproduction (10 items, 1 judged, 9 budget-skipped; or 9 target errors on a `label-rate`
  key) gives `n_items` 1 and a `min_items: 8` rate rule fails.
- A2. A Hypothesis invariant asserts YS-02 for `rate:*` rules with errored and budget-skipped items.
- A3. `test_backcompat` pins the literal content hash of `fixtures/suites/support-bot.yaml` and the run id of
  a Phase 1 run.
- A4. On the judged hybrid cell, `yardstick gate ... -c fixtures/gates/footnote.yaml` shows
  `rate:support[A+M+V]` as report-only with "judge kappa 0.17 (n 40) < floor 0.6".
- A5. A calibration with pooled n below `min_graded` leaves a judge rule report-only; n at or above it gates
  as before.
- A6. The old and new Footnote suite hashes are recorded in a D-row, with the Footnote re-pin as a hand step.
