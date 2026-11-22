# PRD-G: Markdown escaping and name constraints

Review item 9. No decision needed.

## Problem

Target output (an error string, or the first 80 characters of an answer quoted by a scorer) reaches the
markdown report verbatim, and the report is posted as a PR comment and job summary: `@octocat` mentions,
`<img>` tags, links, `<details>`, the comment marker `<!-- yardstick:gate -->`, and a `\r` that ends a table
row. Suite, target, model, prompt hash and git SHA are not escaped at all: a suite name with newlines produced
a fake `**Gate: PASSED**` line, and a pipe adds a table column. Scorer keys are unconstrained: a key with a
pipe or a space shows a rate that no gate rule can name. An item id with a backtick closes its code span.

## Scope

- One escaper for free text in markdown, `md_text`: replace `&`, `<`, `>` with entities; backslash-escape
  markdown punctuation (`\ * _ [ ] ( ) # + ! | ~ >` and the backtick); break `@` with a zero-width joiner
  so it never mentions (`@⁠user`); replace `\r`, `\n`, tabs and other control characters with a space.
  This also neutralises `<!--`.
- `md_code` for values shown in code spans: strip control characters, pick a backtick fence longer than any
  run of backticks inside, pad with spaces when needed. Used for ids, scorer keys, rule labels, run ids and
  names.
- Every free-text value in `report.md.j2` goes through one of the two: suite name, target name and kind,
  model, prompt hash, git SHA, started_at, warnings, judge model/source/prompt hash, scorer labels, slice
  names, failing-item details, gate notes, and the "Item changes" ids.
- `ScorerSpec.key` and `name` must match `[A-Za-z0-9_.+-]+` at suite load (the pattern rate metrics already
  use), so every displayed rate can be gated. The committed suites already comply.
- Test: a run with hostile strings in every field renders with none of `@octocat`, `<img`, `](`, `<!--`,
  `\r` or a second `**Gate:` line surviving.

## Out of scope

The PR comment marker trust and redirect findings (item 17, Later).

## Acceptance

- G1. The hostile-strings test passes for the markdown report; the HTML report (autoescaped, D-30) is checked
  by the same strings.
- G2. A suite name with a newline and a pipe renders as one heading and one table cell.
- G3. A scorer key with a pipe or a space is rejected at load with exit 2.
- G4. Committed examples change only where escaping applies (verified by the regenerated diff).
