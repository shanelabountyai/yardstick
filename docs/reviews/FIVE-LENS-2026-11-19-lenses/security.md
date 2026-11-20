# Five-lens review 2026-11-19: security lens, as returned

Unedited output of the security lens agent (repo `main` at `94949eb`, reviewed 2026-11-20), apart from sandbox paths shortened to `<sandbox>` and the agent's closing housekeeping line about session memory removed. Ranking and calls are in [`../FIVE-LENS-2026-11-19.md`](../FIVE-LENS-2026-11-19.md). Nothing here was fixed.

### Target output is written unescaped into the markdown report, and so into the PR comment and job summary
- Severity: Major
- Where: `src/yardstick/report/format.py:48-50` (`md_cell` escapes only `|` and `\n`), `src/yardstick/report/markdown.py:45` (`autoescape=False`), `:229-237` (score detail goes into the "Failing items" cell), `src/yardstick/report/templates/report.md.j2` lines 1, 8-12 (suite name, target name, model, prompt hash, git SHA, warnings and judge model are not passed through `md_cell` at all), `src/yardstick/github_comment.py:31-38` (the report is posted as is).
- Observed: reproduced with a command target under `runs/poc/`. `yardstick run --suite evil-suite.yaml --cmd "python3 evil_target.py" ... && yardstick gate evil-run.json --config gate.yaml --report evil.md`. A target `error` string, or the first 80 characters of an answer quoted by the `exact` scorer (`expected 'x', got '...'`), reached `evil.md` verbatim: `@octocat`, `<img src=https://attacker.example/p.png>`, `[click](https://attacker.example)`, `<details>`, and the comment marker `<!-- yardstick:gate -->`. A `\r` in the text is not replaced, so it can end the table row and start a line such as `**Gate: PASSED**`. A suite name containing newlines produced a second `# BIG HEADING` and a fake `**Gate: PASSED**` line above the real verdict.
- Why it matters: the comment is posted by `github-actions[bot]` on the user's own PR, and its content is whatever the system under test printed. For an LLM target that means model output, which can be steered by prompt injection in its inputs or retrieved documents; for an `http` target it is a third-party endpoint. The realistic results are notification spam through @mentions of users or teams, phishing links or remote images in a bot-authored comment, and a spoofed verdict line. GitHub sanitises HTML, so this is not script execution. The attacker needs control of the target's output on a failing item (first 25 failing items, 300 characters each). A fork PR author controls the suite as well, but gets a read-only token, so only the job summary is affected there.
- Recommended fix: escape every free-text value in the markdown report: backslash-escape markdown punctuation, replace `<`, `>` and `&` with entities, break `@` with a zero-width character or put it in a code span, replace `\r` and other control characters, and neutralise `<!--`. Apply it to the header fields too. Add a test that renders a run with hostile strings and asserts none of them survive.
- Status: verified

### PR comment lookup trusts any comment containing the marker
- Severity: Minor
- Where: `src/yardstick/github_comment.py:101-116` (`find_comment`), `:118-125` (`upsert`).
- Observed: by reading. `find_comment` returns the first comment on the PR (oldest first) whose body contains `<!-- yardstick:<tag> -->`, with no check on the author or on where the marker sits in the body. The marker text can also arrive inside a report through target output (previous finding, reproduced there).
- Why it matters: on a public repo anyone can comment on a PR. Someone who posts the marker first makes the action PATCH their comment instead of creating its own. Either the report then lives in a comment they own and can edit afterwards to show a different verdict, or the PATCH fails and D-44 downgrades it to a warning, so no report comment appears. It needs no privileges, but the damage is limited to a misleading or missing comment; the gate's exit code is unaffected.
- Recommended fix: only accept comments whose `user.type` is `Bot` and `user.login` is `github-actions[bot]`, and require the body to start with the marker.
- Status: suspected (read directly; not exercised against GitHub)

