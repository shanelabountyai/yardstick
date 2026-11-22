# Yardstick: ten-minute demo

A script for showing Yardstick to a hiring manager: one command per step, what to say, and what the audience
should see. Everything runs offline against the fixtures in this repo. No API key, no model call, no hosted service.

**How this was checked.** Every command below was run by Claude on 2026-11-20 in a cloud sandbox (Linux, uv
0.11.32, Python 3.12.3), in a fresh clone of `main` at `94949eb`, in the order written. "Verified in this run"
means the command ran there and printed what the step says. It does not mean it was run on Shane's Mac: that is
an owner step (see `NEXT.md`). Steps that need a desktop browser are marked "not verified" with the reason.

This is a sample build. The support-bot suite and its target are synthetic. The Footnote files are committed
results from Shane's own sample project, copied with attribution (`fixtures/footnote/ATTRIBUTION.md`).

## Setup (before the audience arrives, about two minutes)

1. Start from a clean checkout so the output matches this script:

   ```bash
   git clone https://github.com/shanelabountyai/yardstick && cd yardstick
   uv sync
   rm -rf runs .yardstick
   ```

   `uv sync` installs the pinned versions from `uv.lock`. It needs network access once. In the sandbox it exited 0.
2. Open a second terminal in the same folder and start the local test endpoint for step 10. It listens on
   127.0.0.1 only and prints `listening on http://127.0.0.1:8808/answer`:

   ```bash
   python3 fixtures/targets/fake_http_target.py --port 8808
   ```

3. Make the terminal font large, and have `examples/footnote/report.html` ready to open in a browser tab.
4. Check the tool answers: `uv run yardstick --help` should list `run`, `compare`, `gate`, `report`, `baseline`,
   `kappa` and `footnote`.

## The script

Times are a guide. They add up to about ten minutes.

### 1. A healthy run (0:00 to 1:00). Verified in this run

```bash
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py" --target-name fake -o runs/healthy.json
```

**Say:** "Yardstick sits on top of an AI project's own evals. A suite is a set of questions with expected
behaviour. A target is anything that answers them. Here the target is a small script standing in for a support
bot. Twelve questions go in, and every answer is scored by plain deterministic checks: does it contain the facts,
does it refuse when it should, is the quote really in the cited source."

**See:** `sha256:12e96079a9074ae8  support-bot  12/12 passed  -> runs/healthy.json`. Exit code 0.

### 2. Pin the baseline (1:00 to 1:30). Verified in this run

```bash
uv run yardstick baseline pin runs/healthy.json
```

**Say:** "This is the known-good result. It is a file in the project's own repo, so changing the baseline is
reviewed in a pull request like any other change."

**See:** `pinned sha256:12e96079a9074ae8 -> .yardstick/baselines/support-bot__fake.json`. Exit code 0.

### 3. A degraded run (1:30 to 2:15). Verified in this run

```bash
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py --degrade" --target-name fake -o runs/degraded.json
```

**Say:** "Now someone changes the prompt or swaps the model. The `--degrade` flag makes the stand-in bot worse in
ways real systems get worse: it drops a fact, misquotes a source, and answers two questions it should refuse."

**See:** `sha256:2dfe089c3b40fc75  support-bot  7/12 passed  -> runs/degraded.json`. Exit code 0: the run itself
worked. Whether it is good enough is the gate's job.

### 4. The gate fails (2:15 to 3:15). Verified in this run

```bash
uv run yardstick gate runs/degraded.json -c fixtures/gates/support-bot.yaml --report runs/report.md; echo "exit $?"
```

**Say:** "The gate is three rules in a YAML file: overall pass rate at least 85% and no more than two points
below the baseline, every refusal question refused, and p95 latency under two seconds. Exit code 1 is what
fails a CI job. Exit code 2 is reserved for broken input or a broken target, so a team can tell a regression
from an outage."

**See:**

```text
wrote runs/report.md
FAIL    pass_rate                    58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)
FAIL    pass_rate[refusal]           50.0% (floor 100.0%)
PASS    latency_p95_ms               ok
gate FAILED
exit 1
```

### 5. Compare the two runs (3:15 to 4:00). Verified in this run

