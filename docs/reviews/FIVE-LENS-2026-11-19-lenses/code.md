# Five-lens review 2026-11-19: code lens, as returned

Unedited output of the code lens agent (repo `main` at `94949eb`, reviewed 2026-11-20), apart from sandbox paths shortened to `<sandbox>` and the agent's closing housekeeping line about session memory removed. Ranking and calls are in [`../FIVE-LENS-2026-11-19.md`](../FIVE-LENS-2026-11-19.md). Nothing here was fixed.

Repo root for every path below: `<sandbox>/lens-code` (main at 94949eb). Experiment scripts and hand-made suites, runs and gate files are in `<sandbox>/lens-code/runs/` (`e1.py`, `e2.py`, `srv.py`, `x/`). No tracked file was changed (`git status` clean) and no server is left running.

### A `rate:<key>` gate passes `min_items` on items that contributed nothing (YS-02 hole)
- Severity: Blocker
- Where: `src/yardstick/metrics.py:44-56` (`rates`, `slot[2] += 1` for every score, including 0/0); `src/yardstick/runner.py:25-39` (errored item gives a counting scorer 0/0); `src/yardstick/scorers/llm_judge.py:128` (budget-skipped item gives 0/0); `src/yardstick/gate.py:53-60`
- Observed: `runs/e1.py`, sections B and B2.
  - 10 items, `llm-judge` key `judge`, budget $1.00, $0.60 per call: 1 unit judged, 9 skipped. `rate:judge` = `hits=1 total=1 n_items=10`. Gate `min_items: 8, rate:judge floor 0.9` with a matching calibration returns `gate passed: True`, check text `10 item(s), need >= 8`.
  - 10 items, `label-rate`, target errors on 9 (or returns no row for 9): `hits=2 total=2 n_items=10`, `pass_rate 0.1`, yet `rate:sup floor 0.9, min_items 8` returns `gate passed: True`.
  - Only the "field not reported" case is counted correctly (`1 item(s), need >= 8`, fails).
- Why it matters: YS-02 says a gate never passes with fewer items than `min_items`, and D-26 says a rate gate counts "only items the scorer applied to". A judge that ran out of budget after one item, or a target that crashed on 90% of items, still passes a rate gate on a sample of one.
- Recommended fix: count an item toward a rate's `n_items` only when its score has `total > 0` (non-counting scorers always have 1). Add an invariant test for rate metrics with errored and budget-skipped items.
- Status: verified

### Judge verdicts gate without any kappa check when they arrive through `label-rate` (YS-05 bypass in the committed Footnote gate)
- Severity: Major
- Where: `src/yardstick/gate.py:95-100` (`judge_keys` only knows `llm-judge` scores and `run.judges`); `fixtures/gates/footnote.yaml` (rule `rate:support`, slice `A+M+V`); `fixtures/footnote/suite.yaml:19-28`
- Observed: running `fixtures/footnote/suite.yaml` over the judged cell `answers-hybrid-claude-sonnet-5-5-theta-on-…-2026-10-23T1646.json`, then `yardstick gate fn.json -c fixtures/gates/footnote.yaml`, prints `PASS    rate:support[A+M+V]          ok`. The report row reads `96.1% | … | floor: 96.1% >= 90.0% (ok) | pass`, with no "report-only" marking. This is the same Opus judge and the same 96.1% that `footnote-judged.yaml` demotes to report-only at κ 0.17.
- Why it matters: YS-05 says an LLM-judge metric with kappa below the floor or unknown never gates. D-23 and D-32 chose to gate on `support`, but nobody wrote down that this route skips YS-05. Any results-file project that maps a judge's labels into a field gets an uncalibrated judge gating.
- Recommended fix: add a way to mark a scorer as judge-derived (for example `judge: {model, prompt_hash}` on the `label-rate` spec, recorded in `run.judges`) so `judge_status` applies. At minimum, record a decision row and change the comment in `footnote.yaml`.
- Status: verified

