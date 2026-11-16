# Yardstick — Phase 3 plan

Scope, exactly as PRD §8 row 3 and §4 "Judge calibration": the **`llm-judge` scorer with a budget cap**, **human-grade
ingestion**, **Cohen's kappa per judge prompt hash**, and invariant **YS-05** (an LLM-judge metric whose judge kappa is
below the floor, or unknown, is report-only, never gating). Branch `phase-3`, one PR against `main`, never merged by
Claude.

**Gate (PRD §8):** kappa on Footnote's graded sentences matches its `eval:kappa` output (difference listed if not
exact). Plus the standing gates: ruff (lint + format), mypy `--strict`, pytest (unit, property, YS-01..YS-05),
examples regenerate byte-identically, GitHub CI green.

Not in Phase 3 (Phase 4): the GitHub composite action, the Footnote branch, the README case study, the `http` adapter.

**Owner rule (2026-11-15): no live LLM API calls and no API keys in this phase.** The judge sits behind an interface.
The scorer is built and tested against a fake judge and a recorded judge that replays verdicts Footnote already
committed (with attribution). Running it live is an owner hand step.

## What Footnote has (read from `shanelabountyai/footnote` @ `3c9b0c7`)

- `scripts/kappa.ts` (`npm run eval:kappa`): for each grade sheet (`eval/grades.md` sheet 1, `eval/grades-2.md` sheet
  2) and pooled, and for each judge run (Opus = `answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646`,
  Sonnet = `rejudge:claude-sonnet-5-5:2026-10-23T1646`), joins Shane's grade to the judge's `outcome = ok`
  SentenceJudgment row by `answerId:sentenceIndex` and prints n, misses, raw agreement, p_e, κ, label counts and the
  disagreements. `src/lib/eval/kappa.ts` `cohenKappa`: unweighted over `supported / partial / unsupported`, κ null
  when p_e = 1 (its D-36).
- Human grades: `eval/grades.md`, `eval/grades-2.md` (20 sentences each, `<!-- key answerId:idx -->` + `grade:`).
- **Opus verdicts are committed**: `eval/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json`
  carries `answerId` and `verdicts[sentenceIndex]` for every row (judge `claude-opus-5-5`, `judgePromptHash`
  `071689f33855`; a non-ok judgment is written as `schema_invalid`).
- **Sonnet re-judge verdicts are not committed**: run `rejudge:claude-sonnet-5-5:2026-10-23T1646` exists only as
  SentenceJudgment rows in Footnote's database; no file in the repo holds them.
- `eval:kappa`'s console output is not committed as a file. Its figures are recorded in Footnote's committed
  `docs/decisions.md` (D-40 sheet 1, D-42 sheet 2 and pooled), `NEXT.md`, `docs/WRITEUP.md` and the scorecard
  (`κ 0.17 n 40, raw agreement 83%`). Those strings are the reference.

## Tasks

1. **Judge interface** `src/yardstick/judge/`: `Judge` protocol (`describe()` → model + prompt hash + source;
   `estimate_usd(request)` → upper bound; `judge(request)` → label or None, cost); `RecordedJudge` (replays a verdict
   file keyed `<item id>:<unit index>`, cost $0 because no call is made); `ScriptedJudge` (tests: fixed labels and costs,
   counts calls); `AnthropicJudge` (Messages API client behind an injectable transport; never called live here; needs
   a key from the environment and explicit prices, so cost is computed, not guessed).
2. **Budget** `judge/budget.py`: a cap in USD for the whole run. A call is made only if `spent + estimate <= cap`;
   actual cost is charged (the estimate when the judge reports none). Units not judged because of the cap are counted
   and named in the score detail and the run's judge record. A call whose actual cost exceeds its estimate stops all
   further calls and is flagged.
3. **`llm-judge` scorer**: options `rubric`, `labels`, `positive`, `units_field` (list field → one unit per element;
   absent → the whole output text is one unit), `exclude`. Counting scorer: hits = units judged positive, total =
   units with a valid label. Per-unit labels stored on the score (`Score.labels`). Must be `report_only: true` in the
   suite (YS-05 at item level). Runner gets a `JudgeSession` (judge + budget); without one the scorer refuses to run.
   Run records `judges[key]` = model, prompt hash, source, calls, units judged / invalid / skipped by budget, spend,
   cap.
