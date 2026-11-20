# Five-lens review 2026-11-19: accessibility lens, as returned

Unedited output of the accessibility lens agent (repo `main` at `94949eb`, reviewed 2026-11-20), apart from sandbox paths shortened to `<sandbox>` and the agent's closing housekeeping line about session memory removed. Ranking and calls are in [`../FIVE-LENS-2026-11-19.md`](../FIVE-LENS-2026-11-19.md). Nothing here was fixed.

### Wide tables scroll inside unnamed, non-focusable containers at narrow widths
- Severity: Major
- Where: `src/yardstick/report/templates/report.html.j2` line 23 (`.table-wrap { overflow-x: auto; }`) and every `<div class="table-wrap">` (lines 48, 65, 92, 102, 113, 125, 134, 154)
- WCAG: 2.1.1 Keyboard (also 4.1.2 Name, Role, Value for the scroller)
- Observed: axe rule `scrollable-region-focusable`, impact serious, at a 320 px viewport with `<details>` open: 6 nodes in runs/report.html (e.g. `.table-wrap:nth-child(3)`), 5 nodes in examples/footnote/judged-report.html. Measured scrollWidth/clientWidth at 320 px: up to 445/288 (Gate table) and 749/288 (Judges table). The Judges table still overflows at 640 px (749/608), which is the 200% zoom case on a 1280 px screen. No wrapper has `tabindex`, `role` or a name. Chromium 157 makes scrollers tab stops by itself (I got 6 and 5 tab stops at 320 px), so the failure is in browsers that do not, notably Safari.
- Why it matters: a keyboard-only user who zooms in or uses a narrow window cannot reach the right-hand columns, and the right-hand column of the Gate table is the pass/FAIL result.
- Recommended fix: `<div class="table-wrap" tabindex="0" role="region" aria-label="Gate rules">` (one label per table, or `aria-labelledby` pointing at the `<h2>`), plus a visible `:focus-visible` outline for `.table-wrap`.
- Status: verified
- Check type: automated (axe-core 4.14.1) plus inspection of scroll widths

### Chart text shrinks with the viewport: 5.3 px at 320 px wide and it does not reach 200% on zoom
- Severity: Major
- Where: template lines 33-34 (`svg { width: 100%; height: auto }`, `svg text { font-size: 13px }`) with the fixed `viewBox="0 0 640 …"` on line 75
- WCAG: 1.4.4 Resize Text (and readability under 1.4.10 Reflow)
- Observed: effective rendered size of chart labels and values, computed as 13 × svg width / 640: 18.3 px at a 1280 px viewport, 11.8 px at 640 px, 5.3 px at 320 px. Zooming 1280 to 200% (640 CSS px) makes chart text 23.6 device px against 18.3 before, so it grows 1.29 times, not 2 times. The screenshot at 320 px confirms the labels are not legible. The surrounding HTML text stays at 15 px.
- Why it matters: on a phone, or for a low-vision user who zooms, the chart labels and values are the one part of the page that gets smaller. The same numbers are in the Rates and Slices tables, which is why this is not a Blocker.
- Recommended fix: stop scaling the text with the drawing. Either render each row as HTML (label, a `<div>` or small SVG bar, value) in a CSS grid, or keep the SVG at a fixed pixel height with `preserveAspectRatio="none"` for the bars only and put label and value in HTML beside it.
- Status: verified
- Check type: automated measurement (Playwright 1.63.0, Chromium 157) plus screenshot inspection

### Chart values and the baseline marker have no reliable text alternative
- Severity: Minor
- Where: template line 75 (`<svg … role="img" aria-label="{{ chart.title }}">`), lines 78-82 (`<text>`, `<rect>`, `<line class="base">`)
- WCAG: 1.1.1 Non-text Content
- Observed: axe `svg-img-alt` passes because the name exists, but the name is only the title ("Pass rate by slice"). There is no `<title>` or `<desc>`. Children of `role="img"` are presentational by the ARIA spec, so the label and value `<text>` nodes are not guaranteed to be read; Chromium does expose them (aria snapshot: `img "Pass rate by slice": account 75.0% faq 50.0% refusal 50.0%`). The baseline line has no text at all inside the chart. The values are also in the Rates and Slices tables, but nothing links chart to table, and the Slices table gives only "Pass rate change", not the baseline value.
- Why it matters: a screen reader user hears "Pass rate by slice, image" and is not told the data is in a table two headings below.
- Recommended fix: build the label in `html.py`, for example `aria-label="Pass rate by slice: account 75.0% (baseline 100.0%), faq 50.0% (baseline 100.0%), …"`, or add `aria-describedby` pointing at the id of the matching table. Add a Baseline column to the Slices table.
- Status: verified
- Check type: inspection, plus automated accessibility tree (Playwright aria snapshot and CDP `Accessibility.getFullAXTree`)

