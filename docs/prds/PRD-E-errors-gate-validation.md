# PRD-E: Errors, exit codes and gate file validation

Review items 7 and 13. No decision needed.

## Problem

1. About 10 kinds of bad input end in a Rich traceback and exit 1, which D-18 reserves for a failed gate:
   `--fixed-clock notadate`, an unterminated `--cmd` quote, a non-executable `--cmd`, `-o` pointing at a
   directory, non-UTF-8 run/gate/results files, a suite input that is not JSON-serialisable (an unquoted YAML
   date), a NaN run cost, a replay file with an undeclared label, and in the http target a malformed
   `Content-Length`, deeply nested `fields`, a header name with a trailing newline and a non-ASCII URL.
2. Passing the wrong kind of file prints a wall of pydantic errors ("104 validation errors for Run", about
   310 lines, with input values and a URL).
3. A misspelt scorer name blames the items ("unknown scorers: ['contains-all']").
4. Gate file mistakes fail with no clear reason: `rules: []` prints only `gate FAILED`; an unknown slice does
   not list the run's slices; `floor: 85` and `max_drop: 2` on a rate are accepted (the latter can never
   fail); `floor: true` is coerced to 1.0; NaN thresholds are accepted.

## Scope

- One place turns a pydantic `ValidationError` into a short message:
  `error: <path> is not a <run|suite|gate> file: <first 3 problems as "loc: msg">` and, when the top-level
  keys look like another kind of file, `(it looks like a <kind> file)`. No input values, no URL.
- The CLI's commands run under one handler that maps `OSError`, `UnicodeDecodeError`, `ValueError`,
  `TypeError`, `RecursionError` and `JudgeError` to `error: ...` and exit 2. `typer.Exit` passes through.
  `pretty_exceptions_show_locals=False` is set explicitly.
- Specific fixes: `_read_structured` and the results-file reader catch `UnicodeDecodeError`; the command
  adapter turns `ValueError` from `shlex` and `OSError` from `Popen` into `AdapterError`; suite load checks
  that every item input is JSON-serialisable; the results-file adapter rejects a non-finite `run_cost_usd`;
  `RecordedJudge` errors exit 2 through the handler; in the http target, `Content-Length` is parsed only when
  it is ASCII digits, the three header/URL patterns use `fullmatch`, a non-ASCII URL is rejected, and
  `ValueError`/`RecursionError`/pydantic serialisation errors while handling a response become a failed
  request (D-62 then applies: exit 2 or a recorded item).
- Suite: scorer names are validated before items, `unknown scorer 'contains-al'; available: ...`.
- Gate file: `rules: []` is rejected at load (exit 2, "no rules"); for `pass_rate`, `mean_score` and `rate:*`
  the thresholds `floor`, `max`, `max_drop`, `max_rise` must be in [0, 1]; booleans and non-finite numbers
  are rejected for every metric; an unknown slice's check says `slice 'x' not in run (slices: a, b, c)`.

## Out of scope

The `command` adapter and run-file checks of item 16 (Later).

## Acceptance

- E1. A parametrised CLI test covers the review's cases; each exits 2 with a one-line `error:` and no
  traceback.
- E2. Passing a suite where a run is expected prints at most 5 lines.
- E3. A misspelt scorer name is named, with the available names.
- E4. The gate file cases (`rules: []`, `floor: 85` on a rate, `max_drop: 2` on a rate, `floor: true`,
  `floor: .nan`) exit 2 at load; an unknown slice names the run's slices.
- E5. The existing exit-2 tests still pass.