4. **Human grades** `grades.py`: a grade set file (YAML/JSON: `name`, `grader`, `source`, `labels`, `grades: [{key,
   label, note}]`); `yardstick footnote grades <sheet.md> --answers <answers.json>` converts a Footnote sheet,
   translating `answerId:idx` to `<golden id>:<idx>`; `yardstick footnote verdicts <answers.json>` writes the recorded
   verdict file. Both outputs are committed under `fixtures/footnote/` with attribution.
5. **Kappa** `kappa.py`: `cohen_kappa(a, b, labels)` (Footnote semantics); `calibrate(grade_sets, verdicts)` per set and
   pooled; `yardstick kappa --grades … (--run RUN --key K | --verdicts FILE) [-o calibration.json]` prints the table
   and writes a calibration file (judge model, prompt hash, per set + pooled κ, n, p_o, p_e, disagreements).
6. **YS-05 in the gate**: `GateConfig.judge` = `{kappa_floor (default 0.6, D-06), calibrations: [files]}`. A rule on
   `rate:<key>` where `<key>` is an `llm-judge` score is gating only if a calibration for that judge's (model, prompt
   hash) exists and its pooled κ ≥ floor; otherwise the rule is evaluated and shown as **report-only** with the reason,
   and never affects pass/fail. A gate left with no gating rule fails closed (D-11). Reports show it.
7. **Footnote kappa reproduction**: `yardstick footnote kappa` computes every `eval:kappa` figure from the committed
   inputs (recorded Opus verdicts via a Yardstick run with the replayed judge, plus both sheets), formats them like
   `kappa.ts` (`toFixed`), and compares with the reference strings; the Sonnet lines are listed "not reproducible"
   with the missing input named. Exit 1 on any difference. Output `examples/footnote/kappa.md`.
8. **Examples + docs**: `examples/make-example.sh` regenerates the kappa reproduction and a Footnote gate report in
   which the judge's support rule is report-only (κ 0.17 < 0.6); README; DECISIONS rows from D-34.

## Tests that prove each acceptance item

| Acceptance item | Test |
|---|---|
| `llm-judge` scorer | unit: labels, positive/exclude, invalid labels excluded, whole-text vs `units_field`, counting rate pools units; refuses without a session; suite validator rejects `llm-judge` without `report_only: true`; stored labels round-trip; run judge record |
| Budget cap | unit + hypothesis: with any per-call costs ≤ their estimates, spend never exceeds the cap and every unit is judged or counted as skipped; exact stop point (cap 0.05, $0.01 calls → 5 calls); actual > estimate stops further calls and is flagged; cap required and ≥ 0; replay spends $0 under cap 0 |
| Live client without live calls | `AnthropicJudge` against a fake transport: request shape, cost from usage × prices, upper-bound estimate, unparseable reply → invalid (excluded), missing key → error; no socket opened (transport injected) |
| Human-grade ingestion | Footnote sheet parser = Footnote's regex (20 + 20 grades, blank grade refused, unknown label refused), answerId → item id mapping, grade-set file round-trip |
| Kappa | textbook 2×2 κ 0.4, perfect = 1, chance = 0, one-label null (Footnote's four cases), unequal lengths / empty / unknown label raise; hypothesis: κ ≤ 1, symmetric, p_o = 1 ⇒ κ ∈ {1, null} |
| YS-05 | `tests/invariants/test_ys05_judge_report_only.py`: for any κ < floor or no calibration, the gate verdict is identical whether the judge rule's value passes or fails; with κ ≥ floor the rule gates; a calibration for another prompt hash does not count; a gate whose only rule is a demoted judge rule fails closed |
| Phase 3 gate | `tests/test_footnote_kappa.py`: the reproduction over the committed fixtures has 0 differences, the Opus sheet 1 / sheet 2 / pooled figures match, the Sonnet lines are "not reproducible" naming the missing run, and the replayed support rate equals Phase 2's 49/51 |
| No regressions | YS-01..YS-04 and every Phase 1-2 test unchanged; Phase 1-2 run JSON stays byte-identical (additive fields, D-24) |

## Risks

- **The reference figures are docs, not a committed output file.** If Footnote's docs mistyped a figure, the
  reproduction would show a difference. They agree with each other (decisions, NEXT, WRITEUP, scorecard).
- **Sentence index alignment.** `verdicts[i]` is written in sentence order by `eval-answers.ts`; the grade key's index is
  `sentenceIndex`. The reproduction checks every graded key has a verdict.
- **Live judge behaviour is unverified** (no live calls by rule). The client is tested only against a fake transport.