### Uncaught exceptions on endpoint-controlled or config-controlled input in the http target
- Severity: Minor
- Where: `src/yardstick/adapters/http.py:365` (`declared.isdigit() and int(declared)`), `:275-282` and `:434-443` (deeply nested `fields`), `:72-74` (regexes end in `$`, which also matches before a trailing newline), `:152` (non-ASCII URL accepted); `src/yardstick/cli.py:260` catches only `AdapterError` and `ScorerConfigError`.
- Observed: reproduced against a local server on 127.0.0.1:8821 with a fake token.
  - A response header `Content-Length: ²` (byte 0xB2) raises `ValueError: invalid literal for int()`.
  - A `fields` value nested 900 deep raises `PydanticSerializationError`; nested 5000 deep raises `RecursionError`.
  - A header name `"X-Foo\n"` passes validation and raises `ValueError: Invalid header name` from `http.client`.
  - `--http-url 'http://127.0.0.1:8821/päth'` raises `UnicodeEncodeError`.
  - A scheme `"Bearer\n"` is accepted and sent as a folded header.
  - Each crash prints a rich traceback and exits 1 instead of 2. The fake token did not appear in any traceback (`grep -c` gave 0 on every log): typer 0.29.1 prints no locals.
- Why it matters: D-62 says a bad response is either a clean exit 2 or, with `on_error: record`, an errored item. These paths bypass both, so one malformed response kills a long run. No secret leaked today, but that rests on typer's default of not showing locals; `headers` and `secrets` are live locals in those frames.
- Recommended fix: use `re.fullmatch` or `\Z` in the three patterns; parse Content-Length with `str.isascii() and str.isdigit()`; reject non-ASCII URLs in the validator; wrap `_fetch`/`_output` so `ValueError`, `RecursionError` and pydantic serialisation errors become `_RequestFailed`; set `pretty_exceptions_show_locals=False` explicitly on the Typer app.
- Status: verified

### The redaction leaks the tail of a secret when one secret is a prefix of another; D-61's limits are wider than stated
- Severity: Minor
- Where: `src/yardstick/adapters/http.py:269-272` (`_scrub` replaces in dict insertion order), `:344-345`.
- Observed: reproduced. With two secret headers, `POC_A=test-secret` and `POC_B=test-secret-123-long-tail`, an endpoint echoing both produced the recorded text `A=[redacted:$POC_A] X=[redacted:$POC_A]-123-long-tail`. Reversing the header order hides it. Also confirmed: base64, upper-cased, reversed and truncated echoes are recorded unredacted (D-61 documents the encoded case). A one-character secret is replaced wherever that character occurs, before scoring, so it changes scores.
- Why it matters: it needs two secret headers where one value is a prefix or substring of the other (for example a key id and `id:secret`) and an endpoint that echoes them, so it is rare. When it happens the remainder of the longer secret is written to the run file and may be committed as a baseline.
- Recommended fix: scrub longest value first; refuse or warn on secret values shorter than about 8 characters; also scrub the scheme-prefixed and base64 forms of each value.
- Status: verified

### A response that drips its headers is not bounded by the request deadline (D-63)
- Severity: Minor
- Where: `src/yardstick/adapters/http.py:360-373`. The deadline is checked only inside the body read loop; `opener.open` reads the status line and headers under the per-recv socket timeout alone.
- Observed: reproduced. With `timeout_s: 3`, a local server that sent one header line every 0.5 s for 30 s held the request for 30.4 s, ending only when my server stopped. D-63 says "worst case about twice `timeout_s`". Body drip is bounded as claimed (3.4 s). The size limits held: a huge Content-Length, an endless chunked body and a 50 MB gzip body were all refused in under a second.
- Why it matters: an endpoint that is slow or hostile in the header phase can hold a CI job well beyond the configured timeout, per item (`http.client` allows 100 header lines of up to 64 KiB each). The attacker is the endpoint the user chose, so this costs runner minutes, nothing more.
- Recommended fix: run each request under an overall deadline (a watchdog timer that closes the socket, or `http.client` directly with the socket timeout reset to the remaining time before each read), or correct D-63 to say the bound covers the body only.
- Status: verified

