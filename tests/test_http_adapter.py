"""http target: request shape, response mapping, secrets, failures, CLI. Every server here is started inside
the test on 127.0.0.1; an autouse guard refuses any other address."""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.helpers import (
    CLOCK,
    FAKE_HTTP_CONFIG,
    FAKE_HTTP_TARGET,
    GATES,
    SUITES,
    fake_adapter,
    fake_http_adapter,
    fake_http_server,
    serving,
    tiny_suite,
)
from yardstick.adapters.base import AdapterError
from yardstick.adapters.http import (
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_S,
    HttpAdapter,
    load_http_config,
    parse_http_config,
    safe_url,
)
from yardstick.cli import app
from yardstick.models import Item, ScorerSpec, Suite
from yardstick.report.html import render_html
from yardstick.report.markdown import render
from yardstick.runner import run_suite
from yardstick.suite_io import load_run, load_suite, run_to_json

runner = CliRunner()
ITEMS = tiny_suite(2).items
SECRET = "s3cr3t-token-do-not-record"  # a made-up test value, not a credential


class NonLoopback(ConnectionRefusedError):
    pass


@pytest.fixture(autouse=True)
def _loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this module may open a connection to anything but 127.0.0.1."""
    real = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> None:
        if not (isinstance(address, tuple) and address[0] == "127.0.0.1"):
            raise NonLoopback(f"test tried to connect to {address!r}")
        real(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


# -- a scripted test server ---------------------------------------------------------------------------------

Respond = Callable[[BaseHTTPRequestHandler, Any], None]


def reply(h: BaseHTTPRequestHandler, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(raw)))
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(raw)


def ok(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": "ok"})


@contextmanager
def serve(respond: Respond = ok) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yields (url, requests seen). ``respond(handler, parsed request body)`` writes the response."""
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            headers = {k.lower(): v for k, v in self.headers.items()}
            seen.append({"method": self.command, "path": self.path, "headers": headers, "raw": raw})
            with contextlib.suppress(OSError):  # the client gave up (timeout tests)
                respond(self, json.loads(raw))

        do_POST = _handle
        do_PUT = _handle

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    with serving(server) as url:
        yield url, seen


def closed_port_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}/answer"


def _suite_file(tmp_path: Path, n: int = 2) -> Path:
    p = tmp_path / "suite.json"
    p.write_text(tiny_suite(n).model_dump_json(), encoding="utf-8")
    return p


