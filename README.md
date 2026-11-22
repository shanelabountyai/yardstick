# Yardstick

An eval harness that sits on top of AI projects' own evals: one run format, baselines, side-by-side compare, and CI gates that fail on regressions.

Build-log #26. Status: **Phases 1-5 are on `main`** (core; results-file adapter, Footnote mapping, HTML report; `llm-judge` with a budget cap, human grades, kappa, YS-05; GitHub composite action and the Footnote case study; the `http` target). Spec in `docs/PRD.md`, plans in `docs/PHASE1_PLAN.md` … `docs/PHASE5_PLAN.md`, defaults in `docs/DECISIONS.md`.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12, which Yardstick pins) and any `python3` on
`PATH` for the fake target. Everything below runs offline, with no API key.

```bash
git clone https://github.com/shanelabountyai/yardstick.git && cd yardstick
uv sync
# run a suite against a command target (any program that reads JSONL items and prints JSONL outputs)
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py" \
  --target-name fake -o runs/healthy.json
uv run yardstick baseline pin runs/healthy.json            # -> .yardstick/baselines/support-bot__fake.json
uv run yardstick run -s fixtures/suites/support-bot.yaml --cmd "python3 fixtures/targets/fake_target.py --degrade" \
  --target-name fake -o runs/degraded.json
uv run yardstick gate runs/degraded.json -c fixtures/gates/support-bot.yaml --report runs/report.md   # exit 1
uv run yardstick compare runs/healthy.json runs/degraded.json
```

The gate step prints the verdict, value first and the requirement in brackets, and exits 1:

```text
FAIL    pass_rate                    58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)
FAIL    pass_rate[refusal]           50.0% (floor 100.0%)
PASS    latency_p95_ms               ok
gate FAILED
```

Exit codes, for every command: **0** ok (gate passed), **1** gate failed (a regression or a missed threshold),
**2** bad input or a target that could not run. The quick start writes `runs/` and `.yardstick/`, both ignored in
this repo (a project using Yardstick commits its `.yardstick/baselines/`, D-04).

Example output: [`examples/report-example.md`](examples/report-example.md) (regenerate with `examples/make-example.sh`).
A ten-minute demo script: [`docs/DEMO.md`](docs/DEMO.md).

## Footnote: reading a real project's eval results

Footnote's committed `eval/results/answers-*.json` files (copied into `fixtures/footnote/` with attribution) run through
the `results-file` adapter with the built-in `footnote` mapping:

```bash
uv run yardstick footnote suite fixtures/footnote/golden.json -o fixtures/footnote/suite.yaml
uv run yardstick run -s fixtures/footnote/suite.yaml --mapping footnote --target-name dense-sonnet \
  --results fixtures/footnote/results/answers-dense-claude-sonnet-5-5-theta-off-cd1252c6a407-2026-10-28T0102.json \
  -o runs/dense-sonnet.json
# exit 1: this cell misses Footnote's own targets (D-32), and no baseline is pinned for it, so the drop check
# fails closed (D-11)
uv run yardstick gate runs/dense-sonnet.json -c fixtures/gates/footnote.yaml --html-report runs/report.html
# replay Footnote's theta gate at another threshold, as its scorecard's θ′ axis does
uv run yardstick run -s fixtures/footnote/suite.yaml --mapping footnote --target-name dense-sonnet \
  --results fixtures/footnote/results/answers-dense-claude-sonnet-5-5-theta-off-cd1252c6a407-2026-10-28T0102.json \
  --theta-prime 0.52 -o runs/dense-sonnet-theta.json
# check every number in Footnote's own scorecard that the answers files can support
uv run yardstick footnote reproduce --results-dir fixtures/footnote/results --golden fixtures/footnote/golden.json \
  --scorecard fixtures/footnote/results/scorecard-cd1252c6a407-2026-10-28.md
```

Result: [`examples/footnote/reproduction.md`](examples/footnote/reproduction.md): 74 scorecard numbers match, 0 differ,
49 are listed as not reproducible with the reason (they come from database rows or other result files). The gate
report against Footnote's own targets: [`report.md`](examples/footnote/report.md) and
[`report.html`](examples/footnote/report.html) (one static file, inline SVG, no scripts).

