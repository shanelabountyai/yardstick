# Five-lens review 2026-11-19: ux lens, as returned

Unedited output of the ux lens agent (repo `main` at `94949eb`, reviewed 2026-11-20), apart from sandbox paths shortened to `<sandbox>` and the agent's closing housekeeping line about session memory removed. Ranking and calls are in [`../FIVE-LENS-2026-11-19.md`](../FIVE-LENS-2026-11-19.md). Nothing here was fixed.

### Terminal gate lines print a false-looking inequality under FAIL, in fractions the rest of the tool shows as percentages
- Severity: Major
- Where: `uv run yardstick gate runs/degraded.json -c fixtures/gates/support-bot.yaml --report runs/report.md` (README.md line 17); format built in `src/yardstick/gate.py` lines 66, 69, 82 and printed by `src/yardstick/cli.py` about line 354
- Observed: `FAIL    pass_rate                    floor: 0.583333 >= 0.85; max_drop: drop 0.416667 <= 0.02` and `FAIL    pass_rate[refusal]           floor: 0.5 >= 1`. The markdown report for the same gate says `floor: 58.3% >= 85.0% (FAIL)`, and `compare` prints `58.3%` and `−41.7 pt`.
- Why it matters: This is the punchline of the ten-minute demo. A viewer reads "0.583333 >= 0.85" as a claim that is plainly untrue, then has to work out that it is the requirement that was not met. The six-decimal fractions also do not match the percentages on the next command's output.
- Recommended fix: Print actual value, requirement and outcome separately, in the report's units, e.g. `FAIL  pass_rate  58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)`. Reuse the formatter the markdown report already uses.
- Status: verified

### Pointing a command at the wrong kind of file prints a wall of raw pydantic errors
- Severity: Major
- Where: `uv run yardstick gate fixtures/suites/support-bot.yaml -c fixtures/gates/support-bot.yaml`; `_load_run` in `src/yardstick/cli.py` lines 79-83
- Observed: `error: fixtures/suites/support-bot.yaml: 104 validation errors for Run`, followed by about 310 lines of `Field required [type=missing, input_value={...}]` and `For further information visit https://errors.pydantic.dev/2.14/v/missing`. Swapping the gate's two files (`-c runs/healthy.json`) gives 11 errors, `baseline pin <gate file>` gives 8, and an empty suite file gives `Input should be a valid dictionary or instance of Suite`.
- Why it matters: Mixing up suite, run and gate paths is the most likely slip in a live demo, since all three are YAML or JSON paths on adjacent lines. The result scrolls the terminal off screen and shows library internals and an external URL.
- Recommended fix: Catch `ValidationError` in one place and print a single line saying what was expected, e.g. `error: X is not a run file (missing run_id, suite_hash, ...); did you pass a suite?`. Show at most the first three field errors, without `input_value` or the pydantic URL.
- Status: verified