```bash
uv run yardstick compare runs/healthy.json runs/degraded.json | head -10
```

**Say:** "Compare puts any two runs side by side: two prompts, two models, this week and last week. Cost did
not move, quality did. The full output continues by slice and by scorer."

**See:** a table whose first rows are `pass_rate 100.0% 58.3% −41.7 pt`, `mean_score 100.0% 75.0% −25.0 pt` and
`latency_p95_ms 714 ms 1428 ms +714 ms`. The full report with the five newly failing items is in
`runs/report.md` (the same content as `examples/report-example.md`, apart from the run ids and timestamp).

### 6. The Footnote reproduction (4:00 to 5:15). Verified in this run

```bash
uv run yardstick footnote reproduce --results-dir fixtures/footnote/results --golden fixtures/footnote/golden.json --scorecard fixtures/footnote/results/scorecard-cd1252c6a407-2026-10-28.md | head -5
```

**Say:** "Before this tool was allowed to gate a real project, it had to reproduce that project's own numbers.
Footnote is a cited-answer assistant with its own scorecard. Yardstick reads Footnote's committed result files
and recomputes every scorecard number those files can support. 74 match. None differ. 49 cannot be recomputed
from those files, and each one is listed with the reason. The command exits 1 if any number differs."

**See:** `**74 match, 0 differ, 49 not reproducible** (each with the reason).` on the fifth line. The full table
is `examples/footnote/reproduction.md`.

### 7. The HTML report (5:15 to 6:15). Report generation verified in this run; opening it in a desktop browser not verified

```bash
uv run yardstick report runs/degraded.json --baseline runs/healthy.json --gate fixtures/gates/support-bot.yaml --format html -o runs/report.html
```

Then open `runs/report.html` (on a Mac: `open runs/report.html`), and the Footnote one in the second tab
(`open examples/footnote/report.html`).

**Say:** "The same report as one static HTML file: HTML and CSS bar charts, no scripts, no external requests, so it can
be attached to a build or emailed. The bar is this run, the vertical line is the baseline."

**See:** a page titled "Yardstick report: support-bot" with a red "Gate failed" badge, a summary table, two bar
charts and the gate table.

**Why part is not verified:** the sandbox has no desktop. The command exited 0 and wrote the file. Both HTML
files were loaded in headless Chromium, which found the title, two SVG charts, zero `<script>` elements and no
console errors. The macOS `open` command and how the page looks in Shane's browser were not checked.

### 8. A judge, replayed at zero cost (6:15 to 7:15). Verified in this run

```bash
uv run yardstick run -s fixtures/footnote/judge-suite.yaml --mapping footnote --target-name hybrid-sonnet --results fixtures/footnote/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json --judge replay:fixtures/footnote/judge/verdicts-opus-1646.json --judge-budget-usd 0 -o runs/judged.json
```

**Say:** "Some things need an LLM judge, for example whether each sentence is supported by its source. Every
judged run must carry a spend cap. Here the judge is a replay of the verdicts Footnote already committed, so it
makes zero calls under a zero-dollar cap. A live judge has never been run from this repo."

**See:** `footnote-golden-judged  28/41 passed` and a judge line ending
`55 calls, 55 units judged, 0 invalid, 0 not judged (budget), spent $0.000000 of $0.000000`. Exit code 0.

### 9. The kappa rule (7:15 to 8:15). Verified in this run

```bash
uv run yardstick gate runs/judged.json -c fixtures/gates/footnote-judged.yaml; echo "exit $?"
```

**Say:** "This is the rule I would point a hiring manager at. The judge says 96% of sentences are supported,
which would pass a 90% floor. But a judge only gets a vote if it agrees with human graders. Against 40 sentences
graded by hand, this judge's Cohen's kappa is 0.17, and the floor is 0.6. So its rule is shown as report-only
and cannot change the verdict. The gate still fails, on the two deterministic rules."

**See:**

```text
FAIL    rate:refusal[A+M]            63.6% (floor 90.0%)
FAIL    pass_rate[U]                 87.5% (floor 90.0%)
(pass)  rate:judge[A+M+V]            ok; report-only (YS-05): judge kappa 0.17 (n 40) < floor 0.6
gate FAILED
exit 1
```