## Judges and calibration (Phase 3)

An `llm-judge` scorer labels each unit of an output (a sentence, or the whole text) against a rubric. Its scores are
report-only per item; a gate rule on its rate (`rate:<key>`) **gates only when the judge's Cohen's kappa against human
grades clears the floor** (YS-05; default 0.6). Below the floor, or with no calibration, the rule is shown as
"report-only" and never changes the verdict. Every run that uses a judge needs a spend cap.

```bash
# replay Footnote's committed Opus verdicts through the llm-judge scorer: zero calls, $0 under a $0 cap
uv run yardstick run -s fixtures/footnote/judge-suite.yaml --mapping footnote --target-name hybrid-sonnet \
  --results fixtures/footnote/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json \
  --judge replay:fixtures/footnote/judge/verdicts-opus-1646.json --judge-budget-usd 0 -o runs/judged.json
# kappa per grade set and pooled -> a calibration file a gate can use. The gate file below already names the
# committed copy (fixtures/footnote/judge/calibration-opus-1646.json: same judge and figures, only its source line
# differs), so the next command does not pass --calibration; passing both would be two calibrations (D-84)
uv run yardstick kappa --grades fixtures/footnote/grades/sheet-1.yaml --grades fixtures/footnote/grades/sheet-2.yaml \
  --run runs/judged.json --key judge -o runs/calibration.json
# exit 1: the A+M and U rules miss Footnote's targets; the judge rule is report-only (κ 0.17 < 0.6)
uv run yardstick gate runs/judged.json -c fixtures/gates/footnote-judged.yaml
# the Phase 3 gate: Footnote's eval:kappa figures, reproduced
uv run yardstick footnote kappa --golden fixtures/footnote/golden.json \
  --answers fixtures/footnote/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json \
  --sheet fixtures/footnote/grades/grades.md --sheet fixtures/footnote/grades/grades-2.md \
  --reference fixtures/footnote/kappa-reference.yaml
```

Result: [`examples/footnote/kappa.md`](examples/footnote/kappa.md): sheet 1 κ 0.44 (n 20), sheet 2 κ 0.00 (n 20),
pooled κ 0.17 (n 40, raw agreement 83%), all 19 recorded Opus figures match, 0 differ; the 5 Sonnet re-judge figures are
not reproducible because Footnote never committed those verdicts. The gate report with the judge rule demoted:
[`judged-report.md`](examples/footnote/judged-report.md).

**Live judge (not run in this repo):** `--judge anthropic:MODEL --judge-price-in USD_PER_MTOK --judge-price-out
USD_PER_MTOK --judge-budget-usd CAP` with `ANTHROPIC_API_KEY` set. Before each call the worst-case cost must fit
under the cap; after it the actual cost from token usage is charged. Tests exercise this client only against a fake
transport.

Any other project's result JSON works with a mapping file (dotted paths):

```yaml
rows: rows
id: id
text: answer
refused: {path: status, values: [refused]}
fields: {status: status, refusal_code: refusal}
model: model
run_cost_usd: spentUsd
```

## Case study: gating Footnote in CI (Phase 4)