### `command` target records its full command line in the run file, which the README says to commit as a baseline
- Severity: Minor
- Where: `src/yardstick/adapters/command.py:34` (`detail=shlex.join(self.argv)`), `:56-57` (last 5 stderr lines echoed in the error).
- Observed: reproduced. `yardstick run --suite suite1.yaml --cmd "python3 evil_target.py --api-key test-secret-123" --no-git --out out-cmd.json` wrote the fake key into `target.detail`. It is not shown in the md or html report (0 matches in each). `yardstick baseline pin` copies the run file into `.yardstick/baselines/`. Separately, a target that exits non-zero has its last stderr lines printed by yardstick, including a fake key my test script printed.
- Why it matters: the http target was built so credentials cannot reach a run file (D-61); the command target has no equivalent, and baselines are meant to be committed. The user would have to put a secret on the command line themselves, so this is a foot-gun rather than an attack.
- Recommended fix: record only `argv[0]` plus a hash of the rest, or document plainly that `--cmd` is recorded verbatim and secrets belong in the environment. Add a README note that target stderr reaches the CI log.
- Status: verified

### The judge and PR-comment HTTP clients forward their credential across redirects
- Severity: Minor
- Where: `src/yardstick/judge/anthropic.py:37-43` and `src/yardstick/github_comment.py:68-75` (both use plain `urllib.request.urlopen`).
- Observed: reproduced locally with a fake token. A server on 127.0.0.1:8824 answering 302 to another port received, at the second port, the `X-Api-Key` header from `judge.anthropic.urllib_transport` and the `Authorization` header from `python -m yardstick.github_comment` (with `GITHUB_API_URL` pointed at the local server). The comment tool also printed "created comment" although the POST had become a redirected GET. Both clients honour proxy environment variables too, which is normal but differs from the http target.
- Why it matters: D-61 gives exactly this reason for never following redirects in the http target, but the two clients that carry the more valuable credentials (the Anthropic key and the GitHub token) do follow them. Exploiting it needs api.anthropic.com or the GitHub API host (or a GHES `GITHUB_API_URL`) to issue a redirect, so the practical risk is low.
- Recommended fix: reuse the `_NoRedirect` opener in both clients. In `github_comment`, treat any status other than 200/201 as a failure.
- Status: verified

### Secrets in a URL path are recorded; only the query string is stripped
- Severity: Minor
- Where: `src/yardstick/adapters/http.py:201-204` (`safe_url`), `:308-310`.
- Observed: reproduced. `url: http://127.0.0.1:8821/echo;p=qs-secret-456#frag` was recorded in `target.detail` as `POST http://127.0.0.1:8821/echo;p=qs-secret-456`. Query strings were stripped as claimed, in the run file and in every error message, including with `--http-url`.
- Why it matters: webhook-style endpoints carry their credential in the path. D-61 lists the query string of a committed config as not covered, but says nothing about path secrets reaching the run file and baselines.
- Recommended fix: record only scheme, host and port, plus a short hash of the path, or document the limit next to D-61 and in the README "Secrets" bullet.
- Status: verified

### The `check` CI job uses third-party actions by mutable tag; the action's own install is not hash-verified
- Severity: Minor
- Where: `.github/workflows/ci.yml:15-16` (`actions/checkout@v4`, `astral-sh/setup-uv@v6`) versus `:36` (SHA pin); `action.yml:114-122` (`pip install "uv==$UV_VERSION"` with no `--require-hashes`; hatchling is fetched at build time and is not in `uv.lock`).
- Observed: by reading. D-43 records that the `check` job's tags "were left as they were". The job has `contents: read` and no secrets.
- Why it matters: a moved tag or a compromised release would run code in this repo's CI, and for the composite action in every caller's job, which may hold `pull-requests: write` and the caller's header secrets in env. The blast radius in this repo is small because no secrets are configured.
- Recommended fix: pin both actions by full SHA as in the `action` job; install uv from a hash-pinned requirements file (`pip install --require-hashes -r`); state in the README that callers should pin the action by SHA.
- Status: verified (read directly)

### The action prepends its whole venv `bin` to PATH for the rest of the caller's job
- Severity: Minor
- Where: `action.yml:124` (`echo "$GITHUB_ACTION_PATH/.venv/bin" >> "$GITHUB_PATH"`).
- Observed: by reading, plus listing the synced `.venv/bin`, which holds `python`, `python3`, `python3.12`, `typer`, `jsonschema`, `markdown-it` and `pygmentize` beside `yardstick`. After the action runs, including the full run mode and not just `install-only`, every later step's `python3` resolves to the action's interpreter. This repo's CI already depends on that: the `--cmd "python3 fixtures/targets/fake_target.py"` steps run under it.
- Why it matters: the action silently replaces the interpreter and several tool names for all later steps in the caller's job. That is a supply-chain surface the caller did not ask for, and a source of confusing breakage (the venv has no `pip`).
- Recommended fix: export a directory containing only a `yardstick` shim or symlink, and only when `install-only` is true.
- Status: verified (read directly; not run on a GitHub runner)