def _config_file(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "http.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# -- A1: same record as the command target ------------------------------------------------------------------


@pytest.mark.parametrize("suite_file", ["support-bot.yaml", "extraction.yaml"])
@pytest.mark.parametrize("flags", [(), ("--degrade",), ("--no-telemetry",)])
def test_http_run_matches_command_run(suite_file: str, flags: tuple[str, ...]) -> None:
    suite = load_suite(SUITES / suite_file)
    by_command = run_suite(suite, fake_adapter(*flags), clock=CLOCK)
    with fake_http_server(*flags) as url:
        by_http = run_suite(suite, fake_http_adapter(url), clock=CLOCK)
    assert [i.model_dump(mode="json") for i in by_http.items] == [
        i.model_dump(mode="json") for i in by_command.items
    ]
    assert by_http.target.kind == "http"
    assert by_http.target.detail == f"POST {url} (config: test)"
    assert any(i.passed for i in by_http.items)


def test_fixture_reports_error_for_unknown_items() -> None:
    with fake_http_server() as url:
        out = fake_http_adapter(url).produce(ITEMS)
    assert [o.error for o in out.values()] == ["fake target has no answer for this item"] * 2


# -- A2: request shape ---------------------------------------------------------------------------------------


def test_request_shape_and_order() -> None:
    items = tiny_suite(3).items
    with serve() as (url, seen):
        out = fake_http_adapter(url).produce(items)
    assert list(out) == ["i0", "i1", "i2"]
    assert [r["raw"] for r in seen] == [f'{{"id":"i{k}","input":{k}}}'.encode() for k in range(3)]
    for r in seen:
        assert r["method"] == "POST" and r["path"] == "/answer"
        assert r["headers"]["content-type"] == "application/json"
        assert r["headers"]["accept"] == "application/json"
        assert r["headers"]["user-agent"].startswith("yardstick/")
        assert "authorization" not in r["headers"]


def test_put_and_query_string_are_sent() -> None:
    with serve() as (url, seen):
        fake_http_adapter(url + "?v=2", method="PUT").produce(ITEMS[:1])
    assert seen[0]["method"] == "PUT" and seen[0]["path"] == "/answer?v=2"


def test_body_template() -> None:
    item = Item(id="q1", input={"question": "hi", "ctx": {"role": "admin", "n": [1, 2]}}, expected={"x": 1})
    body = {
        "messages": [{"role": "user", "content": "$input.question"}],
        "meta": {"ref": "$id", "literal": "$$id", "n": "$input.ctx.n.1", "all": "$input", "k": 3},
        "note": "costs $5, not a placeholder",
    }
    with serve() as (url, seen):
        fake_http_adapter(url, body=body).produce([item])
    assert json.loads(seen[0]["raw"]) == {
        "messages": [{"role": "user", "content": "hi"}],
        "meta": {"ref": "q1", "literal": "$id", "n": 2, "all": item.input, "k": 3},
        "note": "costs $5, not a placeholder",
    }


def test_body_template_that_does_not_fit_fails_before_any_request() -> None:
    good = Item(id="a", input={"question": "hi"}, expected={"x": 1})
    bad = Item(id="b", input={"prompt": "hi"}, expected={"x": 1})
    expected = "http target: item 'b': the input has no value at 'input.question'"
    with serve() as (url, seen), pytest.raises(AdapterError) as err:
        fake_http_adapter(url, body={"q": "$input.question"}).produce([good, bad])
    assert str(err.value) == expected
    assert seen == []


# -- A3: response mapping ------------------------------------------------------------------------------------

MAPPING = {
    "text": "data.answer",
    "refused": {"path": "data.status", "values": ["refused", "blocked"]},
    "latency_ms": "usage.ms",
    "cost_usd": "usage.usd",
    "error": "err",
    "fields": {"citations": "data.citations", "status": "data.status"},
}


def test_response_mapping() -> None:
    docs: dict[str, Any] = {
        "i0": {
            "data": {"answer": "yes", "status": "ok", "citations": [{"id": "kb-1", "quote": "q"}]},
            "usage": {"ms": 12, "usd": 0.0100004},
        },
        "i1": {"data": {"answer": {"b": 1, "a": 2}, "status": "blocked"}},
        "i2": {"err": "model overloaded"},
        "i3": {"data": {"answer": "partial"}, "err": {"code": 7}},
    }
    with serve(lambda h, req: reply(h, 200, docs[req["id"]])) as (url, _):
        out = fake_http_adapter(url, response=MAPPING).produce(tiny_suite(4).items)
    assert out["i0"].text == "yes" and out["i0"].refused is False and out["i0"].error is None
    assert out["i0"].latency_ms == 12 and out["i0"].cost_usd == 0.01
    assert out["i0"].fields == {"citations": [{"id": "kb-1", "quote": "q"}], "status": "ok"}
    assert out["i1"].text == '{"a":2,"b":1}' and out["i1"].refused is True
    assert out["i2"].text == "" and out["i2"].error == "model overloaded" and out["i2"].refused is None
    assert out["i3"].text == "partial" and out["i3"].error == '{"code":7}'


def test_response_mapping_defaults_are_the_command_protocol() -> None:
    row = {"id": "i0", "output": "ok", "refused": True, "latency_ms": 5, "cost_usd": 0.5, "error": None}
    with serve(lambda h, req: reply(h, 200, row)) as (url, _):
        out = fake_http_adapter(url).produce(ITEMS[:1])["i0"]
    assert (out.text, out.refused, out.latency_ms, out.cost_usd, out.error) == ("ok", True, 5, 0.5, None)
    assert out.fields == {}


def test_missing_optional_values_are_not_reported() -> None:
    """YS-04: an absent or null value is never defaulted, and Yardstick does not measure latency itself."""
    docs: dict[str, Any] = {
        "i0": {"output": "ok"},
        "i1": {"output": "ok", "latency_ms": None, "refused": None},
    }
    with serve(lambda h, req: reply(h, 200, docs[req["id"]])) as (url, _):
        out = fake_http_adapter(url).produce(ITEMS)
    for o in out.values():
        assert o.refused is None and o.latency_ms is None and o.cost_usd is None and o.error is None
    with serve() as (url, _):
        only_text = fake_http_adapter(
            url, response={"refused": None, "latency_ms": None, "cost_usd": None, "error": None}
        ).produce(ITEMS[:1])["i0"]
    assert only_text.text == "ok" and only_text.latency_ms is None


def test_whole_body_can_be_the_text() -> None:
    with serve(lambda h, req: reply(h, 200, ["a", 1])) as (url, _):
        out = fake_http_adapter(url, response={"text": ""}).produce(ITEMS[:1])
    assert out["i0"].text == '["a",1]'


# -- A4: secrets ---------------------------------------------------------------------------------------------

AUTH = {"Authorization": {"env": "YS_TEST_TOKEN", "scheme": "Bearer"}}


def _adapter(url: str, env: dict[str, str], **config: Any) -> HttpAdapter:
    return HttpAdapter("t", parse_http_config({"url": url, **config}), "test", env=env)


def test_secret_headers_come_from_the_environment() -> None:
    headers = {**AUTH, "X-Api-Version": {"env": "YS_TEST_VERSION", "secret": False}}
    env = {"YS_TEST_TOKEN": SECRET, "YS_TEST_VERSION": "2"}
    with serve() as (url, seen):
        adapter = _adapter(url, env, headers=headers)
        out = adapter.produce(ITEMS[:1])
    assert seen[0]["headers"]["authorization"] == f"Bearer {SECRET}"
    assert seen[0]["headers"]["x-api-version"] == "2"
    assert out["i0"].text == "ok"
    assert SECRET not in adapter.info.model_dump_json()
    assert SECRET not in repr(adapter.config)


def test_secret_env_var_missing_fails_before_any_request() -> None:
    with serve() as (url, seen):
        for env in ({}, {"YS_TEST_TOKEN": ""}):
            with pytest.raises(
                AdapterError, match=r"environment variable YS_TEST_TOKEN \(header Authorization\) is not set"
            ):
                _adapter(url, env, headers=AUTH).produce(ITEMS)
    assert seen == []


@pytest.mark.parametrize("value", [f"{SECRET}\r\nX-Injected: 1", f"{SECRET}\n", f" {SECRET}", f"{SECRET}☃"])
def test_secret_value_that_cannot_be_sent_is_not_echoed(value: str) -> None:
    with serve() as (url, seen), pytest.raises(AdapterError) as err:
        _adapter(url, {"YS_TEST_TOKEN": value}, headers=AUTH).produce(ITEMS)
    assert "YS_TEST_TOKEN" in str(err.value) and SECRET not in str(err.value)
    assert seen == []


def _echo_auth(h: BaseHTTPRequestHandler, request: Any) -> None:
    auth = h.headers.get("Authorization", "")
    doc = {"output": f"you sent {auth}", "error": f"debug: {auth}", "trace": {"hdr": [auth], auth: 1}}
    reply(h, 200, doc)


def test_secret_echoed_by_the_server_is_scrubbed_everywhere() -> None:
    suite = tiny_suite(2)
    with serve(_echo_auth) as (url, _):
        adapter = _adapter(
            url + "?api_key=in-query",
            {"YS_TEST_TOKEN": SECRET},
            headers=AUTH,
            response={"fields": {"t": "trace"}},
        )
        run = run_suite(suite, adapter, clock=CLOCK)
    out = run.items[0].output
    assert out.text == "you sent Bearer [redacted:$YS_TEST_TOKEN]"
    assert out.error == "debug: Bearer [redacted:$YS_TEST_TOKEN]"
    assert out.fields == {
        "t": {"hdr": ["Bearer [redacted:$YS_TEST_TOKEN]"], "Bearer [redacted:$YS_TEST_TOKEN]": 1}
    }
    for artefact in (run_to_json(run), render(run), render_html(run)):
        assert SECRET not in artefact
        assert "in-query" not in artefact
    assert run.target.detail == f"POST {url} (config: test)"


@pytest.mark.parametrize("on_error", ["fail", "record"])
def test_secret_in_an_error_response_is_never_reported(on_error: str) -> None:
    def deny(h: BaseHTTPRequestHandler, request: Any) -> None:
        reply(h, 401, {"error": f"bad token {h.headers.get('Authorization')}"})

    def leak(h: BaseHTTPRequestHandler, request: Any) -> None:
        reply(h, 200, f"not json {h.headers.get('Authorization')}".encode())

    for respond, reason in ((deny, "HTTP 401"), (leak, "response is not JSON: Expecting value")):
        with serve(respond) as (url, _):
            adapter = _adapter(
                url + "?k=in-query", {"YS_TEST_TOKEN": SECRET}, headers=AUTH, on_error=on_error
            )
            if on_error == "fail":
                with pytest.raises(AdapterError) as err:
                    adapter.produce(ITEMS)
                message = str(err.value)
                assert err.value.__cause__ is None and err.value.__suppress_context__
            else:
                message = str(adapter.produce(ITEMS)["i0"].error)
        assert reason in message
        assert SECRET not in message and "in-query" not in message


def test_redirect_is_not_followed() -> None:
    """A redirect would resend the Authorization header to wherever the server points."""
    with serve() as (elsewhere, seen_elsewhere):

        def redirect(h: BaseHTTPRequestHandler, request: Any) -> None:
            reply(h, 307, {"moved": True}, {"Location": elsewhere})

        with serve(redirect) as (url, seen), pytest.raises(AdapterError) as err:
            _adapter(url, {"YS_TEST_TOKEN": SECRET}, headers=AUTH).produce(ITEMS)
        assert str(err.value) == "http target: item 'i0': HTTP 307 (redirects are not followed)"
        assert len(seen) == 1
    assert seen_elsewhere == []


def test_proxy_environment_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, closed_port_url())
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    with serve() as (url, seen):
        assert fake_http_adapter(url).produce(ITEMS[:1])["i0"].text == "ok"
    assert len(seen) == 1


