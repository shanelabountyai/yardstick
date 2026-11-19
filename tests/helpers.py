"""Shared test helpers."""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

from yardstick.adapters.command import CommandAdapter
from yardstick.adapters.http import HttpAdapter, parse_http_config
from yardstick.clock import FixedClock
from yardstick.models import Item, Output, Run, ScorerSpec, Suite, TargetInfo
from yardstick.runner import build_run

ROOT = Path(__file__).resolve().parent.parent
SUITES = ROOT / "fixtures" / "suites"
GATES = ROOT / "fixtures" / "gates"
FAKE_TARGET = ROOT / "fixtures" / "targets" / "fake_target.py"

CLOCK = FixedClock(datetime(2026, 11, 14, tzinfo=UTC))
TARGET = TargetInfo(name="t", kind="command", detail="test")


def fake_adapter(*flags: str) -> CommandAdapter:
    return CommandAdapter("fake", [sys.executable, str(FAKE_TARGET), *flags])


def tiny_suite(n: int, name: str = "tiny", slice_name: str = "s") -> Suite:
    return Suite(
        name=name,
        scorers=[ScorerSpec(name="exact")],
        items=[Item(id=f"i{k}", input=k, expected={"exact": "ok"}, slices=[slice_name]) for k in range(n)],
    )


def run_from_passes(
    passes: list[bool],
    *,
    name: str = "tiny",
    latency: Sequence[int | None] | None = None,
    cost: Sequence[float | None] | None = None,
) -> Run:
    """Build a run over ``tiny_suite`` where item k passes iff passes[k]."""
    suite = tiny_suite(len(passes), name=name)
    outputs = {
        f"i{k}": Output(
            text="ok" if p else "nope",
            latency_ms=latency[k] if latency else None,
            cost_usd=cost[k] if cost else None,
        )
        for k, p in enumerate(passes)
    }
    return build_run(suite, TARGET, outputs, clock=CLOCK)


# -- http target fixture (Phase 5) -------------------------------------------------------------------------

FAKE_HTTP_TARGET = ROOT / "fixtures" / "targets" / "fake_http_target.py"
FAKE_HTTP_CONFIG = ROOT / "fixtures" / "targets" / "fake-http.yaml"


def load_fake_http() -> ModuleType:
    """Import ``fixtures/targets/fake_http_target.py`` (a script, not a package module)."""
    spec = importlib.util.spec_from_file_location("fake_http_target", FAKE_HTTP_TARGET)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def serving(server: HTTPServer) -> Iterator[str]:
    """Serve ``server`` (bound to 127.0.0.1) on a thread for the duration; yields its ``/answer`` URL."""
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/answer"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def fake_http_server(*flags: str, token: str | None = None) -> Iterator[str]:
    """The fixture HTTP target on a free port. ``flags`` as for ``fake_target.py``."""
    server: HTTPServer = load_fake_http().make_server(
        0, degrade="--degrade" in flags, telemetry="--no-telemetry" not in flags, token=token
    )
    with serving(server) as url:
        yield url


def fake_http_adapter(url: str, **config: Any) -> HttpAdapter:
    return HttpAdapter("fake", parse_http_config({"url": url, **config}), "test")