### Many input errors escape as tracebacks with exit 1, which means "gate failed"
- Severity: Major
- Where: `src/yardstick/cli.py:252` (`parse_fixed`), `:255-261` (only `AdapterError`/`ScorerConfigError` caught), `:262` (`save_run`), `:79-83` and `src/yardstick/suite_io.py:19-29` (`UnicodeDecodeError` is not `OSError`), `cli.py:97-103` (`_write_or_echo`); `src/yardstick/adapters/command.py:38` (`shlex.split`), `:43-54` (only `FileNotFoundError`/`TimeoutExpired`); `src/yardstick/adapters/results_file.py:111`, `:126`; `src/yardstick/judge/recorded.py:64-66`
- Observed (all in `runs/x`, each ended in a Rich traceback and `exit=1`):
  - `run --fixed-clock notadate` gives `ValueError: Invalid isoformat string`.
  - `run --cmd "python3 'unterminated"` gives `ValueError: No closing quotation`.
  - `run --cmd ./noexec.sh` (not executable) gives `PermissionError`.
  - `run -o adir`, `report -o adir` and `gate --report adir` (a directory) give `IsADirectoryError`. For `gate` this happens on a passing gate.
  - `gate bad.json`, `compare bad.json …`, `gate -c badgate.yaml` and `run --results res-bad.json` on files that are not UTF-8 give `UnicodeDecodeError`.
  - A suite YAML with an unquoted date in an input (`as_of: 2026-11-14`) and `--cmd` gives `TypeError: Object of type date is not JSON serializable`.
  - A results file with `"spent": NaN` mapped to `run_cost_usd` gives `ValueError: Out of range float values are not JSON compliant: nan`.
  - `--judge replay:v2.json` whose `labels` has one label the scorer does not declare gives `JudgeError`.
- Why it matters: D-18 reserves exit 1 for a failed gate and 2 for bad input. In `action.yml` a `gate` exit of 1 sets `passed=false` and, with `fail-on-gate: "false"`, becomes only a warning. The README says the action "always fails on bad input (exit 2)".
- Recommended fix: wrap each command body in one handler that maps `OSError`, `UnicodeDecodeError`, `ValueError`, `TypeError` and `JudgeError` to `_fail` (exit 2). Catch `UnicodeDecodeError` in `_read_structured` and `ResultsFileAdapter.document`, and `OSError`/`ValueError` in the command adapter. Reject non-finite `run_cost_usd`. Validate that suite inputs are JSON-serialisable at load. Add a parametrised CLI test over these cases.
- Status: verified

### `yardstick report --gate` ignores the pinned baseline, so it prints "Gate: FAILED" where `yardstick gate` passes
- Severity: Major
- Where: `src/yardstick/cli.py:381-393` (`base = _load_run(baseline) if baseline else None`; no `baseline_mod.find`), against `cli.py:340`
- Observed: after the README quick start (`baseline pin runs/healthy.json`), `yardstick gate healthy.json -c fixtures/gates/support-bot.yaml` prints `gate PASSED`, exit 0. `yardstick report healthy.json --gate fixtures/gates/support-bot.yaml` prints `**Gate: FAILED**` with `max_drop: no baseline (FAIL)`, and exits 0.
- Why it matters: the same run and gate file give two verdicts depending on the command (D-18 describes auto-loading only for `gate`). `report` is the documented way to regenerate a report.
- Recommended fix: give `report` the same `--baselines-dir` lookup through `_resolve_baseline`, or print that no baseline was looked up. Add a test.
- Status: verified

### An item scored only by report-only scorers always fails, so a judge-only suite has pass rate 0%
- Severity: Major
- Where: `src/yardstick/runner.py:64-66` (`passed = bool(gating) and …`, mean 0.0); `src/yardstick/models.py:142-166` (suite validation does not reject it)
- Observed: `runs/e1.py` section A. A suite of 10 items whose only scorer is `llm-judge` (forced `report_only` by D-36), with every unit judged "good", gives `pass_rate 0.0 mean 0.0` beside `rate hits=10 total=10`. The report lists every item under "Failing items" as `no scorer applied`.
- Why it matters: D-25 and D-36 together make "the item has no gating scorer" a permanent failure, and no decision says so. `pass_rate`, `mean_score`, "newly failing" and any `pass_rate` gate are wrong for judge-only suites, and diluted for mixed suites where some items carry only report-only keys.
- Recommended fix: either reject at suite load any item whose `expected` keys are all report-only, or exclude such items from `pass_rate`/`mean_score` and show them as "not scored". Record the choice as a decision.
- Status: verified