def test_safe_url_drops_query_and_fragment() -> None:
    assert (
        safe_url("https://api.example.test:8443/v1/answer?key=abc#frag")
        == "https://api.example.test:8443/v1/answer"
    )
    assert safe_url("http://127.0.0.1:1") == "http://127.0.0.1:1/"


# -- A5 / A6: failures ---------------------------------------------------------------------------------------

BIG = DEFAULT_MAX_RESPONSE_BYTES + 1


def _status_500(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 500, {"output": "should not be read"})


def _status_404(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 404, b"<html>nope</html>")


def _not_json(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, b"<html>hello</html>")


def _empty(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 204, b"")


def _nan(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, b'{"output": "x", "cost_usd": NaN}')


def _missing_field(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"answer": "the mapped field is 'output'"})


def _null_field(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": None})


def _bad_latency(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": "x", "latency_ms": "fast"})


def _negative_latency(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": "x", "latency_ms": -5})


def _bad_cost(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": "x", "cost_usd": "0.1"})


def _huge_cost(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, b'{"output": "x", "cost_usd": 1e999}')


def _bad_refused(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, {"output": "x", "refused": "no"})


def _huge_declared(h: BaseHTTPRequestHandler, request: Any) -> None:
    reply(h, 200, b'{"output": "' + b"x" * BIG + b'"}')


def _huge_undeclared(h: BaseHTTPRequestHandler, request: Any) -> None:
    h.send_response(200)  # HTTP/1.0, no Content-Length: the body runs until the connection closes
    h.end_headers()
    h.wfile.write(b'{"output": "' + b"x" * BIG + b'"}')


def _slow(h: BaseHTTPRequestHandler, request: Any) -> None:
    time.sleep(1.5)
    reply(h, 200, {"output": "too late"})


def _hangs_up(h: BaseHTTPRequestHandler, request: Any) -> None:
    h.connection.shutdown(socket.SHUT_RDWR)


FAILURES: list[tuple[Respond, dict[str, Any], str]] = [
    (_status_500, {}, "HTTP 500"),
    (_status_404, {}, "HTTP 404"),
    (_not_json, {}, "response is not JSON: Expecting value"),
    (_empty, {}, "response is not JSON: Expecting value"),
    (_nan, {}, "response is not JSON: non-finite number or nesting too deep"),
    (_missing_field, {}, "response has no value at 'output'"),
    (_null_field, {}, "response has no value at 'output'"),
    (_bad_latency, {}, "response value at 'latency_ms' is not an integer"),
    (_negative_latency, {}, "bad response value: Value error, latency_ms must be >= 0"),
    (_bad_cost, {}, "response value at 'cost_usd' is not a number"),
    (_huge_cost, {}, "response value at 'cost_usd' is not a number"),
    (_bad_refused, {}, "response value at 'refused' is not a boolean"),
    (_huge_declared, {}, f"response larger than {DEFAULT_MAX_RESPONSE_BYTES} bytes"),
    (_huge_undeclared, {}, f"response larger than {DEFAULT_MAX_RESPONSE_BYTES} bytes"),
    (_missing_field, {"max_response_bytes": 20}, "response larger than 20 bytes"),
    (_slow, {"timeout_s": 0.3}, "timed out after 0.3s"),
    (_hangs_up, {}, "connection failed (RemoteDisconnected)"),
]
FAILURE_IDS = [f"{f.__name__.lstrip('_')}-{n}" for n, (f, _, _) in enumerate(FAILURES)]


def _fails_on_first_item(respond: Respond) -> Respond:
    def choose(h: BaseHTTPRequestHandler, request: Any) -> None:
        (respond if request["id"] == "i0" else ok)(h, request)

    return choose


@pytest.mark.parametrize(("respond", "config", "reason"), FAILURES, ids=FAILURE_IDS)
def test_failure_fails_the_run(respond: Respond, config: dict[str, Any], reason: str) -> None:
    """Default (`on_error: fail`): one failed request aborts the run, like a crashed command target (D-14)."""
    with serve(_fails_on_first_item(respond)) as (url, seen), pytest.raises(AdapterError) as err:
        fake_http_adapter(url, **config).produce(ITEMS)
    assert str(err.value) == f"http target: item 'i0': {reason}"
    assert len(seen) == 1, "no retry, and no request after the failure"


@pytest.mark.parametrize(("respond", "config", "reason"), FAILURES, ids=FAILURE_IDS)
def test_failure_is_recorded_when_configured(respond: Respond, config: dict[str, Any], reason: str) -> None:
    suite = tiny_suite(2)
    with serve(_fails_on_first_item(respond)) as (url, seen):
        run = run_suite(suite, fake_http_adapter(url, on_error="record", **config), clock=CLOCK)
    failed, fine = run.items
    assert failed.output.error == reason and failed.output.text == "" and not failed.passed
    assert failed.output.latency_ms is None and failed.output.cost_usd is None
    assert fine.output.error is None and fine.output.text == "ok" and fine.passed
    assert [json.loads(r["raw"])["id"] for r in seen] == ["i0", "i1"], "one request per item, no retry"


def test_connection_refused() -> None:
    url = closed_port_url()
    with pytest.raises(AdapterError) as err:
        fake_http_adapter(url).produce(ITEMS)
    assert str(err.value) == "http target: item 'i0': connection failed (ConnectionRefusedError)"
    out = fake_http_adapter(url, on_error="record").produce(ITEMS)
    assert [o.error for o in out.values()] == ["connection failed (ConnectionRefusedError)"] * 2


def test_slow_drip_response_times_out() -> None:
    """Each read is quick, so the socket timeout never fires; the limit on the whole request does."""

    def drip(h: BaseHTTPRequestHandler, request: Any) -> None:
        h.send_response(200)
        h.send_header("Content-Length", "1000")
        h.end_headers()
        for _ in range(100):
            h.wfile.write(b" ")
            h.wfile.flush()
            time.sleep(0.05)

    with serve(drip) as (url, _):
        started = time.monotonic()
        with pytest.raises(AdapterError, match=r"item 'i0': timed out after 0\.4s"):
            fake_http_adapter(url, timeout_s=0.4).produce(ITEMS)
        assert time.monotonic() - started < 2.0


def test_timeout_default_and_override() -> None:
    cfg = parse_http_config({"url": "http://127.0.0.1:9/"})
    assert cfg.timeout_s == DEFAULT_TIMEOUT_S == 30.0
    assert HttpAdapter("t", cfg).timeout_s == 30.0
    assert HttpAdapter("t", cfg, timeout_s=2.5).timeout_s == 2.5
    with pytest.raises(AdapterError, match="positive"):
        HttpAdapter("t", cfg, timeout_s=0)


def test_tests_only_use_loopback() -> None:
    """The guard above works: a non-loopback address is refused before any packet is sent."""
    with pytest.raises(NonLoopback):
        socket.create_connection(("192.0.2.1", 80), timeout=0.1)
    with pytest.raises(AdapterError, match=r"connection failed \(NonLoopback\)"):
        fake_http_adapter("http://192.0.2.1/answer", timeout_s=0.1).produce(ITEMS)


# -- A9: config validation -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        {},  # no url
        {"url": "ftp://127.0.0.1/x"},
        {"url": "127.0.0.1:8808/answer"},
        {"url": "http:///answer"},
        {"url": "http://127.0.0.1:port/answer"},
        {"url": "http://127.0.0.1/a b"},
        {"url": "http://user:hunter2-in-url@127.0.0.1/answer"},
        {"url": "http://127.0.0.1/", "method": "GET"},
        {"url": "http://127.0.0.1/", "retries": 3},
        {"url": "http://127.0.0.1/", "timeout_s": 0},
        {"url": "http://127.0.0.1/", "max_response_bytes": 0},
        {"url": "http://127.0.0.1/", "on_error": "skip"},
        {"url": "http://127.0.0.1/", "body": {"q": "$question"}},
        {"url": "http://127.0.0.1/", "body": ["$inputs"]},
        {"url": "http://127.0.0.1/", "headers": {"Authorization": "Bearer literal-secret-in-config"}},
        {"url": "http://127.0.0.1/", "headers": {"Authorization": {"env": "literal secret-in-config"}}},
        {
            "url": "http://127.0.0.1/",
            "headers": {"Authorization": {"env": "T", "value": "literal-secret-in-config"}},
        },
        {
            "url": "http://127.0.0.1/",
            "headers": {"Authorization": {"env": "T", "scheme": "Bearer literal-secret-in-config"}},
        },
        {"url": "http://127.0.0.1/", "headers": {"Bad Header": {"env": "T"}}},
        {"url": "http://127.0.0.1/", "headers": {"Content-Type": {"env": "T"}}},
        {"url": "http://127.0.0.1/", "headers": {"X-A": {"env": "T"}, "x-a": {"env": "U"}}},
        {"url": "http://127.0.0.1/", "response": {"rows": "rows"}},
        ["not", "a", "mapping"],
    ],
)
def test_config_validation(config: Any) -> None:
    with pytest.raises(AdapterError, match="bad http target config") as err:
        parse_http_config(config)
    assert "hunter2" not in str(err.value) and "secret-in-config" not in str(err.value)


def test_load_http_config(tmp_path: Path) -> None:
    cfg = load_http_config(FAKE_HTTP_CONFIG)
    assert cfg == parse_http_config({"url": "http://127.0.0.1:8808/answer"}), (
        "the fixture config is the defaults"
    )
    assert load_http_config(FAKE_HTTP_CONFIG, "http://127.0.0.1:1/x").url == "http://127.0.0.1:1/x"
    empty = _config_file(tmp_path, "")
    assert load_http_config(empty, "http://127.0.0.1:1/x").method == "POST"
    with pytest.raises(AdapterError, match=r"http\.yaml: bad http target config: url: Field required"):
        load_http_config(empty)
    with pytest.raises(AdapterError, match="cannot read http target config"):
        load_http_config(tmp_path / "nope.yaml")
    with pytest.raises(AdapterError, match="not valid YAML") as err:
        load_http_config(_config_file(tmp_path, "url: [unclosed-secret-in-config"))
    assert "secret-in-config" not in str(err.value)


# -- A8: CLI -------------------------------------------------------------------------------------------------


def _cli_run(suite: Path, out: Path, *target: str) -> Any:
    args = ["run", "-s", str(suite), "-o", str(out), "--target-name", "fake", "--no-git"]
    return runner.invoke(app, [*args, "--fixed-clock", "2026-11-14T00:00:00Z", *target])


def test_cli_http_end_to_end_gates_against_the_command_baseline(tmp_path: Path) -> None:
    suite = SUITES / "support-bot.yaml"
    baseline, healthy, degraded = (
        tmp_path / "base.json",
        tmp_path / "healthy.json",
        tmp_path / "degraded.json",
    )
    res = _cli_run(
        suite, baseline, "--cmd", f"{sys.executable} {FAKE_HTTP_TARGET.with_name('fake_target.py')}"
    )
    assert res.exit_code == 0, res.output
    with fake_http_server() as healthy_url:
        res = _cli_run(suite, healthy, "--http", str(FAKE_HTTP_CONFIG), "--http-url", healthy_url)
        assert res.exit_code == 0, res.output
    with fake_http_server("--degrade") as url:
        res = _cli_run(suite, degraded, "--http", str(FAKE_HTTP_CONFIG), "--http-url", url)
        assert res.exit_code == 0, res.output
    assert load_run(healthy).target.kind == "http"
    assert load_run(healthy).target.detail == f"POST {healthy_url} (config: fake-http.yaml)"
    gate_cfg = str(GATES / "support-bot.yaml")
    ok_gate = runner.invoke(app, ["gate", str(healthy), "-c", gate_cfg, "--baseline", str(baseline)])
    assert ok_gate.exit_code == 0, ok_gate.output
    bad_gate = runner.invoke(app, ["gate", str(degraded), "-c", gate_cfg, "--baseline", str(baseline)])
    assert bad_gate.exit_code == 1, bad_gate.output
    cmp = runner.invoke(app, ["compare", str(baseline), str(healthy)])
    assert cmp.exit_code == 0 and "newly failing: -" in cmp.output


def test_cli_http_dead_endpoint_exits_2_and_writes_no_run(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    res = _cli_run(
        _suite_file(tmp_path), out, "--http", str(FAKE_HTTP_CONFIG), "--http-url", closed_port_url()
    )
    assert res.exit_code == 2
    assert "error: http target: item 'i0': connection failed (ConnectionRefusedError)" in res.output
    assert not out.exists()


def test_cli_http_timeout_overrides_the_config(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    with serve(_slow) as (url, _):
        cfg = _config_file(tmp_path, f"url: {url}\ntimeout_s: 20\n")
        res = _cli_run(_suite_file(tmp_path), out, "--http", str(cfg), "--timeout", "0.2")
    assert res.exit_code == 2 and "timed out after 0.2s" in res.output
    assert not out.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--http", "x.yaml", "--cmd", "true"],  # two targets
        ["--http", "x.yaml", "--results", "x.json", "--mapping", "footnote"],  # two targets
        ["--http-url", "http://127.0.0.1:1/"],  # url without a config
        ["--cmd", "true", "--http-url", "http://127.0.0.1:1/"],  # url with another target
        ["--http", "x.yaml", "--mapping", "footnote"],  # mapping without results
        ["--http", "x.yaml", "--theta-prime", "0.5"],
        ["--http", "does-not-exist.yaml"],
    ],
)
def test_cli_http_target_options_are_validated(tmp_path: Path, extra: list[str]) -> None:
    res = _cli_run(_suite_file(tmp_path), tmp_path / "r.json", *extra)
    assert res.exit_code == 2
    assert not (tmp_path / "r.json").exists()


def test_cli_http_secret_never_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The proof for the secrets rule, through the CLI: stdout, stderr, run file and both reports."""
    monkeypatch.setenv("YS_TEST_TOKEN", SECRET)
    suite = tmp_path / "suite.json"
    suite.write_text(
        Suite(
            name="echo",
            scorers=[ScorerSpec(name="regex")],
            items=[Item(id="q1", input={"q": "hi"}, expected={"regex": "you sent"})],
        ).model_dump_json(),
        encoding="utf-8",
    )
    out, md, html = tmp_path / "run.json", tmp_path / "report.md", tmp_path / "report.html"
    with serve(_echo_auth) as (url, seen):
        cfg = _config_file(
            tmp_path,
            f"url: {url}?api_key=in-query\n"
            "headers:\n  Authorization: {env: YS_TEST_TOKEN, scheme: Bearer}\n"
            "response:\n  fields: {trace: trace}\n",
        )
        res = _cli_run(suite, out, "--http", str(cfg))
        assert res.exit_code == 0, res.output
        monkeypatch.delenv("YS_TEST_TOKEN")
        unset = _cli_run(suite, tmp_path / "unset.json", "--http", str(cfg))
    assert seen[0]["headers"]["authorization"] == f"Bearer {SECRET}", "the server did get the secret"
    assert len(seen) == 1 and unset.exit_code == 2
    assert "environment variable YS_TEST_TOKEN (header Authorization) is not set" in unset.output
    assert runner.invoke(app, ["report", str(out), "-o", str(md)]).exit_code == 0
    assert runner.invoke(app, ["report", str(out), "-f", "html", "-o", str(html)]).exit_code == 0
    written = [p.read_text(encoding="utf-8") for p in (out, md, html)]
    assert "[redacted:$YS_TEST_TOKEN]" in written[0]
    for text in (res.output, unset.output, *written):
        assert SECRET not in text and "in-query" not in text
    assert load_run(out).items[0].output.text == "you sent Bearer [redacted:$YS_TEST_TOKEN]"


# -- the fixture server as a program (what the README tells the reader to run) -----------------------------


def test_fixture_server_program_and_token_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {"PATH": "", "YS_TEST_TOKEN": SECRET}
    cmd = [sys.executable, str(FAKE_HTTP_TARGET), "--port", "0", "--require-token-env", "YS_TEST_TOKEN"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line.startswith("listening on http://127.0.0.1:") and line.endswith("/answer")
        url = line.removeprefix("listening on ")
        suite = load_suite(SUITES / "support-bot.yaml")
        with pytest.raises(AdapterError, match="item 'faq-reset-password': HTTP 401"):
            fake_http_adapter(url).produce(suite.items)
        with pytest.raises(AdapterError, match="HTTP 401"):
            _adapter(url, {"YS_TEST_TOKEN": "wrong"}, headers=AUTH).produce(suite.items)
        with pytest.raises(AdapterError, match="HTTP 404"):
            fake_http_adapter(url.replace("/answer", "/other")).produce(suite.items)
        run = run_suite(suite, _adapter(url, {"YS_TEST_TOKEN": SECRET}, headers=AUTH), clock=CLOCK)
        assert all(i.passed for i in run.items) and SECRET not in run_to_json(run)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