[Footnote](https://github.com/shanelabountyai/footnote) is a cited-answer assistant over IRS publications with its own
eval system: a 41-question golden set, six committed answer cells, a sentence judge and two sheets of human grades.
Yardstick does not replace any of that. It reads Footnote's committed files and fails the PR when a number drops.

**The gate** ([footnote#5](https://github.com/shanelabountyai/footnote/pull/5), branch `yardstick-gate`, unmerged)
runs one job with no database, no model call and no secret:

1. **Product default** (dense + Sonnet, θ 0.52, Footnote D-46), replayed from the committed θ-off cell: answered or
   partial on A+M, refusal on U and overall pass rate may not drop below the pinned baseline (D-42).
2. **The judged cell** (hybrid + Sonnet θ on, run `2026-10-23T1646`), with Footnote's committed Opus verdicts replayed
   through the `llm-judge` scorer under a $0 cap: the same regression rules, plus sentence support ≥ 90%. That rule
   is **report-only**: the judge's pooled κ against Shane's grades is 0.17 (n 40), below Footnote's 0.7 floor (YS-05).

Suites, replayed verdicts and the κ calibration are rebuilt in CI from Footnote's `eval/golden.json`, answers file and
grade sheets (D-46). Both gates passed on the PR's first run, and each posted one PR comment that is updated in
place on later pushes. The gate table from the judged comment:

| Rule | Current | Baseline | Items | Result |
|---|---|---|---|---|
| `rate:refusal[A+M]` | 63.6% | 63.6% | 22 / min 8 | pass |
| `pass_rate[U]` | 87.5% | 87.5% | 8 / min 8 | pass |
| `rate:judge[A+M+V]` | 96.1% | 96.1% | 16 / min 8 | report-only: pass (judge kappa 0.17 (n 40) < floor 0.7) |

And from the product-default comment: `rate:refusal[A+M]` 77.3% (17/22), `pass_rate[U]` 87.5% (7/8), `pass_rate`
78.0% (32/41), all ±0.0 pt against the baseline. These are below Footnote's own ≥ 90% targets, which is why the gate
guards against regressions and leaves the targets to Footnote's scorecard.

**What Yardstick checked before it was trusted to gate:**

- Phase 2: 74 numbers in Footnote's own scorecard are recomputed from the answers files: 74 match, 0 differ, and 49
  are listed as not reproducible with the reason ([`reproduction.md`](examples/footnote/reproduction.md)).
- Phase 3: Footnote's `eval:kappa` figures, recomputed from its committed verdicts and grade sheets: **19 match, 0
  differ, 5 not reproducible**. The 5 are the Sonnet re-judge figures, whose verdicts exist only in Footnote's
  database ([issue #4](https://github.com/shanelabountyai/yardstick/issues/4), [`kappa.md`](examples/footnote/kappa.md)).

**Not done here (owner step):** a live judge. That needs `ANTHROPIC_API_KEY` as a repo secret and a gate step with
`--judge anthropic:MODEL`, prices and a budget. Until then, the judge's numbers can be reported but cannot gate.

## HTTP target (Phase 5)

`--http CONFIG.yaml` sends one request per suite item, in suite order, and reads the answer from the JSON response.
The output record is the one the `command` target produces, so scorers, baselines, compare, gates and reports
work the same. To try it against the fixture endpoint in this repo:

```bash
# terminal 1: a local endpoint with canned answers (standard library, listens on 127.0.0.1 only)
python3 fixtures/targets/fake_http_target.py --port 8808
# terminal 2
uv run yardstick run -s fixtures/suites/support-bot.yaml --http fixtures/targets/fake-http.yaml \
  --target-name fake-http -o runs/http.json
uv run yardstick baseline pin runs/http.json
uv run yardstick gate runs/http.json -c fixtures/gates/support-bot.yaml
```

A target config, with every key (only `url` is required; `--http-url URL` overrides it):

```yaml
url: https://my-service.example/v1/answer   # http or https; no user:password@ part
method: POST                                # or PUT
body:                                       # JSON template; default {id: $id, input: $input}
  question: $input.question                 # a whole string $id / $input / $input.<path> becomes that value
  request_id: $id
headers:                                    # header name -> environment variable NAME, never a value
  Authorization: {env: MY_SERVICE_TOKEN, scheme: Bearer}    # sends "Bearer <value of $MY_SERVICE_TOKEN>"
  X-Api-Version: {env: MY_SERVICE_API_VERSION, secret: false}
response:                                   # dotted paths into the response; defaults are the command row's keys
  text: data.answer
  refused: {path: data.status, values: [refused]}           # or a path to a boolean
  latency_ms: usage.ms
  cost_usd: usage.usd
  error: error
  fields: {citations: data.citations}       # structured values for field-equals / label-rate scorers
timeout_s: 30                               # per request; `--timeout` overrides it
max_response_bytes: 1048576
on_error: fail                              # or record
```

- **Failures.** By default a failed request (connection refused, timeout, a non-2xx status, a body that is not
  JSON, no value at the `text` path, a response over the size limit) stops the run with exit 2 and writes no run
  file, like a crashed `command` target. `on_error: record` records the item as errored and carries on instead. An
  error value the endpoint itself returns marks only that item. No retries; one request at a time.
- **Secrets.** Header values are read from the named environment variables when the run starts and are not written
  to the run file, reports or error messages. The recorded target is the method and the URL without its query
  string. Redirects are not followed and proxy environment variables are not used. If the endpoint echoes a
  secret header value back, it is replaced by `[redacted:$NAME]` before anything is recorded.
- **Telemetry.** Latency and cost are recorded only when the endpoint reports them. Yardstick does not time the
  requests itself, so the same responses give a byte-identical run (YS-01); otherwise they show "not reported".

**Only run against the local fixture.** This target has been exercised against `fake_http_target.py` and test
servers on 127.0.0.1, in pytest and in CI. It has not been pointed at a real service, so authentication schemes,
response envelopes and rate limits of real endpoints are untested. Decisions: `docs/DECISIONS.md` D-59 to D-68.

## GitHub Action

```yaml
permissions:
  contents: read
  pull-requests: write          # only for the PR comment
steps:
  - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  - uses: shanelabountyai/yardstick@<tag or SHA>
    with:
      suite: evals/suite.yaml
      gate-config: .yardstick/gates/main.yaml       # thresholds
      results: evals/results/latest.json            # or: command: python3 my_target.py   or: http: my-http.yaml
      mapping: my-mapping.yaml                      # or: footnote
      baseline: .yardstick/baselines/main.json
      report-path: yardstick-report.md
```

The action installs a pinned `uv` from PyPI and syncs Yardstick from its own ref against `uv.lock`, so it uses no
third-party actions (D-43). It runs `yardstick run` and `yardstick gate`, appends the markdown report to the job
summary, and posts or updates one PR comment per `comment-tag` with `GITHUB_TOKEN` (D-44). It fails the step when
the gate fails, unless `fail-on-gate: "false"`, and always fails on bad input (exit 2). Outputs: `passed`,
`exit-code`, `report`, `run`. Other inputs: `run-args`, `run-path`, `calibration`, `html-report-path`,
`target-name`, `comment`, `comment-tag`, `github-token`, `fail-on-gate`, `install-only` (only put `yardstick` on
`PATH`), `http` and `http-url` (an HTTP target; put the variables its config names for headers in the job's
`env:`). The `action` job in `.github/workflows/ci.yml` tests it on every
push: a healthy run must pass, a degraded run must fail, a missing target must exit 2, the fixture HTTP target must
pass against the command target's baseline, and an HTTP target that is not listening must exit 2.

## Pieces

- **Scorers** (deterministic): `exact`, `regex`, `json-schema`, `numeric-tolerance`, `contains-all`, `refusal-expected`, `citation-grounded`, `field-equals`, `label-rate`. Any scorer can be `report_only` (measured, never decides pass). **`llm-judge`** (always report-only per item) labels units through a judge behind an interface: replay, or the Anthropic Messages API, under a run-level budget cap.
- **Calibration**: human grade sets, Cohen's kappa per judge (model + prompt hash), per set and pooled; gates honour YS-05.
- **Metrics**: pass rate, mean score, per-slice, `rate:<scorer key>` (pooled hits/total, e.g. supported sentences), p50/p95 latency (integer ms), total and per-item cost (USD, 6 dp; a run-level total when the target only reports that). Unreported telemetry is "not reported", never 0.
- **Gates**: `floor`, `max`, `max_drop` / `max_rise` vs baseline, `min_items`, on any metric including `rate:<key>`, run-wide or per `slice`. Fail closed. A judge rate (an `llm-judge` key, or a `label-rate` key marked `judge: true`) gates only when its kappa clears `judge.kappa_floor` with at least `judge.min_graded` graded units (default 30), from the calibration files in `judge.calibrations`.
- **Targets**: `command` (JSONL over stdin/stdout), `results-file` (declarative mapping, or the built-in `footnote` mapping) and `http` (one JSON request per item to a configured URL; run only against the local fixture server so far).
- **Reports**: markdown (PR comments, CI logs) and static HTML (`report --format html`, `gate --html-report`).

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
