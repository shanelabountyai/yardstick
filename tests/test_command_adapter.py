from __future__ import annotations

import sys

import pytest

from tests.helpers import fake_adapter, tiny_suite
from yardstick.adapters.base import AdapterError
from yardstick.adapters.command import CommandAdapter


def _py(code: str) -> CommandAdapter:
    return CommandAdapter("py", [sys.executable, "-c", code])


ITEMS = tiny_suite(2).items


def test_missing_command() -> None:
    with pytest.raises(AdapterError, match="not found"):
        CommandAdapter("x", ["definitely-not-a-real-binary-ys"]).produce(ITEMS)


def test_nonzero_exit() -> None:
    with pytest.raises(AdapterError, match="exited 3"):
        _py("import sys; sys.stderr.write('boom'); sys.exit(3)").produce(ITEMS)


def test_bad_json_line() -> None:
    with pytest.raises(AdapterError, match="not JSON"):
        _py("print('hello')").produce(ITEMS)


def test_unknown_and_duplicate_ids() -> None:
    with pytest.raises(AdapterError, match="unknown item id"):
        _py('print(\'{"id": "zz", "output": "x"}\')').produce(ITEMS)
    with pytest.raises(AdapterError, match="duplicate"):
        _py('print(\'{"id": "i0", "output": "x"}\'); print(\'{"id": "i0", "output": "x"}\')').produce(ITEMS)


def test_negative_latency_rejected() -> None:
    with pytest.raises(AdapterError, match="bad output row"):
        _py('print(\'{"id": "i0", "output": "x", "latency_ms": -5}\')').produce(ITEMS)


def test_timeout() -> None:
    with pytest.raises(AdapterError, match="timed out"):
        CommandAdapter("slow", [sys.executable, "-c", "import time; time.sleep(5)"], timeout_s=0.5).produce(
            ITEMS
        )


def test_fake_target_reports_error_for_unknown_items() -> None:
    out = fake_adapter().produce(ITEMS)
    assert all(o.error for o in out.values())


def test_json_output_is_canonicalised() -> None:
    out = _py('print(\'{"id": "i0", "output": {"b": 1, "a": 2}}\')').produce(ITEMS)
    assert out["i0"].text == '{"a":2,"b":1}'
    assert "i1" not in out
