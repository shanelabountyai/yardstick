"""Shared test helpers."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from yardstick.adapters.command import CommandAdapter
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