### The `command` target aborts on valid JSONL that contains U+2028, U+2029, NEL or other Unicode line separators
- Severity: Major
- Where: `src/yardstick/adapters/command.py:63` (`stdout.splitlines()`)
- Observed: `runs/x/ls.py` prints one valid JSON object per line with `ensure_ascii=False` and an output text containing U+2028. `yardstick run … --cmd "python3 ls.py"` ends with `error: stdout line 1 is not JSON: Unterminated string starting at`, exit 2.
- Why it matters: `str.splitlines` also splits on `\x0b`, `\x0c`, `\x1c-\x1e`, `\x85`, U+2028 and U+2029. Node's `JSON.stringify` and Python with `ensure_ascii=False` write these raw, and model output does contain them. A whole run is lost (D-14 treats it as a malformed line) on output that follows the documented protocol.
- Recommended fix: `stdout.split("\n")`, stripping a trailing `\r`. Add a test with U+2028 and `\x85` in an output.
- Status: verified

### A comment-step crash fails the job and skips the verdict step (contradicts D-44)
- Severity: Minor
- Where: `src/yardstick/github_comment.py:68-75` (`json.loads` and `resp.read()` outside any handler), `:49` (`event.get("pull_request", {}).get`), `:152` (`read_text` outside the `try`), `:155` (only `HttpError`, `OSError`); `action.yml` steps "Comment on the pull request" (`set -euo pipefail`) and "Verdict" (no `always()`)
- Observed: with `GITHUB_API_URL=http://127.0.0.1:8831` served by `runs/srv.py`:
  - a 200 response with an HTML body gives `json.decoder.JSONDecodeError`, exit 1;
  - a truncated body gives `http.client.IncompleteRead`, exit 1;
  - an event file `{"pull_request": null}` gives `AttributeError: 'NoneType' object has no attribute 'get'`, exit 1.
- Why it matters: D-44 says any comment error "is a warning and never changes the gate's verdict". Here a passing gate turns into a failed job, and the Verdict step never runs.
- Recommended fix: in `main`, catch `Exception` around `post` and the report read, and print `::warning::`. Guard `pull_request` with `isinstance(…, dict)`. Extend `test_main_never_fails_the_job_on_comment_errors` beyond `HttpError`.
- Status: verified

### Report check text contradicts its own verdict after rounding
- Severity: Minor
- Where: `src/yardstick/report/markdown.py:278-291` (`_humanise` re-parses `%.6g` text and reformats to one decimal); `src/yardstick/report/format.py:14-37`
- Observed (`runs/e1.py` section C):
  - 1699/2000 against floor 0.85 and `max_drop: 0` (baseline 1700/2000) prints `floor: 85.0% >= 85.0% (FAIL); max_drop: drop 0.1 pt <= ±0.0 pt (FAIL)`. The Summary row shows `85.0% | 85.0% | −0.1 pt`.
  - 179/200 against baseline 180/200 with `max_drop: 0.0045` prints `drop 0.5 pt <= 0.4 pt`.
- Why it matters: the verdict is right (D-12 compares at 6 dp), but the PR comment shows a true-looking statement marked FAIL. The limit for `max_drop: 0` renders as `±0.0 pt`.
- Recommended fix: build the humanised text from `RuleResult` numbers, not by regex over the detail string. When both sides print equal but the check fails, add decimals until they differ. Format a zero limit as `0.0 pt`.
- Status: verified

### Gate thresholds are not range-checked: `max_drop: 2` on a rate always passes, and `floor: true` is accepted
- Severity: Minor
- Where: `src/yardstick/models.py:408-424`
- Observed:
  - `rules: [{metric: pass_rate, max_drop: 2}]` on the degraded run (100% to 58.3%) prints `PASS pass_rate ok`, `gate PASSED`.
  - `floor: true` is coerced to 1.0 and passes on a 100% run.
  - `floor: 85` is accepted and fails with `1 >= 85`.
  - `floor: .nan` and `max_drop: .nan` are accepted (they fail closed).
- Why it matters: D-12 defines `max_drop: 0.02` as two points. A user who writes `2` gets a gate that can never fail and no warning.
- Recommended fix: for `pass_rate`, `mean_score` and `rate:*`, require `floor`, `max`, `max_drop` and `max_rise` in [0, 1]. Reject booleans and non-finite values for every metric.
- Status: verified

