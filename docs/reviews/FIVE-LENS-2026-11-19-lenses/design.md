# Five-lens review 2026-11-19: design lens, as returned

Unedited output of the design lens agent (repo `main` at `94949eb`, reviewed 2026-11-20), apart from sandbox paths shortened to `<sandbox>` and the agent's closing housekeeping line about session memory removed. Ranking and calls are in [`../FIVE-LENS-2026-11-19.md`](../FIVE-LENS-2026-11-19.md). Nothing here was fixed.

Reports were rendered in headless Chromium (Playwright) at 1280 and 390 px, light and dark, deviceScaleFactor 1, plus print media and an A4 PDF: `examples/footnote/report.html`, `examples/footnote/judged-report.html`, and a freshly generated support-bot report (`runs/report.html`, untracked/ignored). Markdown files and both templates were read as source, not rendered on GitHub. Screenshots are in <sandbox>/design-work (`fn-*`, `judged-*`, `sb-*`, `fnpdf-1.png`).

### The verdict comes first, but the reason for it is at the bottom
- Severity: Major
- Where: `src/yardstick/report/templates/report.html.j2` lines 45-47 (badge) vs 132-140 (Gate table); same order in `report.md.j2`
- Observed: fn-1280-light. A red "Gate failed" pill, then a 9-row metadata table of hashes, then a Summary showing Pass rate 90.2% vs 68.3%, +22.0 pt. The three failing rules only appear about 1,500 px down at 1280, and about 2,400 px down at 390. Nothing near the top says why a run that improved by 22 points failed.
- Why it matters: A hiring manager reading the first screen sees "failed" next to a large improvement. That reads as a bug or a contradiction unless they scroll to the sixth section.
- Recommended fix: Put a one-line reason under the badge ("2 of 3 rules failed: `rate:refusal[A+M]` 86.4% < 90.0% floor; ...") or move the Gate table directly under the badge. Demote the run metadata below Summary or into a `<details>`.
- Status: verified

### Chart text is about 7 px on a phone
- Severity: Major
- Where: `report.html.j2` line 33 (`svg { width: 100% }`) with a fixed `viewBox 0 0 640 …` and 13 px text (line 34); `html.py` `CHART_WIDTH = 640`
- Observed: fn-390-light and fn-390-dark. The SVG scales to 332 px wide, so the 13 px labels render at about 6.7 px (measured text box height 9 px). Slice names and values ("85.7%", "0.0% (0/41)") are unreadable without zooming. The caption and legend around them stay at normal size, which makes the chart look broken.
- Why it matters: The charts are the only visual element in the report, and they are illegible on the device a recruiter is most likely to open a link on.
- Recommended fix: Stay within D-30 (no scripts). Either build the bars as HTML/CSS rows (label, track, value in a grid, so text stays 13-15 px), or give the SVG a `min-width` of about 520 px inside an `overflow-x: auto` wrapper.
- Status: verified

### Code cells break mid-word, at desktop width too
- Severity: Major
- Where: `report.html.j2` line 20 (`code { overflow-wrap: anywhere }`); Gate table, Rule column; Rates table, Scorer column; Judges prompt hash
- Observed: fn-1280-light: `rate:refusa / l[A+M]`, `pass_rate[U / ]`, `rate:suppor / t[A+M+V]`. sb-1280-dark: `pass_rate[re / fusal]`, `latency_p95_ / ms`. At 390 the rule names stack 3-4 characters per line (`rat / e:r / efu / sal / [A+ / M]`), scorer names become `refus / al` and `suppo / rt / (repo / rt- / only)`, and item ids become `GA- / 11`.
- Why it matters: The rule name identifies what failed. Broken at arbitrary characters on a full-width desktop table, it looks unfinished.
- Recommended fix: `overflow-wrap: anywhere` shrinks the column's minimum width. Use `overflow-wrap: break-word`, or `white-space: nowrap` on the first-column `<code>`, and let `.table-wrap` scroll. Give the Checks column the flexible width.
- Status: verified

### "Gate failed" badge disappears when printed or saved as PDF
- Severity: Major
- Where: `report.html.j2` lines 21-22 (`.badge` white text on a CSS background); there is no `@media print` block
- Observed: fnpdf-1.png (Chromium A4 PDF, default "background graphics off"). The red pill is gone and "Gate failed" is white-on-white, barely visible. The SVG bars and baseline lines print correctly.
- Why it matters: Saving the report as a PDF to attach or forward loses the verdict, the most important element on the page.
- Recommended fix: Add `@media print { .badge { color: var(--fail); background: none; border: 1.5px solid currentColor } }` (and the same for pass), or `print-color-adjust: exact` on `.badge` and `.warn`. Also add `break-inside: avoid` on `figure` and `tr`.
- Status: verified

