# PRD-F: Reports for a first reader

Review items 8, 10 and 11. Decision 5 (b).

## Problem

1. The verdict is first but its reason is at the bottom: the Footnote example shows "Gate failed", a 9-row
   metadata table, then "+22.0 pt", and the 3 failing rules appear about 1,500 px down. The baseline is a
   different target and the markdown report does not say so. Markdown and HTML differ (title, verdict
   wording, the long uncollapsed "Rates by slice" table in markdown, an empty header row).
2. `refusal 92.5%` reads as a refusal rate but means "answered as expected"; slices A, A+M, A+M+V, M, P, U, V
   have no legend.
3. `kappa.md` has duplicate rows and a 200-character reason repeated 5 times; `reproduction.md` repeats 4 or
   5 long reasons inline in 49 rows.

## Decision applied

**5 (b):** keep the `refusal` key. Add a display label/description per scorer and slice, shown as a legend.
No hash moves.

## Scope

- **Legend.** Suites may carry `descriptions: {scorers: {key: text}, slices: {name: text}}` (additive, and
  excluded from the suite hash like `description`, D-17). The run does not store it; reports take the suite
  as an optional input (`report --suite`, `gate --suite`; the action and `make-example.sh` pass it). When
  present, a "Key" section under the verdict lists the scorers and slices in use with their text. The Footnote
  suite generator writes descriptions for every scorer and slice (texts from Footnote's scorecard row names
  and D-23/D-32), e.g. `refusal`: "refused when it should, answered when it should (hit = outcome as
  expected; on A and M a hit means answered or partial)".
- **First screen.** Directly under the verdict: one line per failing gating rule (rule, value, requirement:
  the PRD-B formatter), and, when the baseline's target name differs from the run's,
  `Compared against a different target: <baseline target>`. Run metadata moves below Summary.
- **Markdown in line with HTML.** Same title ("Yardstick report: x") and verdict wording ("Gate passed" /
  "Gate failed", bold); "Rates by slice" collapsed in `<details>` in markdown too; the metadata table gets a
  header row; the baseline target name is shown in markdown.
- **kappa.md:** the duplicate `pooled | opus` figures are shown once each (a figure recorded by more than one
  source document is one row with the documents listed); the Note column is empty on a match; repeated
  reasons become footnote markers defined once under the table.
- **reproduction.md:** "not reproducible" rows carry a marker (`[1]`...) whose reason is defined once under
  the table; matches are unchanged; counts unchanged.

## Out of scope

Charts and narrow-screen layout (PRD-I).

## Acceptance

- F1. In the regenerated Footnote report (both formats), the failing rules and the cross-target note appear
  before the Summary table.
- F2. The Footnote reports show a Key with every scorer and slice used; the suite hashes do not move because
  of descriptions (test).
- F3. Markdown "Rates by slice" is inside `<details>`.
- F4. `kappa.md` has no two identical rows; its headline still reads 19 match, 0 differ, 5 not reproducible.
- F5. `reproduction.md` defines each not-reproducible reason once; its headline still reads 74 match,
  0 differ, 49 not reproducible.