### The `command` adapter coerces telemetry that the other two adapters reject, and a target that prints nothing yields a "successful" run
- Severity: Minor
- Where: `src/yardstick/adapters/command.py:80-86` (raw row values passed to `Output`, pydantic lax mode); `src/yardstick/runner.py:92` (`NO_OUTPUT`)
- Observed:
  - A row `{"latency_ms": true, "cost_usd": "0.5", "refused": "yes"}` is stored as `latency_ms: 1, cost_usd: 0.5, refused: True` (`runs/x/boolat.json`).
  - `"cost_usd": NaN` is silently stored as `null`.
  - `--cmd "python3 -c pass"` exits 0 with `0/12 passed`, every item "no output from target", and the gate then exits 1.
- Why it matters: `true` recorded as 1 ms is an invented number (YS-04). `results_file.py` and `http.py` reject booleans and strings explicitly. D-62 separates "target is broken" (exit 2) from "answers got worse" (exit 1), yet a command that outputs nothing lands in the second group. D-14 does not say what a missing id means.
- Recommended fix: apply the type checks `http.py` uses (`_number`, bool rejection, int-only latency) in `_parse`. Decide and record whether zero rows from a command, or missing ids, is an `AdapterError`.
- Status: verified

### Baseline file names collide and `baseline pin` overwrites without notice
- Severity: Minor
- Where: `src/yardstick/baseline.py:15-16` (`_SAFE.sub('-', …)`), `:19-22`; `src/yardstick/cli.py:443-445`
- Observed:
  - `baseline_path("日本","t")` and `baseline_path("中文","t")` both give `-__t.json`.
  - `("a b","c")` equals `("a-b","c")`, and `("a","b__c")` equals `("a__b","c")`.
  - `baseline pin degraded.json` over a pinned healthy baseline prints only `pinned … -> …`; the gate then loses its `max_drop` failure.
- Why it matters: two targets of one suite named `x y` and `x-y` silently share a baseline. Two suites with non-ASCII names overwrite each other, and the next gate exits 2 with "suite hash differs". Pinning a worse run is silent (D-04 relies on PR review to catch it).
- Recommended fix: keep Unicode word characters and append a short hash of the raw `suite::target` when sanitising changed anything. In `find`, check that the loaded run's `suite_name` and `target.name` match. On pin, print the run id being replaced.
- Status: verified

### Run files are trusted: `schema_version`, duplicate item ids and `run_id` are not checked on load
- Severity: Minor
- Where: `src/yardstick/models.py:290-323` (`Run`); `src/yardstick/suite_io.py:40-41`
- Observed:
  - `healthy.json` edited to `schema_version: 99` gates as `gate PASSED`.
  - A run whose 12 items are one item repeated 12 times passes `pass_rate` with `min_items: 10` (`12 item(s)`).
  - `run_id` is never recomputed.
- Why it matters: D-24 says an older Yardstick cannot read newer runs, but that rests only on `extra="forbid"`. Duplicate ids inflate `min_items` (YS-02) for hand-made or converted run files and baselines, although the adapters reject duplicates.
- Recommended fix: have a `Run` validator reject `schema_version != RUN_SCHEMA_VERSION` and duplicate `item_id`s. Optionally warn when `compute_id` differs from the stored `run_id`.
- Status: verified

### Live judge: API failures are charged at the estimate and never stop the run
- Severity: Minor
- Where: `src/yardstick/judge/anthropic.py:117-129`; `src/yardstick/scorers/llm_judge.py:111-112`; `src/yardstick/judge/budget.py:42-49`
- Observed (read, not run): on a transport error, a non-200 status or an unreadable body, the reply is `JudgeReply(None, None, …)`, and `Budget.charge` adds the full estimate. A wrong API key (401 on every call) therefore yields a completed run with every unit "without a valid label" and `spent_usd` near the cap, although nothing was billed. Exit code is 0.
- Why it matters: D-37 says "the estimate if unknown", which is safe for the cap, but the Judges table then reports a spend that did not happen (the spirit of YS-04). An auth or config failure looks like a judge that gave bad labels.
- Recommended fix: raise `JudgeError` (exit 2) on 401/403/404. Charge 0 for failures where no request body was accepted. Record failed calls separately from invalid labels.
- Status: verified (read directly; no live call made)

