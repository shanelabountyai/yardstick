# PRD-I: HTML report layout

Review items 14 and 15, with item 20 riding along because the same template is open. Decision 8 (b).

## Problem

- Tables on narrow screens: the Gate table's Result column and Summary's Baseline/Change are off-screen at
  390 px with no cue; the scroll wrappers are unnamed and not focusable (axe `scrollable-region-focusable` at
  320 px); the Judges table is 749 px wide with a 200-character provenance cell; "Mean score" duplicates
  "Pass rate" in every Footnote row; "$0.000000 / $0.000000"; the "Gate failed" badge prints white on white.
- Charts: the SVG scales with the page, so 13 px labels render at about 5.3 px at 320 px wide and do not
  reach 200% on zoom; zero, "not reported" and collapsed bars look the same; the only text alternative is
  the title (announced three times); the baseline marker is 2.03:1 against the bar in dark theme and the
  track 1.10:1 against the panel; long labels are cut at 30 characters with no ellipsis.
- Semantics (item 20): tables have no name and no row headers; no `color-scheme`; no focus style; the footer
  sits inside `<main>`; the "Rates by slice" disclosure has no heading.

## Decision applied

**8 (b):** charts become HTML/CSS rows, still no scripts. Update D-30's wording, README line 44 and the
Phase 2 test that expects SVG (update, not weaken: it must assert the new structure).

## Scope

- **Charts as rows.** Each chart is a `<figure>` with a `<figcaption>` and a list of rows in a CSS grid:
  label (HTML text, full, wraps), a track `<div>` with a bar `<div>` (width as a percentage) and a baseline
  marker `<div>`, and the value text. Text stays at the page's size at any width and zoom. Label column sized
  to content (`minmax(4ch, max-content)`, capped). Zero gets a 2 px stub; "not reported" gets a dashed track
  and no bar and no marker; report-only rows are muted. The baseline marker has a casing in `--panel` so it
  stays at 3:1 or better on the bar; the track gets a 1 px outline at 3:1 against the panel. Each row has a
  visually hidden text alternative ("account: 75.0%, baseline 100.0%") and the bar/marker are
  `aria-hidden`. No `<svg>` remains.
- **Tables.** Every `.table-wrap` gets `role="region"`, `tabindex="0"` and `aria-labelledby` its heading (the
  metadata table gets an `aria-label`); tables get `<thead>`/`<tbody>`, `scope="col"` headers, and row
  headers (`<th scope="row">`) for the first cell. Gate table puts Result second. A scroll cue (a fading edge
  shadow, CSS only) on wrappers.
- **Numbers.** "Mean score" is hidden in Summary and Slices when it equals Pass rate in every row (a note
  says all scorers are binary); zero judge spend prints `$0 (replay)` when the source is a replay; the
  Judges cell shows model and source type, with the full provenance in a muted second line.
- **Print.** `@media print`: badges become outlined text in the verdict colour, `print-color-adjust: exact`
  on the bars, `break-inside: avoid` on figures and rows.
- **Semantics.** `color-scheme: light dark`; `:focus-visible` outline for `summary` and `.table-wrap`;
  `<footer>` after `</main>`; the disclosure summary holds an `<h3>`.
- D-30's wording, README line 44 and `tests/test_html_report.py` updated (asserts rows, no `<svg>`, no
  `<script>`, text alternative per row).

## Out of scope

Anything that adds a script or an external resource (D-30's "no scripts" rule holds).

## Acceptance

- I1. The regenerated HTML examples contain no `<svg>` and no `<script>`; each chart row has a text
  alternative; the test asserts that structure.
- I2. In headless Chromium at 320 px, chart label font size equals body text size, and axe (if available
  offline) reports no `scrollable-region-focusable` violation; otherwise the run records it as not verified.
- I3. Printing to PDF (headless Chromium) shows the verdict text in the fail colour.
- I4. Every table has an accessible name and row headers (test on the HTML).