### On a phone, the columns that carry the answer are clipped off-screen with no scroll cue
- Severity: Major
- Where: `.table-wrap` (line 23) for the Summary, Rates, Gate and Judges tables
- Observed: fn-390-light. Summary shows only Metric and Value, cut mid-phrase at "(run total reported by targe"; Baseline and Change are hidden. Gate cuts off inside Checks, so the Result column (FAIL) is hidden. Rates clips "Chang". The page itself does not overflow (scrollWidth 390); the wrappers scroll, but nothing indicates that.
- Why it matters: The phone reader sees no baseline, no change and no FAIL, and has no hint that more exists.
- Recommended fix: Fix the mid-word wrapping first, which frees width. Move "(run total reported by target)" to a footnote marker. Put Result as the second Gate column. Add a scroll shadow on `.table-wrap` or stack rows as cards below about 480 px.
- Status: verified

### Gate "Checks" cell reads as false statements and a double negative
- Severity: Major
- Where: `src/yardstick/report/markdown.py` lines 277-291 (`_humanise`); Gate table Checks column in HTML and markdown
- Observed: "floor: 86.4% >= 90.0% (FAIL)" states something untrue and then marks it failed. "max_drop: drop −22.7 pt <= 2.0 pt (ok)" describes a 22.7 pt rise as a negative drop. "min_items: 22 item(s), need >= 8 (ok)" repeats the Items column beside it ("22 / min 8"). Raw config keys (`min_items`, `max_drop`) and ASCII `>=` sit inside otherwise typeset prose, all as one semicolon-joined run (fn-1280-light, sb-1280-dark).
- Why it matters: This cell explains the verdict. A non-author has to decode it, and the first impression is of an incorrect inequality.
- Recommended fix: One check per line, in plain words with pass/fail colour: "Floor 90.0%: 86.4% is below (fail)", "Max drop 2.0 pt: rose 22.7 pt (ok)". Drop the min_items line when it passes. Use ≥ and ≤.
- Status: verified

### Slice and scorer names are unexplained, and "refusal" reads backwards
- Severity: Major
- Where: Footnote reports, Slices table and charts (A, A+M, A+M+V, M, P, U, V); Rates (`refusal`, `pre-call`, `support`); Gate rule `rate:refusal[A+M]`
- Observed: No legend anywhere on the page for the single-letter slices. D-32 says `rate:refusal[A+M]` means "answered-or-partial on A+M", but the report shows "refusal 92.5%", which reads as "the bot refused 92.5% of the time". The Failing items then say "expected refusal=False, got refusal=True". "(YS-05)" and "theta-off" are also undefined on the page.
- Why it matters: The Footnote report is the flagship example. A reader who has not read Footnote's docs cannot tell what was measured, and the headline scorer name suggests the opposite of its meaning.
- Recommended fix: Let suites carry a `description` per slice and scorer and render it as a key under the Slices heading. As a minimum, add a note to the example and rename the scorer label to something like `refusal-as-expected`.
- Status: verified

### Zero, "not reported" and collapsed scorers look identical in the chart
- Severity: Major
- Where: "Rate by scorer" figure, `report.html.j2` lines 79-82; `examples/footnote/report.html`
- Observed: fn-1280-light and fn-print. Four of five rows have an empty track: three are 0.0% and one is "not reported" (0 items). Each still has a baseline tick at 44-96%, so the chart looks like a collapse. `pre-call (report-only)` 0/41 vs 43.9% and `refusal-code` 0/7 vs 71.4% show −43.9 pt and −71.4 pt with no explanation, in a run whose pass rate rose. At `out-of-scope` the baseline tick sits at 0 on the track's left edge and reads as a stray border.
- Why it matters: The eye goes to the chart first, and it suggests the run is broken. The actual cause (a different retrieval configuration compared against a baseline from another cell) is not stated.
- Recommended fix: Draw "not reported" as a hatched or dashed track with no baseline tick. Give 0% a 2 px stub in the bar colour. Add a comparability note when baseline and run targets differ (see the next finding). Consider leaving report-only scorers out of the chart or muting them.
- Status: verified