### A calibration with almost no data is enough to make a judge rule gate
- Severity: Minor
- Where: `src/yardstick/gate.py:103-125` (`judge_status`); `src/yardstick/kappa.py:88-125`
- Observed: `runs/e1.py` section B. A calibration from 3 graded units (`kappa 1.0 n 3`) gives `judge kappa 1.00 (n 3) >= floor 0.6` and the rule gates. `missing` (graded units with no verdict) is not considered either.
- Why it matters: YS-05 rests on kappa being meaningful. D-40 lists the "unknown" cases (no record, zero or two calibrations, undefined kappa) but sets no minimum n.
- Recommended fix: add `judge.min_graded` (default about 30) to `JudgePolicy`, treat `pooled.n` below it as unknown, and show `missing` in the note.
- Status: verified

### Scorer keys, suite names and target names are not constrained to what gates and reports can handle
- Severity: Minor
- Where: `src/yardstick/models.py:43` (`_RATE_METRIC`) against `ScorerSpec.key` (no pattern); `src/yardstick/report/templates/report.md.j2:1,8,9`
- Observed:
  - Suite `name: "my suite | v2"` renders the header row as ``| Suite | `my suite | v2` (…) |``, which adds a table column. The H1 and the Target row are also unescaped.
  - Scorer `key: "k|pipe"` shows a rate in the report, but a rule on `rate:k|pipe` is rejected as `unknown metric`. The same holds for keys with spaces or colons.
  - An item id containing a backtick closes the code span early (`` `tick`s` ``).
  - Ids in table cells and slices are escaped correctly (`\|`, newline to space).
- Why it matters: a rate can be displayed but never gated, and one pipe in a suite name breaks the PR comment's first table.
- Recommended fix: validate `ScorerSpec.key`/`name` against `[A-Za-z0-9_.+-]+` at suite load. Pass suite, target, model, prompt hash and git SHA through `md_cell`. Escape backticks in ids, including in the "Item changes" list.
- Status: verified

### `contains-all` counts a whitespace-only expected string as found
- Severity: Minor
- Where: `src/yardstick/scorers/contains_all.py:16-21, 27`
- Observed: `ContainsAll()([" "], Output(text="anything"), {})` returns `Outcome(score=1.0, passed=True)`. A non-breaking space behaves the same.
- Why it matters: this is the D-20 problem in another scorer: the string normalises to empty, which is a substring of everything, so the check can never fail.
- Recommended fix: reject expected strings that are empty after `normalize_text` with `ScorerConfigError`.
- Status: verified

### Two tests assert less than their names and decisions claim
- Severity: Minor
- Where: `tests/test_backcompat.py:31-35`; `tests/invariants/test_ys02_min_items.py`; `tests/test_rates.py:141-150`
- Observed:
  - `test_report_only_false_does_not_change_suite_hash` asserts `suite.content_hash == load_suite(same file).content_hash`, a value compared with itself. No Phase 1 suite hash or run id is pinned as a literal, yet D-24 says "byte-identical (tested)". The only real pin is the CI check that `examples/report-example.md` regenerates identically.
  - The YS-02 invariant tests cover only `pass_rate` and `mean_score`. The rate test covers only the "empty label list" case, which is why the first finding passes the suite.
- Why it matters: a change to hashing or to rate counting would not be caught by the tests named for it.
- Recommended fix: pin the literal `content_hash` of `fixtures/suites/support-bot.yaml` and one run id. Add errored and budget-skipped items to the YS-02 property test for `rate:*`.
- Status: verified

### Docs and code disagree in small ways
- Severity: Minor
- Where: `pyproject.toml` (`license = { text = "MIT" }`); `README.md` "GitHub Action" and "Pieces"; `docs/PRD.md` §3
- Observed:
  - There is no `LICENSE` file in the repo.
  - The README's action input list omits `run-path` and `github-token`, which `action.yml` defines.
  - The README "Gates" line omits the `slice` and `judge` keys.
  - PRD §3 lists 8 scorers; the registry has 10 (`field-equals`, `label-rate` added by D-23 and D-26).
  - PRD §3 writes gates as `supported_rate >= 0.85`, `drop <= 0.02`; the real keys are `rate:<key>`, `floor`, `max_drop`.
  - `requires-python >=3.12,<3.13` excludes 3.13. The action copes through `uv … --python 3.12`; a `pip install` on 3.13 does not.
  - D-48 to D-57 unused is explained by D-58; this is not a defect.
- Why it matters: a public repo that claims MIT without a licence text, and users who cannot find documented inputs.
- Recommended fix: add `LICENSE`, complete the README input list, and add a note to PRD §3 pointing at D-23 and D-26.
- Status: verified

## Found clean
- **Percentiles (D-10):** `ceil(pct/100*n)` matches integer arithmetic for p50 and p95 for every n from 1 to 5000.
- **Fail-closed gates (D-11):** an empty rule list, a missing slice, a `rate:` key that does not exist, a not-reported metric, an empty suite (0 items), `max_drop` with no baseline and NaN thresholds all fail. `min_items: 0` and a misspelt metric name exit 2 with a clear message.
- **D-12:** 0.92 to 0.90 passes a 0.02 gate (existing test; the logic reads correctly).
- **YS-03:** `compare` and `gate` across different suites exit 2 with the hash message. With `--allow-suite-change` the warning appears once in the report.
- **YS-05 for `llm-judge` keys:** no judge record, no calibration, a wrong model or prompt hash, two calibrations, and kappa below the floor are all report-only. A gate made only of report-only rules fails.
- **Budget (D-37):** spend is re-rounded to 9 dp on every charge, so nothing accumulates. A call is refused when `spent + estimate > cap`. Without an overrun, spend can exceed the cap by at most about 5e-10.
- **Kappa:** p_e = 1 gives `None`; empty input, unequal lengths and labels outside the set raise and exit 2; duplicate keys inside a grade set are rejected; n = 0 prints "not computed".
- **D-17:** the same content with a different `started_at` gives the same run id; repeated command and http runs are byte-identical (existing tests).
- **Duplicate suite item ids** are rejected at load. Duplicate, unknown and non-string ids are rejected by both the command and results-file adapters.
- **Markdown and HTML** render for 0 items, all items errored and no baseline. Signs and units of changes are correct (`−100.0 pt`, `n/a` when one side is not reported, `not reported (k/n items)`).
- **Comment handling:** pagination stops correctly on a short page, and truncation lands exactly on 65,536 characters with the note.
- **`http.py`** (by reading): non-finite numbers, booleans, wrong types, the size limit, the whole-request deadline and `on_error` are all handled, and nothing is measured locally (D-65).
- **`numeric-tolerance` (D-21):** the listed cases hold (`INV-2026`, dates, `5-10`, `.5`, `1,250.00`).

## Test coverage notes
- **Hypothesis** is used for the aggregators, as PRD §6 says (`tests/test_metrics.py`, `tests/test_rates.py`, the YS-01, YS-02, YS-04 and YS-05 invariants, kappa, budget).
- **CLI error paths:** `test_bad_inputs_exit_2` covers two cases, a missing file and a missing binary. None of the tracebacks in the third finding has a test.
- **Not tested:** `report --gate` without `-b`; baseline name sanitising and collisions; pin overwrite; `Run` load validation; `_humanise` near rounding boundaries; report-only-only items; `github_comment.main` with non-`HttpError` failures; Unicode line separators and type coercion in the command adapter.
- **YS-04** is asserted on metrics and markdown only, not on HTML, `compare` output or judge spend.
- **Possible flakiness:**
  - `tests/test_http_adapter.py::test_slow_drip_response_times_out` asserts wall time under 2.0 s for a 0.4 s deadline.
  - `_slow` relies on 0.3 s against 1.5 s, and `tests/test_command_adapter.py::test_timeout` on 0.5 s against 5 s.
  - `closed_port_url()` binds, closes and reuses a port number, which is a small race.
  - CI uses fixed port 8808 with a retry loop, which is fine on a fresh runner.
  - Test servers otherwise bind port 0.

## Not reviewed
- Secrets handling, header scrubbing and the action's injection surface (`run-args` word splitting, env passing): owned by the security reviewer.
- `adapters/footnote.py`, `footnote_scorecard.py`, `footnote_kappa.py`: only exercised through the README commands (suite run, judged replay), not read line by line, because they are project-specific and the brief asked for a lighter touch.
- `report.html.j2` beyond the first 80 lines, and HTML and SVG well-formedness: left to the report-design and accessibility reviewers.
- The live Anthropic judge and the `http` target against a real service: no LLM calls or external requests were allowed.
- `action.yml` end to end on a GitHub runner: read only.
- Windows paths: out of scope per the brief.