### Chart title is announced three times
- Severity: Minor
- Where: template lines 73-75 (`<figure>`, `<figcaption>`, `aria-label` on the `<svg>`)
- WCAG: 1.3.1 Info and Relationships (verbosity; not a strict failure)
- Observed: aria snapshot gives `figure "Pass rate by slice"` → `text: Pass rate by slice` → `img "Pass rate by slice"`.
- Why it matters: three repeats of the same string and no data, for each chart.
- Recommended fix: resolved by the fix above: let the figcaption name the figure and give the SVG the data summary as its label.
- Status: verified
- Check type: automated accessibility tree (Playwright 1.63.0)

### Data tables have no accessible name and no row headers
- Severity: Minor
- Where: template lines 48, 65, 92, 102, 113, 125, 134, 154 (`<table>`); first cells on lines 68, 95, 105, 116, 128, 137, 157 are `<td>`
- WCAG: 1.3.1 Info and Relationships
- Observed: 7 tables in runs/report.html and 8 in judged-report.html; none has `<caption>`, `aria-label` or `aria-labelledby` (CDP tree: every `table` has name ""). No `<thead>`, no `scope` on any `<th>` (0 of 9, 4, 5, 5, 5, 6, 3). Chromium still infers 23 column headers and, in the first key/value table, 9 row headers, so that table reads correctly ("Run, row header"). It has no header row, which is fine for a key/value table. In the data tables the row label (metric, scorer, slice, rule, item) is a plain cell.
- Why it matters: moving down the Result column a screen reader says "Result, FAIL" without the rule name; a tables list shows unnamed tables.
- Recommended fix: `<caption>` (visually hidden if wanted) or `aria-labelledby` the `<h2>`; make the first cell of each body row `<th scope="row">`; add `scope="col"` to header cells and `scope="row"` in the key/value table; wrap in `<thead>`/`<tbody>`.
- Status: verified
- Check type: inspection plus automated accessibility tree

### Baseline marker has 2.03:1 against the bar in dark theme
- Severity: Minor
- Where: template line 36 (`svg .base { stroke: var(--base) }`), line 12 (dark `--base: #e6e8eb`, `--bar: #7aa2ff`), element `<line class="base">` line 81
- WCAG: 1.4.11 Non-text Contrast (3:1)
- Observed: computed baseline line against bar fill: light #1d2129 on #3b6fd8 = 3.42:1 (pass); dark #e6e8eb on #7aa2ff = 2.03:1 (fail). Against the track it is 13.72:1 light, 11.45:1 dark. The overlap happens whenever the current value is above the baseline. The line is 22 units tall against a 16-unit bar, so 3 units stick out above and below, onto the panel (15.03:1 light, 13.46:1 dark).
- Why it matters: for an improved run in dark mode the baseline marker nearly disappears inside the bar; only the two short ends remain.
- Recommended fix: give the line a contrasting casing, e.g. draw a 4-unit line in `var(--panel)` under the 2-unit line, or use a darker dark-theme `--base` only where it crosses the bar.
- Status: verified
- Check type: automated measurement from computed styles (Playwright 1.63.0)

### Bar track is nearly invisible against the chart panel
- Severity: Minor
- Where: template line 35 (`svg .track`), tokens on lines 8-12 (`--track`, `--panel`)
- WCAG: 1.4.11 Non-text Contrast (3:1)
- Observed: track against panel: light #e9edf2 on #f5f7fa = 1.10:1; dark #262c35 on #1b1f26 = 1.18:1. The track is the only mark that shows where 100% is; the legend says "Scale 0–100%" and each row prints its value, so the information is not lost.
- Why it matters: a low-vision reader cannot judge how full a bar is from the graphic alone, and with no baseline line there is no visible 100% end.
- Recommended fix: outline the track with a 1-unit stroke at 3:1 or better against the panel, or add 0% and 100% tick lines.
- Status: verified
- Check type: automated measurement from computed styles

