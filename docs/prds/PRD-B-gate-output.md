# PRD-B: Gate output a stranger can read

Review items 2 and 6. Decision 1 (a).

## Problem

1. The terminal prints `FAIL pass_rate floor: 0.583333 >= 0.85; max_drop: drop 0.416667 <= 0.02`: the
   requirement written as if it were a fact, in fractions, while `compare` and the reports use percentages.
   The report's "Checks" cell re-parses that text with a regex (`_humanise`), prints "drop −22.7 pt <= 2.0 pt"
   for a rise, and near a rounding boundary prints `85.0% >= 85.0% (FAIL)`.
2. Two visible defects in the committed examples: in `examples/footnote/report.md` the "Newly failing" and
   "Newly passing" bullets run together on one line, and in the HTML report `<code>` breaks rule names
   mid-word at desktop width (`rate:refusa / l[A+M]`).

## Decision applied

**1 (a):** value first, requirement in brackets, e.g.
`FAIL pass_rate 58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)`. The same single formatter prints one check
per line in reports.

## Scope

- `CheckResult` carries the numbers (`value`, `limit`), so the text is built from numbers, never parsed back.
  One formatter, `report.format.check_text(metric, check)`, used by the terminal and both reports.
- Wording per check:
  - floor: `58.3% (floor 85.0%)`; max: `1840 ms (max 2000 ms)`;
  - max_drop: `dropped 41.7 pt (max 2.0 pt)`, `rose 22.7 pt (max drop 2.0 pt)`, `no change (max drop 2.0 pt)`;
  - max_rise mirrors it (`rose ... (max 50 ms)`, `fell ... (max rise 50 ms)`);
  - min_items: `22 items (min 8)`; not reported: `not reported`; no baseline: `no baseline`.
- When the value and the limit print the same at one decimal but the check failed (D-12 compares at 6 dp),
  add decimals until they differ (up to 6). A zero limit prints `0.0 pt`, not `±0.0 pt`.
- Terminal: `FAIL    pass_rate                    58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)`. A
  failing rule prints its failing checks; a passing rule prints `ok`. Report-only notes stay after a `;`.
- Reports: the Checks cell lists every check, one per line (`<br>` in markdown cells and in HTML), each ending
  in `(ok)` or `(FAIL)`.
- Template fixes: newline after each "Item changes" bullet in `report.md.j2`; `code` uses
  `overflow-wrap: break-word` (and the rule column does not wrap) in `report.html.j2`.
- Regenerate the committed examples and update the README case-study gate table, which quotes the report.

## Out of scope

The report's first-screen layout (PRD-F) and CLI flag renames (item 21, Later).

## Acceptance

- B1. The terminal line for the degraded support-bot run reads
  `58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)` (test).
- B2. A rise against a `max_drop` reads `rose ... (max drop ...)`, never a negative drop (test).
- B3. 1699/2000 against floor 0.85 prints `84.95% (floor 85.0%)`, not `85.0% >= 85.0%` (test).
- B4. `examples/footnote/report.md` has the two "Item changes" bullets on separate lines; a test renders both
  lists non-empty.
- B5. The HTML template no longer contains `overflow-wrap: anywhere` (test).
- B6. `_humanise` (the regex re-parser) is gone.