The agreement figures themselves are in `examples/footnote/kappa.md` (sheet 1 κ 0.44, sheet 2 κ 0.00, pooled κ
0.17, raw agreement 83%).

### 10. The HTTP target (8:15 to 9:15). Verified in this run, against the local fixture server only

```bash
uv run yardstick run -s fixtures/suites/support-bot.yaml --http fixtures/targets/fake-http.yaml --target-name fake -o runs/http.json && uv run yardstick gate runs/http.json -c fixtures/gates/support-bot.yaml
```

**Say:** "Same suite, but the target is now an HTTP endpoint: the test server in the other terminal. One request
per question. The run is gated against the baseline pinned in step 2, so the HTTP path has to produce the same
quality as the command path. Header values such as tokens are read from environment variables by name and are
kept out of the run file. This target has only ever been pointed at this local server, never at a real service."

**See:** `support-bot  12/12 passed  -> runs/http.json`, then three `PASS` lines and `gate PASSED`. Exit code 0.

**Optional, if there is time:** stop the server in the second terminal (Ctrl-C) and run the first half again.
It prints `error: http target: item 'faq-reset-password': connection failed (ConnectionRefusedError)`, exits 2
and writes no run file. Verified in this run.

### 11. The GitHub action (9:15 to 10:00). CI result verified through the GitHub API; the browser view not verified

Open the latest CI run on `main` in a browser:
<https://github.com/shanelabountyai/yardstick/actions/runs/44636574148>

**Say:** "The same two commands are packaged as a composite GitHub action. It runs the suite, gates it, writes
the report to the job summary and posts or updates one comment on the pull request. The `action` job here tests
the action on every push: a healthy run must pass, a degraded run must fail, a missing target must exit 2, and
the HTTP target must pass against the command target's baseline."

**See:** two jobs, `check` and `action`, both green. In the `action` job: "gate a healthy run (must pass)",
"gate a degraded run (must fail; fail-on-gate false keeps the job going)" and the two http steps.

**Why part is not verified:** the GitHub API reported run 32 on commit `94949eb` as `success` for both jobs and
every step (read 2026-11-20). The page itself was not opened in a browser, and the job summary and PR comment
were not looked at in this run. The Footnote pull request that uses the action (footnote#5, described in the
README) is in a repo this run could not read.

## If a step fails live

- **`uv sync` fails or is slow:** it needs the network once. Run setup before the meeting. If it still fails,
  show the committed outputs instead: `examples/report-example.md`, `examples/footnote/reproduction.md`,
  `examples/footnote/kappa.md` and `examples/footnote/report.html`.
- **Step 1 or 3 prints different run ids:** the ids are content hashes that include the git SHA of the checkout,
  so a different commit gives different ids. The pass counts (12/12 and 7/12) are what matter.
- **Step 4 says `max_drop: no baseline`:** step 2 was skipped, or `--target-name` differs from step 1. Re-run
  step 2. This is the tool failing closed, which is worth saying out loud.
- **Step 4 or 9 "fails":** it is meant to. Exit code 1 is the demo. Exit code 2 means something is wrong with
  the input: read the `error:` line.
- **Step 10 exits 2 with `connection failed`:** the server in the second terminal is not running, or port 8808
  is taken. Restart it. With another port, add `--http-url http://127.0.0.1:PORT/answer` (not verified in this
  run with a port other than 8808).
- **The browser will not open the HTML file:** drag `examples/footnote/report.html` into a browser window, or
  show `examples/footnote/report.md` in the terminal.
- **No network at all for step 11:** show `.github/workflows/ci.yml` (the `action` job) and `action.yml` in the
  editor instead.
- **After the demo:** `rm -rf runs .yardstick`. `runs/` is git-ignored. `.yardstick/` is not, so it shows up in
  `git status` until removed.

## What this demo does not show

- A live LLM judge. It exists behind `--judge anthropic:MODEL` and has only been tested against a fake
  transport (README, "Live judge (not run in this repo)").
- The HTTP target against a real service.
- The action running in another repository.