### README has no prerequisites and the quick start never says what you should see
- Severity: Major
- Where: README.md lines 7-21
- Observed: The quick start opens with `uv sync`. There is no `git clone` line, no mention that uv is required, no install link, and no Python version (`pyproject.toml` requires `>=3.12,<3.13`; this machine's `python3` is 3.13.18). The only stated outcome is the comment `# exit 1`. Expected output is behind a link to `examples/report-example.md`. All five commands worked as written here.
- Why it matters: A reader without uv stops at the first line. A hiring manager who only reads never sees a failing gate, which is the product. The targets also call bare `python3`, so the reader needs to know any Python 3 on PATH will do for the fake target.
- Recommended fix: Add a two-line "Requirements" note (uv, link; uv fetches Python 3.12) and a `git clone` + `cd` line. Paste the four-line gate output under the quick start with one sentence: "exit 1 means regression, exit 2 means broken setup".
- Status: verified (uv-less machine not tested; uv was preinstalled)

### A README command is a placeholder that fails if pasted
- Severity: Major
- Where: README.md line 35: `uv run yardstick run ... --theta-prime 0.52`
- Observed: Pasted as written it prints `Missing option '--suite' / '-s'.` and exits 2. It sits inside a block where every other line is runnable. With the full arguments from line 30-32 plus `--theta-prime 0.52` it works (`32/41 passed`).
- Why it matters: Anyone pasting the block top to bottom hits an error mid-demo. The θ′ concept is also unexplained at that point.
- Recommended fix: Write the full command with a distinct `-o runs/dense-sonnet-theta.json`, or move it to prose: "add `--theta-prime 0.52` to the run above".
- Status: verified

### Footnote and judge gate commands exit 1 without the README saying so, and one failure is a missing baseline
- Severity: Major
- Where: README.md line 33 and line 61
- Observed: Line 33 prints `FAIL    rate:refusal[A+M]            floor: 0.863636 >= 0.9; max_drop: no baseline`, two more FAILs, `gate FAILED`, exit 1. The README never pins a baseline for that run and has no `# exit 1` comment there, unlike line 17. Line 61 is commented only `# judge rule: report-only (κ 0.17 < 0.6)` but also ends `gate FAILED`, exit 1.
- Why it matters: A newcomer cannot tell an intended failure (D-32: Footnote misses its own targets) from a setup mistake. "no baseline" looks like the latter. In a chained demo script the unannounced exit 1 stops the run.
- Recommended fix: Annotate both lines with `# exit 1: Footnote misses its own targets (D-32)`. For line 33, either pass `--baseline` as `examples/make-example.sh` does or say the drop check fails closed without one (D-11).
- Status: verified

### Missing baseline gives no hint how to fix it and exits 1, the same code as a regression
- Severity: Major
- Where: `uv run yardstick gate runs/healthy.json -c fixtures/gates/support-bot.yaml --baselines-dir runs/probe/nobase`; `src/yardstick/gate.py` line 74
- Observed: `FAIL    pass_rate                    max_drop: no baseline`, `gate FAILED`, exit 1, on a run that is 12/12. Dropping `--target-name fake` from the quick-start run produces the same thing, because the target name defaults to `command` and the lookup is `<suite>__<target>.json`. The message names neither the path searched nor `yardstick baseline pin`.
- Why it matters: Failing closed is deliberate (D-11). But D-18's stated reason for separate codes is that "CI can tell a regression from a broken setup", and a never-pinned baseline is a setup problem that reports as a regression. The user also gets no next step.
- Recommended fix: Keep the fail-closed verdict but print `no baseline at .yardstick/baselines/support-bot__command.json; pin one with: yardstick baseline pin <run>`. Consider exit 2 for this case, or record in DECISIONS that it is intentionally exit 1.
- Status: verified

### A typo in a scorer name blames the items instead of the scorer
- Severity: Major
- Where: `uv run yardstick run -s runs/probe/unk.yaml ...` (support-bot suite with `- name: contains-al`)
- Observed: `1 validation error for Suite / Value error, item 'faq-reset-password' has expected values for unknown scorers: ['contains-all'] [type=value_error, input_value={'name': 'support-bot', '...` plus the pydantic URL. The misspelled `contains-al` is never mentioned and the valid names are not listed. A gate-file metric typo does this well: `unknown metric 'latency_p59_ms'; use one of [...]`.
- Why it matters: The message points at the one correctly spelled thing in the file. Anyone writing a first suite will hit this.
- Recommended fix: Validate scorer names first: `unknown scorer 'contains-al'; available: contains-all, exact, ...`. Strip the pydantic wrapper as in the earlier finding.
- Status: verified

### Exit codes are not fully documented in `--help` or the README
- Severity: Minor
- Where: `yardstick --help`, `yardstick gate --help`, `yardstick run --help`; README.md
- Observed: `gate` help says only `Exit 0 if it passes, 1 if it fails.` Exit 2 appears nowhere in help. The 0/1/2 scheme (D-18) lives in the `cli.py` docstring; the README mentions exit 2 only in the HTTP and Action sections. Behaviour was consistent in every probe: usage, missing file, bad YAML, two targets, suite mismatch and missing judge budget all gave 2; gate failure and reproduction differences gave 1. One exception: bare `yardstick`, `yardstick baseline` and `yardstick footnote` print help and exit 2.
- Why it matters: The three-way split is a selling point for CI and is invisible to someone exploring with `--help`.
- Recommended fix: Add "Exit codes: 0 ok / gate passed, 1 gate failed, 2 bad input or target failure" as an epilog on the top-level and `gate` help, and one line in the README quick start.
- Status: verified

### Flag and command names are inconsistent across commands
- Severity: Minor
- Where: `--help` for `run`, `gate`, `report`, `kappa`, `baseline`
- Observed:
  - The gate file is `-c/--config` on `gate` but `-g/--gate` on `report`.
  - `gate --report PATH` writes markdown, alongside a separate `report` command and `gate --html-report`.
  - `-h` and `--version` are rejected (`No such option: -h`).
  - Booleans display as `<bool>` (`--no-git <bool>`), which suggests they take a value.
  - `baseline` has only `pin`; `baseline list` and `baseline show` give `No such command`.
  - Positionals show as `{run_path}`, `{run_a}`.
  - `run` has no short forms for its targets and does not mark that exactly one of `--cmd`, `--results`, `--http` is required.
- Why it matters: Each one is small, but together they are what a CLI-literate reviewer notices in the first minute.
- Recommended fix: Use `-c/--config` (or `--gate`) on both commands; rename `gate --report` to `--md-report`, keeping the old name as an alias; add `-h` and `--version` via `context_settings`; add uppercase metavars (`RUN`); state "exactly one of" in the `run` help text.
- Status: verified

### `footnote kappa --help` and the README use internal jargon
- Severity: Minor
- Where: `uv run yardstick footnote kappa --help`; `yardstick --help`; README.md lines 5, 49-51, 100-106
- Observed: Help text reads `Phase 3 gate: reproduce Footnote's eval:kappa figures through Yardstick.`, `Answers file of the judged run (1646).` and `(calibration for YS-05)`. The README's second line is `Build-log #26. Status: **Phases 1-5 are on main**`, and it uses YS-05, D-42, D-46 and θ′ before explaining them. The run summary prints `judge judge: claude-opus-5-5 (...)`, because the scorer key is also `judge`.
- Why it matters: "Phase 3 gate" and "YS-05" mean nothing to someone who has not read `docs/`. The opening of the README spends a hiring manager's attention on project bookkeeping.
- Recommended fix: Help text: "Check Yardstick's kappa against the figures Footnote recorded." Move build-log and phase status to a "Status" section at the bottom. Gloss YS-05 once ("judge metrics cannot gate until calibrated"). Print `judge [key=judge]: ...`.
- Status: verified

### `rate:refusal[A+M] 86%` reads as a refusal rate but means "answered as expected"
- Severity: Minor
- Where: `uv run yardstick gate runs/dense-sonnet.json -c fixtures/gates/footnote.yaml`; README.md table lines 112 and 116; scorer key from `yardstick footnote suite` (D-23)
- Observed: `FAIL    rate:refusal[A+M]            floor: 0.863636 >= 0.9`. The gate file's comment says this is "Answered or partial on answerable questions". The metric is the hit rate of the `refusal` scorer, i.e. the share that correctly did not refuse.
- Why it matters: In the case-study table a reader sees "refusal on answerable questions: 63.6%, pass" and concludes the assistant refuses most answerable questions.
- Recommended fix: Rename the generated scorer key (e.g. `refusal-correct` or `answered`). That changes the suite hash under D-17, so it needs a re-pin. Alternatively add a label column or footnote in reports and the README table.
- Status: verified

### The judge section's `kappa -o runs/calibration.json` output is not used by the next command
- Severity: Minor
- Where: README.md lines 58-61; `fixtures/gates/footnote-judged.yaml` (`calibrations: ../footnote/judge/calibration-opus-1646.json`)
- Observed: The README says `# kappa per grade set and pooled -> a calibration file a gate can use` and writes `runs/calibration.json`. The gate on the next line passes no `--calibration`; the gate file loads the committed fixture instead. The `kappa` output also lists each disagreement twice (per sheet, then pooled): 14 lines for 7 disagreements.
- Why it matters: The demo implies a flow from run to kappa to gate, but the middle step's output is ignored. A sharp viewer will ask why.
- Recommended fix: Add `--calibration runs/calibration.json` to the README gate line, or reword the comment to say the gate file already points at the committed copy. Drop the pooled disagreement list or put it behind `--verbose`.
- Status: verified

### Following the README leaves an untracked `.yardstick/` in the repo; `-o` creates any missing directories
- Severity: Minor
- Where: `uv run yardstick baseline pin runs/healthy.json`; `.gitignore`; `uv run yardstick run ... -o /nonexistent/dir/x.json`
- Observed: After the quick start, `git status --short` shows `?? .yardstick/`. `/runs/` is ignored; `.yardstick/` is not. Separately, a mistyped absolute `-o` path succeeded and created `/nonexistent/dir/x.json` with exit 0. `baseline pin` overwrites an existing baseline without saying so.
- Why it matters: Baselines are meant to be committed in the target repo (D-04), so not ignoring the directory globally is defensible. But in Yardstick's own clone the demo leaves a dirty tree, with a risk of committing a demo baseline. Silent directory creation hides path typos.
- Recommended fix: Add one README line ("the quick start writes `runs/` (ignored) and `.yardstick/baselines/`; delete the latter afterwards"), or use `--baselines-dir runs/baselines` in the quick start. Have `pin` print `replaced <old id>` when it overwrites.
- Status: verified

### Empty gate rules, an unknown slice and a percent-style threshold fail without a clear explanation
- Severity: Minor
- Where: `uv run yardstick gate runs/healthy.json -c <file>` with `rules: []`, `slice: refusals`, `floor: 85`
- Observed:
  - `rules: []` prints only `gate FAILED` (exit 1), with no reason.
  - `slice: refusals` prints `FAIL    pass_rate[refusals]          min_items: 0 item(s), need >= 4; reported: pass_rate[refusals] not reported`, exit 1, with no list of the run's slices.
  - `floor: 85` prints `floor: 1 >= 85`, exit 1.
- Why it matters: Failing closed is correct (D-11). But these are config mistakes that report as regressions (exit 1) and do not say what is wrong.
- Recommended fix: Print `gate FAILED: no rules in <file>`; for an unknown slice add `slice 'refusals' not in run (slices: account, faq, refusal)`; reject or warn on a rate `floor` above 1 at load, with exit 2.
- Status: verified

### `compare` columns go out of alignment and file errors repeat the path
- Severity: Minor
- Where: `uv run yardstick compare runs/healthy.json runs/degraded.json`; `uv run yardstick run -s fixtures/suites/nope.yaml ...`
- Observed: Rows with long names shift left by two columns, e.g. `rate:citation-grounded[account]           100.0%           100.0%        ±0.0 pt` against `pass_rate[account]                     100.0%            75.0%       −25.0 pt`. `compare` prints 22 rows with no flag to limit them to changed metrics. Missing files print `error: fixtures/suites/nope.yaml: cannot read fixtures/suites/nope.yaml: No such file or directory`. A missing replay file leaks `[Errno 2] No such file or directory: 'nope.json'`.
- Why it matters: This is cosmetic, but `compare` is the last command of the quick start and is what stays on screen.
- Recommended fix: Size the name column to the longest metric name; add `--changed-only`, or print the changed rows first; drop the duplicated path prefix in `_fail` callers.
- Status: verified

## Found clean
- All five quick-start commands (README lines 10-18) ran as written. Run summaries are one line each (`sha256:12e96079a9074ae8  support-bot  12/12 passed  -> runs/healthy.json`), the gate exits 1 and `compare` ends with `newly failing: acct-cancel, ...`.
- The Footnote, judge and HTTP sections ran as written, apart from the placeholder on line 35. `footnote reproduce` and `footnote kappa` exited 0 with `19 match, 0 differ, 5 not reproducible`. The HTTP flow passed against the fixture server on port 8811, which was stopped afterwards.
- `--help` works at every level (top, `run`, `gate`, `compare`, `report`, `kappa`, `baseline`, `baseline pin`, `footnote` and its subcommands), with required options starred.
- These messages are short and actionable, all exit 2:
  - `give exactly one target: --cmd PROGRAM, --results FILE or --http CONFIG`
  - `--results needs --mapping (footnote, or a mapping YAML file)`
  - `--judge needs --judge-budget-usd (the cap on judge spend for this run, D-37)`
  - `the suite has an llm-judge scorer: pass --judge and --judge-budget-usd (D-34)`
  - `--judge must be replay:VERDICTS.json or anthropic:MODEL`
  - `command not found: nosuchprogram`
  - `http target: item 'faq-reset-password': connection failed (ConnectionRefusedError)` and `HTTP 404`
  - `suite hash differs (...): re-pin the baseline, or pass --allow-suite-change to compare anyway`
  - a gate metric typo, which lists the valid metrics
  - a bad YAML suite, which gives line and column
- Verdict lines go to stdout and `wrote ...` and errors go to stderr, so piping works. The YS-05 demotion line is clear: `(pass)  rate:judge[A+M+V]  ok; report-only (YS-05): judge kappa 0.17 (n 40) < floor 0.6`.
- The markdown report's gate table is well worded: `floor: 58.3% >= 85.0% (FAIL)`.

## Not reviewed
- `uv sync` from a cold machine, including the uv install and the Python 3.12 download: the clone was already synced and I ran offline.
- The live `anthropic:` judge path and anything needing a key or an external service: excluded by the brief.
- `action.yml` behaviour on GitHub and the PR comment: I read the README section only.
- HTML report appearance: generated but not opened in a browser (design and accessibility lenses).
- `examples/make-example.sh`: read, not run.
- pytest, ruff and mypy: code lens.
- The absence of a LICENSE file (pyproject says MIT): noticed, not assessed.

## Housekeeping for the caller
- One probe (`-o /nonexistent/dir/x.json`) wrote a file outside the working directory: `/nonexistent/dir/x.json` (5.5 KB). The sandbox blocked my removal, so it is still there and needs deleting by hand.
- I removed the untracked `.yardstick/` the quick start created. `git status` in the clone is clean and no tracked file was changed.
- Probe files are under `<sandbox>/lens-ux/runs/` (gitignored).