### `json-schema` scorer fetches remote `$ref` URLs named in a suite
- Severity: Minor
- Where: `src/yardstick/scorers/json_schema.py:30` (`Draft202012Validator(expected)` with the default registry).
- Observed: reproduced. A suite item with `expected: {json-schema: {"$ref": "http://127.0.0.1:8821/schema.json"}}` caused a GET to my local server during `yardstick run`, and the item passed against whatever the server returned.
- Why it matters: a score then depends on a network resource, which breaks YS-01 determinism, and a suite file can make the runner issue requests. The suite is the user's own file, so this is hardening.
- Recommended fix: pass a `referencing.Registry` whose `retrieve` raises, so only in-document refs resolve.
- Status: verified

### `regex` scorer has no time bound
- Severity: Minor
- Where: `src/yardstick/scorers/regex.py:21-27`.
- Observed: reproduced. Suite pattern `^(a+)+$` against a target output of 40 `a` plus `!` was still running when my 20 s `timeout` killed it.
- Why it matters: it needs a backtracking-prone pattern in the user's own suite plus a target output that triggers it, and the result is a hung job until the CI timeout. Low risk for a tool whose suite author is its user.
- Recommended fix: document it, or run the match in a worker with a timeout and record a scorer error.
- Status: verified

## Found clean

