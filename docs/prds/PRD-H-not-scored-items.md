# PRD-H: Items with no gating scorer

Review item 12. Decision 9 (b).

## Problem

An item scored only by report-only scorers always fails (`passed = bool(gating) and ...`, mean 0.0). A suite
of 10 items whose only scorer is `llm-judge`, with every unit judged "good", gives `pass_rate 0.0` beside
`rate hits=10 total=10`, and lists every item under "Failing items" as "no scorer applied". D-25 and D-36
together cause it and no decision covers it.

## Decision applied

**9 (b):** exclude such items from `pass_rate` and `mean_score` and show them as "not scored". Check that no
committed example number moves; if one does, explain it.

## Scope

- `ItemResult.scored: bool` (additive; serialised only when false, so existing run JSON and run ids do not
  move). An item is "not scored" when no gating (non-report-only) score was recorded for it: either all its
  scorers are report-only, or every gating scorer was not applicable.
- `metrics.pass_rate` and `mean_score` (run and per slice) are computed over scored items only; `None`
  ("not reported") when there are none. `MetricSet.n_not_scored` counts the others. `n_items` and rates are
  unchanged.
- `pass_rate`/`mean_score` gate rules count only scored items toward `min_items` (YS-02 holds on what the
  value is computed from).
- Reports: Summary shows `Items: N (k not scored)` when k > 0; "Failing items" no longer lists not-scored
  items; a "Not scored" line lists their ids (first 25). Compare: a not-scored item is neither newly failing
  nor newly passing.
- The run summary line prints `x/y passed (k not scored)` when k > 0.

## Out of scope

Rejecting such suites at load (option a, not chosen).

## Acceptance

- H1. The review's judge-only suite gives `pass_rate` "not reported" (no scored items), `rate:judge` 10/10, and
  no "Failing items" (test).
- H2. A mixed suite computes `pass_rate` over scored items only; a `pass_rate` rule's `min_items` counts only
  scored items (test).
- H3. Older run JSON (no `scored` field) loads with every item scored, and the support-bot run id is
  unchanged (pinned literal from PRD-A).
- H4. Regenerating the committed examples moves no number; if one moves, a D-row explains it.
