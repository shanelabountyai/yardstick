# Yardstick — Phase 5 plan

Scope: the third target type the PRD names (§3 "`http` (POST each input)", §4 "generic `command` and `http`"),
which Phases 1-4 deferred. Branch `phase-5`, one draft PR against `main`, never merged by Claude.

**Gate:** the standing gates — ruff (lint + format), mypy `--strict`, pytest (unit, property, YS-01..YS-05),
examples regenerate byte-identically, the action's self-test — all green locally and in GitHub CI. PRD §8 has no
row for this phase, so there is no extra phase gate.

**Rules for this run:** no request to any real external service (every test talks to a server started inside the
test on `127.0.0.1`); no LLM calls, no keys; standard library only for HTTP, so `uv.lock` does not change; no
change to the run format, scorers, gate semantics, or the `command` and `results-file` targets.

## What is in

1. **`src/yardstick/adapters/http.py`** — `HttpAdapter`, an `Adapter` like the other two (`info`, `produce`):
   for each suite item, in suite order, one request to a configured URL; the JSON response becomes the same
   `Output` record the `command` target produces.
2. **Target config file** (YAML, `HttpTargetConfig`, unknown keys rejected):

   ```yaml
   url: http://127.0.0.1:8808/answer   # http or https; no user:password@ part
   method: POST                        # POST (default) or PUT
   body: {id: $id, input: $input}      # default; a JSON template (below)
   headers:                            # header name -> environment variable NAME (never a literal value)
     Authorization: {env: MY_API_TOKEN, scheme: Bearer}
     X-Api-Version: {env: MY_API_VERSION, secret: false}
   response:                           # dotted paths into the JSON response; defaults = the command protocol
     text: output
     refused: refused                  # a boolean path, or {path: status, values: [refused]}
     latency_ms: latency_ms
     cost_usd: cost_usd
     error: error
     fields: {citations: citations}
   timeout_s: 30                       # per request
   max_response_bytes: 1048576
   on_error: fail                      # fail (default) | record
   ```

   - **Body template:** any JSON value. A string that is exactly `$id`, `$input` or `$input.<dotted path>` is
     replaced by that value with its JSON type kept; `$$…` is a literal `$…`. No substitution inside longer
     strings. Every body is rendered before the first request, so a template that does not fit an item's input
     fails the run before anything is sent.
   - **Response mapping:** reuses `get_path` and `RefusedRule` from the `results-file` adapter. `text` must be
     present in every 2xx response unless the mapped `error` is non-null. The optional values (refused, latency,
     cost, fields) stay "not reported" when absent or null (YS-04).
   - **Headers and secrets:** a header's value is read from the named environment variable when the run starts.
     The value is never put in the run file, a report, a log line or an error message; the recorded target detail
     is `METHOD scheme://host[:port]/path` with the query string dropped. Defence in depth: redirects are not
     followed (a 3xx is an error), proxies from the environment are not used, a URL with credentials is
     rejected, and any occurrence of a secret header value in a recorded text, field or error is replaced by
     `[redacted:$NAME]`.
3. **CLI:** `yardstick run --http CONFIG.yaml [--http-url URL]` as the third way to name a target (exactly one of
   `--cmd`, `--results`, `--http`). `--timeout` overrides the config's `timeout_s` for http; for `--cmd` it
   keeps its 300 s default.
4. **Failure behaviour** (decision recorded in DECISIONS): by default any failed request fails the whole run
   (exit 2, no run file), as a crashed or timed-out `command` target does (D-14). Only an explicit error value in
   a 2xx response is a per-item error, like `command`'s `error` field. `on_error: record` is the opt-in that
   records each failed request as an errored item instead.
5. **Determinism:** latency is recorded only when the endpoint reports it; Yardstick does not measure it,
   because a measured value would change the run file between identical runs (YS-01).
6. **Fixture server** `fixtures/targets/fake_http_target.py` (standard library, binds 127.0.0.1 only): the http
   twin of `fake_target.py`, same canned answers, same `--degrade` / `--no-telemetry`, plus
   `--require-token-env NAME`. Config `fixtures/targets/fake-http.yaml`.
7. **Composite action:** additive inputs `http` and `http-url`; the `action` CI job gates the fixture server
   against the baseline pinned from the `command` target.
8. **Docs:** README status line, Targets line, an `http` section; `adapters/__init__.py` docstring; DECISIONS.

## What is not in

- Retries: no existing target retries and the runner has no place for it. Left out.
- Concurrency: the runner is sequential; requests go one at a time.
- Measured latency (see 5), streaming responses, non-JSON responses, GET, form bodies, OAuth flows, mTLS,
  cookies, literal header values.
- A run-level model or cost read from responses; `--model` records the model as for `command`.
- An http example in `examples/make-example.sh` (it would need a server running during the script).
- Any run against a real endpoint. Only the local fixture server and test servers on 127.0.0.1 were used.

## Acceptance items and the tests that prove them

| # | Acceptance item | Test (`tests/test_http_adapter.py` unless noted) |
|---|---|---|
| A1 | An http run of the fixture server gives the same items (outputs, scores, pass/fail) as the `command` run of `fake_target.py`, healthy, degraded and without telemetry | `test_http_run_matches_command_run` |
| A2 | Request shape: method, JSON body from the template, `Content-Type`, one request per item in suite order | `test_request_shape_and_order`, `test_body_template*` |
| A3 | Response mapping: text, non-string text canonicalised, refused (boolean and rule), latency, cost, error, fields; absent optional values stay unreported | `test_response_mapping*`, `test_missing_optional_values_are_not_reported` |
| A4 | Secrets: header values come from env vars; a missing variable fails before any request; the value appears in no run file, report, CLI output or error, including when the server echoes it or a redirect is offered | `test_secret_*`, `test_redirect_is_not_followed`, `test_cli_http_secret_never_written` |
| A5 | Failures, default `fail`: connection refused, timeout, non-2xx, invalid JSON, missing mapped field, oversized response, slow-drip response each raise `AdapterError` naming the item | `test_failure_fails_the_run` (parametrised), `test_connection_refused`, `test_slow_drip_response_times_out` |
| A6 | Failures, `on_error: record`: the same cases become errored items and the run completes | `test_failure_is_recorded_when_configured` |
| A7 | Determinism: two runs against the same server are byte-identical run JSON | `tests/invariants/test_ys01_determinism.py::test_http_runs_are_byte_identical` |
| A8 | CLI: `--http` works end to end, exits 2 on a dead endpoint and writes no run file; target options are validated | `test_cli_http_*` |
| A9 | Config validation: bad URL, credentials in URL, unknown keys, bad header names, reserved headers, bad template | `test_config_validation` |
| A10 | Existing behaviour unchanged: every Phase 1-4 test passes unmodified; `examples/` regenerate byte-identically; `uv.lock` unchanged | whole suite; `make-example.sh` + `git diff --exit-code examples/`; `git diff main -- uv.lock` |
| A11 | Action exposes `http` additively and works end to end | `tests/test_action.py` (unchanged tests still pass, new input checked); CI job `action` |
| A12 | No test reaches a non-loopback address | `test_tests_only_use_loopback` (connect patched to refuse anything but 127.0.0.1) |

## Risks

- **Only the fixture server has been exercised.** Real endpoints differ (auth schemes, envelopes, rate limits).
- **A total time limit is enforced between reads**, so a request can run up to one extra `timeout_s` past it.
- **`on_error: record` turns a dead endpoint into a run of errored items** (gate exit 1, not 2). It is opt-in.