### Markdown "Item changes" list runs two bullets together
- Severity: Major
- Where: `examples/footnote/report.md` line 88; `src/yardstick/report/templates/report.md.j2` lines 90-93
- Observed: "- Newly failing (1): `GA-12`- Newly passing (10): `GA-02`, ..." is on one line. The template's `{% endfor %}` ends the line and the environment's `trim_blocks` removes the newline, so GitHub renders one bullet with a stray "- " in the middle. The HTML version has two `<li>` correctly. `examples/report-example.md` has only newly-failing items, so it does not show the bug.
- Why it matters: It is a visible formatting defect in the committed example a reviewer is pointed to from the README, and in every PR comment where both lists exist.
- Recommended fix: Put the newline outside the block tag (e.g. `{{ "\n" }}` or a trailing `{# #}` after `endfor`) and regenerate the example. Add a test with both lists non-empty.
- Status: verified (read in source; not rendered on GitHub)

### The baseline is a different target, and the page does not say the comparison is cross-configuration
- Severity: Minor
- Where: `examples/footnote/report.html` metadata "Baseline" row; `report.md.j2` line 15
- Observed: HTML shows target `footnote-dense-sonnet-theta-off` and baseline `sha256:082261b0ce16f968 (footnote-hybrid-sonnet-theta-on)`, in small mono text in the ninth metadata row. The markdown shows only the baseline hash, with no target name. Every "Change" figure is therefore one configuration against another, not before/after.
- Why it matters: "+22.0 pt" reads as an improvement over time. It is an A/B between retrieval set-ups, and the markdown reader cannot find that out at all.
- Recommended fix: Add the baseline target name to the markdown row. When target names differ, print a one-line note under the badge ("Compared against a different target: …").
- Status: verified

### HTML and markdown versions of the same report diverge
- Severity: Minor
- Where: `report.html.j2` vs `report.md.j2`
- Observed: (1) "Rates by slice" is collapsed in HTML (D-30) but is a full `###` table in markdown: 21 rows in `report.md`, 27 in `judged-report.md`. That pushes the Gate table far down a PR comment, though GitHub supports `<details>`. (2) The title is "Yardstick report: x" in HTML and "Yardstick report — x" in markdown. (3) The verdict is "Gate failed" vs "**Gate: FAILED**". (4) The Result is coloured "FAIL" vs bold. (5) The footer has an extra sentence in HTML. (6) The baseline target name is HTML-only. (7) The markdown metadata table has an empty header row (`| | |`).
- Why it matters: A reader who opens both will notice two voices. The long uncollapsed table works against the "verdict first" aim in the PR comment, which is the main delivery surface.
- Recommended fix: Wrap the markdown table in `<details><summary>Rates by slice (N rows)</summary>`. Use one title and verdict wording in both.
- Status: verified (source read)

### Number presentation: duplicated columns, six-decimal dollars, zero spend
- Severity: Minor
- Where: Summary, Slices and Judges tables
- Observed: (1) In both Footnote reports "Mean score" equals "Pass rate" in every row (90.2/90.2, 85.7/85.7, ...), so it is a duplicate row in Summary and a duplicate column in Slices. (2) "$0.451399 (run total reported by target)" appears on two consecutive rows and is the widest cell in the table. (3) Judges shows "$0.000000 / $0.000000". (4) "Started 2026-11-14T00:00:00Z" is raw ISO. (5) Rates show "92.5% (37/40)" with a fraction, but Slices and Gate show bare percentages, and Gate "Items 22 / min 8" looks like a fraction but is not.
- Why it matters: Repeated and over-precise numbers add reading effort and make the page look machine-dumped.
- Recommended fix: Hide Mean score when it equals Pass rate throughout (or note "all scorers binary"). Print the run-total caveat once as a footnote. Show "$0 (replay)" for zero spend. Show the n/N fraction in Gate "Current" and label the minimum separately. 6 dp is a stated README convention; consider 4 dp or significant figures for totals of $0.01 or more.
- Status: verified

### Judges table: one cell holds a 200-character provenance string
- Severity: Minor
- Where: `examples/footnote/judged-report.html` Judges table, Judge column; `report.html.j2` line 128
- Observed: judged-1280-light. "claude-opus-5-5 (replay verdicts-opus-1646.json (shanelabountyai/footnote @ 3c9b0c7: eval/results/answers-hybrid-…-2026-10-23T1646.json))" wraps to 5 lines with nested parentheses. The prompt hash breaks as `071689 / f33855`. Six headers wrap to 2-3 lines. At 390 the table is 749 px wide inside a 358 px wrapper. The intro line mentions "kappa clears the floor (YS-05)", but the kappa value (0.17) appears only in the Gate row below.
- Why it matters: The judge-calibration story is the most distinctive part of the project, and this is its least readable table.
- Recommended fix: Show model and source type in the cell ("claude-opus-5-5, replay") and move the file path to a muted second line or a `title`/details. Add kappa and floor columns to this table. Drop zero-only columns.
- Status: verified