- **Secrets in tree and history**: `git log -p --all` over 37 commits and 8 remote branches, plus the working tree. Patterns: `sk-ant-`, `sk-`, GitHub `ghp_/gho_/ghu_/ghs_/ghr_/github_pat_`, AWS `AKIA/ASIA`, Google `AIza`, Slack `xox*-` and webhook URLs, Stripe `sk_/rk_/whsec_`, npm, PyPI, Vercel and SendGrid tokens, JWTs, PEM private keys, database and `http(s)://user:pass@` URLs, generic `key|secret|token|password = <12+ chars>`, and filenames like `.env`, `.pem`, `.key`. The only hits are made-up test values in `tests/test_http_adapter.py` (line 574 and the `SECRET` constant). No file was ever deleted from history. All URLs are PyPI, GitHub, claude.ai session links in commit trailers, 127.0.0.1 or reserved example hosts.
- **D-61, secret never recorded**: a fake token echoed in text, a nested dict value, a dict key, a list, a string `error`, an object `error` and an object `output` was replaced by `[redacted:$POC_TOKEN]` everywhere; 0 occurrences in run files and in stdout/stderr across all runs. Non-2xx bodies are never reported (`HTTP 500` only). `secret: false` leaves that value unredacted, as documented.
- **D-61, header values**: CR/LF, leading or trailing whitespace and an empty value are refused before any request, naming only the variable. Literal header values in a config are refused without echoing them. A YAML syntax error prints "not valid YAML" with no content.
- **D-61, redirects**: 302 and 307 are not followed; the second server received nothing.
- **D-61, proxies**: with `HTTP_PROXY`, `http_proxy` and `ALL_PROXY` pointing at a local listener, the request went direct and the listener saw nothing.
- **D-61, URL rules**: `user:password@`, `file://`, `ftp://`, spaces, a bad port and a malformed IPv6 host are all rejected with a fixed message that does not repeat the URL.
- **D-66, TLS**: an https target with a self-signed certificate failed with `connection failed (SSLCertVerificationError)` and the server received no request; no off switch exists in the code.
- **D-63, size and body time limits**: held (see the header-drip finding for the one gap). urllib does not decompress, so a gzip bomb is just "not JSON".
- **Body template**: `$id` and `$input.<path>` are substituted as JSON values and serialised with `canonical_json`; no string interpolation, so no injection into the body.
- **D-34, judge key**: read only from `$ANTHROPIC_API_KEY`, kept off `repr`, never placed in a `JudgeReply` (a 401 whose body echoed the fake key yielded `HTTP 401`), and not written to run files. Run files hold labels and tallies, not prompts.
- **D-37, budget**: by reading, a call is made only if `spent + estimate <= cap`, HTTP errors are charged at the estimate, and an overrun stops further calls. Prices come from the command line, so the cap is only as true as the prices given.
- **Action inputs**: every `${{ inputs.* }}` is passed through `env:` and used quoted; none is interpolated into shell text. `run-args` is split with `read -r -a` (no globbing, no eval). `github-token` is exposed only to the comment step, not to the step that runs the target.
- **Command target**: no shell. `--cmd 'python3 t.py; touch pwned $(touch pwned)'` created no file; splitting is `shlex.split`.
- **YAML**: `yaml.safe_load` / `safe_dump` at all six call sites; no `yaml.load`, `pickle`, `eval` or `exec` in `src/`.
- **HTML report**: Jinja2 autoescape held for `<script>`, `"><img onerror>` and `javascript:` in suite name, scorer key, item id, slice, target name, model, prompt hash and target output; no `|safe` in the template, no raw tag in the output.
- **Baseline paths**: suite `../../../../trav` and target `..` were pinned as `bl/..-..-..-..-trav__...json` inside the baselines directory.
- **Fork PRs (D-44)**: by reading, a read-only token gives 401/403/404, which becomes a warning; the gate verdict is unchanged. `ci.yml` uses `pull_request`, not `pull_request_target`, with `contents: read` at the top and `pull-requests: write` only on the `action` job.
- **Dependency advisories**: `uvx pip-audit -r <uv export --no-dev> --require-hashes --disable-pip` reported "No known vulnerabilities found" for the 21 locked runtime packages (pydantic 2.14.3, pydantic-core 2.50.4, typer 0.29.1, jinja2 3.1.6, markupsafe 3.0.4, jsonschema 4.26.0, pyyaml 6.0.3, rich 15.0.0 and their dependencies).
- **Fixtures**: `fixtures/footnote/` matches `ATTRIBUTION.md` (copied from the owner's public Footnote repo at a named commit). Scan for emails, phone and SSN shapes and home-directory paths found only a public IRS phone number quoted from a publication. The grader is recorded by first name only. No credentials. The missing LICENSE file does not change redistribution here, since source and copy have the same author; it does leave third parties without licence text for the fixtures.

## Checks automated vs by inspection

- **Automated (run in this sandbox)**: all http-target behaviour above against local servers on 127.0.0.1:8821-8824 (all stopped; `git status` clean; PoC files are under `<sandbox>/lens-sec/runs/poc/`); the secret pattern scan; markdown and HTML report injection; command-target shell test and detail recording; baseline path test; ReDoS; remote `$ref`; redirect forwarding in the judge transport and comment client; judge error surfaces with a fake transport; pip-audit.
- **By inspection only**: `action.yml` and `ci.yml` (not run on a GitHub runner), comment-marker spoofing, token scope and fork behaviour, the budget logic, the PATH change, the unpinned actions.

## Not reviewed

- **Dev dependencies, uv 0.11.32 and hatchling 1.33.0**: not checked for advisories; the single permitted lookup was spent on the runtime set. Not verified.
- **Live behaviour on GitHub**: whether `GITHUB_TOKEN` can PATCH another user's comment, and how GitHub renders the injected markdown, were not exercised (no external requests allowed).
- **Live Anthropic judge**: no key and no calls by rule; only the transport function and a fake transport were exercised. Prompt injection of the judge by target output was not tested; it is inherent to the design and judge scores are report-only unless calibrated (YS-05).
- **SSRF to link-local or metadata addresses**: not treated as a finding. The URL is chosen by the person running the CLI, and a PR author who can change it can already run code in the job.
- **`results-file` and `footnote` adapters, kappa and grades parsing**: read for YAML loading only, not fuzzed.

One disclosure: while testing URL validation I ran one request with `--http-url http://169.254.169.254/latest/meta-data/`. It left the process (the sandbox answered HTTP 403) carrying only the dummy suite item and the fake token `test-secret-123`. It was not needed to reach the conclusion above and I did not repeat it.