### Long chart labels are cut without notice and long values are clipped
- Severity: Minor
- Where: template line 78 (`{{ bar.label[:30] }}`), line 82 (value `<text>`), `html.py` lines 18-20 (`CHART_WIDTH` 640, `LABEL_WIDTH` 220, `VALUE_WIDTH` 120)
- WCAG: 1.4.5 is not engaged; nearest is 1.3.1 Info and Relationships (content lost in the visual presentation)
- Observed: labels are sliced to 30 characters with no ellipsis and no `<title>`. Substituting text in the rendered SVG: the value "100.0% (1234/1234)" ends at x = 651 in a 640-wide viewBox and the SVG computes `overflow: hidden`, so it is clipped. A 30-character label measured 190 to 211 units (fits in 220); 30 capital W's measured 393 units and overlaps the bar. Longest label in the committed examples is 161 units; longest value ends at 618.
- Why it matters: two scorers whose names share the first 30 characters look identical, and large suites lose the end of the count.
- Recommended fix: add "…" when truncating and keep the full label in the accessible name; size the value column from the longest value string, or move labels and values into HTML (same fix as the text-scaling finding).
- Status: verified by DOM substitution; not seen with the committed fixtures
- Check type: inspection with measurement (Playwright `getBBox`)

### Focus ring and scrollbars depend on browser defaults; no `color-scheme` declared
- Severity: Minor
- Where: template lines 10-13 (dark tokens) and line 38 (`details summary`); no `:focus-visible` rule and no `color-scheme` anywhere
- WCAG: 2.4.7 Focus Visible (passes in Chromium), 1.4.11 Non-text Contrast for the indicator
- Observed: the only default tab stop is `<summary>`; computed `outline: auto 1px rgb(16,16,16)` in both themes. #101010 against the dark page #14171c is 1.06:1. Chromium paints a two-tone ring, and the dark screenshot shows the white part clearly, so it is visible there. Computed `color-scheme` on `:root` is `normal`, so in dark mode the browser still treats the page as light (light scrollbars on the table wrappers).
- Why it matters: focus visibility in dark mode rests on one engine's two-tone ring; other engines were not tested.
- Recommended fix: `:root { color-scheme: light dark; }` and `summary:focus-visible, .table-wrap:focus-visible { outline: 2px solid var(--fg); outline-offset: 2px; }`.
- Status: verified in Chromium; behaviour in Firefox and Safari suspected
- Check type: automated (computed style, screenshot) plus inspection

### Footer sits inside `<main>`, so there is no contentinfo landmark
- Severity: Minor
- Where: template lines 162-163 (`<footer>` before `</main>`)
- WCAG: 1.3.1 Info and Relationships (best practice, not a failure)
- Observed: landmarks found: one `main`, nothing else. The aria snapshot shows the footer as plain text inside `main`. axe best-practice rules reported no violation.
- Why it matters: small; the note that explains "not reported" and the units cannot be reached by landmark navigation.
- Recommended fix: move `<footer>` after `</main>` and give it the same max-width and padding.
- Status: verified
- Check type: inspection plus accessibility tree

### "Rates by slice" disclosure has no heading
- Severity: Minor
- Where: template lines 111-112 (`<details><summary>`)
- WCAG: 2.4.6 Headings and Labels (advisory)
- Observed: headings are one `h1` then `h2` only, in order, none skipped. The collapsed section is exposed as `group: Rates by slice (N rows)` with a `DisclosureTriangle` named "Rates by slice (7 rows)"; Enter opens it and Space closes it. It is the only section a heading-key user cannot jump to, and its table (27 rows in the judged example) has no name of its own.
- Why it matters: screen reader users who navigate by heading skip it.
- Recommended fix: `<summary><h3>Rates by slice (27 rows)</h3></summary>` with the h3 styled inline, or an `aria-label` on the table inside.
- Status: verified
- Check type: inspection plus keyboard test (Playwright)