### Colour and chart layout are underused
- Severity: Minor
- Where: `report.html.j2` lines 28, 68, 95, 105, 137; `html.py` `LABEL_WIDTH = 220`
- Observed: Only the Gate Result column uses pass/fail colour. Change columns ("−41.7 pt", "+22.0 pt", "±0.0 pt") are all body colour. "report-only: pass" is unstyled next to red "FAIL". "FAIL" is upper-case and "pass" lower-case. In charts, 220 of 640 units are reserved for labels that are one to five characters in the Footnote slices, so bars use 47% of the width (fn-1280-light). All bars are one blue regardless of gated or report-only. Labels are cut at 30 characters with no ellipsis (line 78; no example exceeds 30, so this part is suspected). A baseline tick at 100% sits on the track's right edge and reads as an end cap (sb-1280-dark: all six ticks do). The two figures have no section heading and sit between the Summary table and "Rates", whose table repeats the second chart.
- Why it matters: A regression report should let the eye find what got worse. Here every delta has the same weight.
- Recommended fix: Tint negative and positive deltas with the existing `--fail`/`--pass` tokens and keep the sign glyph. Mute report-only rows. Size the label column to the longest label. Place each chart beside or under its own table heading. Add a small legend swatch for the baseline tick. Add an ellipsis on truncation.
- Status: verified (truncation: suspected)

### kappa.md and reproduction.md have duplicate rows and repetitive cells
- Severity: Minor
- Where: `examples/footnote/kappa.md` lines 21-27; `examples/footnote/reproduction.md` "Per cell" table
- Observed: In kappa.md, "pooled | opus" lists n, raw and kappa twice (rows 24 and 25 are character-identical "κ 0.17 | 0.17 | match"). The Note column repeats the Yardstick column on every matching row ("reference 20"). Five rows carry the same 200-character "needs the Sonnet re-judge verdicts…" sentence. The Figure column uses raw keys (`p_e`, `human_counts`, `disagree`). In reproduction.md, 49 "not reproducible" rows repeat four or five long reasons inline in the Result column, and some cells run over 300 characters (the U "code mismatch" lists). The "74 match" headline is hard to verify by eye among them.
- Why it matters: These two files are the README's evidence ("74 match, 0 differ"). Exact duplicate rows look like a counting error, and the result worth showing is buried in boilerplate.
- Recommended fix: De-duplicate the pooled rows, or label which source document each comes from. Leave Note empty on a match. Replace repeated reasons with footnote markers ([1]-[5]) defined once under the table. Group by cell with sub-headings, or list matches first.
- Status: verified (source read)

## Found clean
- D-30 is honoured: one static file, no `<script>`, no external URL, inline SVG, theme by `prefers-color-scheme`.
- There is no page-level horizontal overflow at 390 px in any of the three reports (scrollWidth equals clientWidth); overflow is contained in `.table-wrap`.
- Dark mode is coherent: tokens are remapped consistently, the bars, baseline ticks and badge remain legible, and there are no hard-coded light colours (sb-1280-dark, fn-390-dark).
- The type scale and spacing at desktop width are tidy: clear h1/h2 steps, tabular numerals, consistent row rhythm, and a sensible 960 px measure.
- "not reported" is used consistently instead of 0 in tables, in both formats.
- The "Failing items" table is clear and specific in both formats.
- `examples/report-example.md` (support-bot) reads well as a PR comment: its slice names are self-explanatory and it avoids most of the Footnote-specific problems.

## Not reviewed
- Markdown as rendered by GitHub: no external requests were allowed, so the markdown findings come from source and known GFM behaviour.
- Colour contrast ratios, screen-reader output of the SVG (`role="img"` with only the title as label) and focus order: left to the accessibility lens.
- Browsers other than Chromium, and high-DPI rendering (deviceScaleFactor 1 only as instructed).
- Printing from a dark-scheme system: not tested; only light-scheme print was rendered.
- A passing-gate report, the `warnings` banner (`.warn`), and the "first N of M" failing-items truncation: no committed example exercises them, and I generated only the degraded support-bot report.
- README prose and CLI output: other lenses.

