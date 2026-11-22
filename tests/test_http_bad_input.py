"""PRD-E in the http target: endpoint- or config-controlled input fails cleanly (review item 7)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from typing import Any

import pytest

from tests.helpers import fake_http_adapter
from tests.test_http_adapter import ITEMS, _loopback_only, serve  # noqa: F401 (autouse fixture)
from yardstick.adapters.base import AdapterError
from yardstick.adapters.http import parse_http_config


def _bad_length(h: BaseHTTPRequestHandler, request: Any) -> None:
    raw = b'{"output": "ok"}'
    h.send_response(200)
    h.send_header("Content-Length", "²")  # superscript two: str.isdigit() is True, int() raises
    h.end_headers()
    h.wfile.write(raw)
    h.close_connection = True


def test_non_ascii_content_length_does_not_crash() -> None:
    with serve(_bad_length) as (url, _):
        outs = fake_http_adapter(url).produce(ITEMS)
    assert outs["i0"].text == "ok"


def _deep(h: BaseHTTPRequestHandler, request: Any) -> None:
    import json

    nested: Any = 1
    for _ in range(900):
        nested = [nested]
    raw = json.dumps({"output": "ok", "f": nested}).encode()
    h.send_response(200)
    h.send_header("Content-Length", str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)


def test_deeply_nested_fields_fail_the_request_cleanly() -> None:
    with serve(_deep) as (url, _), pytest.raises(AdapterError, match="nested deeper than 64"):
        fake_http_adapter(url, response={"fields": {"f": "f"}}).produce(ITEMS)
    with serve(_deep) as (url, _):
        outs = fake_http_adapter(url, response={"fields": {"f": "f"}}, on_error="record").produce(ITEMS)
    assert outs["i0"].error is not None and "nested deeper" in outs["i0"].error


@pytest.mark.parametrize(
    "config",
    [
        {"url": "http://127.0.0.1:1/päth"},
        {"url": "http://127.0.0.1:1/a", "headers": {"X-Foo\n": {"env": "V"}}},
        {"url": "http://127.0.0.1:1/a", "headers": {"X-Foo": {"env": "V\n"}}},
        {"url": "http://127.0.0.1:1/a", "headers": {"X-Foo": {"env": "V", "scheme": "Bearer\n"}}},
    ],
)
def test_config_values_with_trailing_newlines_or_non_ascii_are_refused(config: dict[str, Any]) -> None:
    with pytest.raises(AdapterError, match="bad http target config"):
        parse_http_config(config)