## Automated checks run
- Tool: axe-core 4.14.1 injected with Playwright 1.63.0 into Chromium 157.0.8103.78; tags wcag2a, wcag2aa, wcag21a, wcag21aa (best-practice also run).
- Files: examples/footnote/report.html, examples/footnote/judged-report.html, runs/report.html (degraded against healthy, gate failed), runs/pass.html (healthy, no baseline); each in light and dark at 1280 × 900. Eight runs.
- Totals at 1280 px: 0 violations, 160 passes (21, 21, 19, 19, 21, 21, 19, 19), 8 incomplete (one per run), 0 best-practice violations.
- Incomplete, all `color-contrast`, impact serious: 24 nodes in footnote/report.html, 26 in judged-report.html, 12 each in runs/report.html and runs/pass.html, example `svg[aria-label="Pass rate by slice"] > text[y="20"][x="0"]`; axe could not determine the background of SVG text. Resolved by hand: SVG text against the panel is 15.03:1 light and 13.46:1 dark.
- Two more runs at 320 px with `<details>` open (runs/report.html, judged-report.html, light): 1 violation each, `scrollable-region-focusable` (first finding).
- Contrast, reflow, keyboard and accessibility-tree scripts: Playwright, from computed styles. Scripts and screenshots are in <sandbox>/a11y-work (axe.js, inspect.js, extra.js).
- No real screen reader was available. Statements about announcements come from Chromium's accessibility tree, not from NVDA, JAWS or VoiceOver.

## Found clean
Contrast, computed, threshold 4.5:1 for text and 3:1 for graphics:

| Pair | Light | Dark |
|---|---|---|
| Body text, headings, code on page | 16.13:1 | 14.63:1 |
| Table header, muted paragraph, footer, `details` summary on page | 6.13:1 | 6.97:1 |
| Legend on panel | 5.71:1 | 6.41:1 |
| Figcaption and SVG text on panel | 15.03:1 | 13.46:1 |
| "Gate failed" badge text on fill | 6.54:1 | 7.87:1 |
| "Gate passed" badge text on fill (runs/pass2.html, healthy against itself) | 5.37:1 | 8.28:1 |
| FAIL result text on page | 6.54:1 | 7.87:1 |
| pass result text on page | 5.37:1 | 8.28:1 |
| Warning text on warning background (element injected; no fixture produces a warning) | 14.72:1 | 10.37:1 |
| Bar against track | 4.01:1 | 5.65:1 |
| Bar against panel | 4.40:1 | 6.64:1 |
| Badge fill against page | 5.37:1 to 6.54:1 | 7.87:1 to 8.28:1 |

- There are no links in any of the four files.
- `lang="en"`, a descriptive `<title>`, `meta viewport` of `width=device-width, initial-scale=1` (zoom not blocked), one `<main>`, one `h1`, ordered `h2`s.
- Colour is never the only signal: the badge says "Gate passed"/"Gate failed", results read "pass"/"FAIL", check details say "(ok)"/"(FAIL)", changes carry a sign.
- Reflow: no horizontal page scroll at 320, 640 or 1280 px, with `<details>` open or closed; only the table wrappers scroll.
- Text-spacing override (SC 1.4.12 values) at 320 px: no page scroll, chart labels stay inside the label column (203 of 220 units at most).
- `<details>`: reachable by Tab, toggles with Enter and Space.
- No animation or transition rules, so `prefers-reduced-motion` does not apply. No scripts, as D-30 states.
- Forced colours (light, emulated): text 21:1, badge fill is dropped but its text remains, bar against background 4.72:1.

## Not reviewed
- Real screen reader output (NVDA, JAWS, VoiceOver, TalkBack): none available here.
- Firefox and Safari: only Chromium is installed; the focus ring and scroller focus findings depend on the engine.
- Markdown reports as rendered by GitHub, and the terminal output: outside the HTML target.
- Forced colours with a dark system theme, print styles, and browser text-only zoom: not run.
- A report with real warnings: no fixture triggers one; only the injected element's colours were measured.
- One thing for the CLI or code lens, not an accessibility finding: runs/pass.html, the healthy run with the gate and no baseline, shows "Gate failed" because the `max_drop` rule reports "no baseline (FAIL)". The command in the brief did not produce a passing shape; I generated runs/pass2.html (healthy against itself) to measure the pass badge.

