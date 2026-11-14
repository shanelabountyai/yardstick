"""YS-01: same suite + outputs -> byte-identical run JSON (timestamps fixed by an injected clock)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import CLOCK, SUITES, TARGET, fake_adapter
from yardstick.clock import FixedClock
from yardstick.models import Output
from yardstick.runner import build_run, run_suite
from yardstick.suite_io import load_run, load_suite, run_to_json


@pytest.mark.parametrize("suite_file", ["support-bot.yaml", "extraction.yaml"])
@pytest.mark.parametrize("flags", [(), ("--degrade",), ("--no-telemetry",)])
def test_command_runs_are_byte_identical(suite_file: str, flags: tuple[str, ...]) -> None:
    suite = load_suite(SUITES / suite_file)
    first = run_to_json(run_suite(suite, fake_adapter(*flags), clock=CLOCK, git_sha="abc"))
    second = run_to_json(
        run_suite(load_suite(SUITES / suite_file), fake_adapter(*flags), clock=CLOCK, git_sha="abc")
    )
    assert first == second


def test_run_id_ignores_timestamp_but_not_content() -> None:
    suite = load_suite(SUITES / "support-bot.yaml")
    later = FixedClock(datetime(2030, 1, 1, tzinfo=UTC))
    a = run_suite(suite, fake_adapter(), clock=CLOCK)
    b = run_suite(suite, fake_adapter(), clock=later)
    c = run_suite(suite, fake_adapter("--degrade"), clock=CLOCK)
    assert a.run_id == b.run_id
    assert a.started_at != b.started_at
    assert a.run_id != c.run_id


def test_round_trip_is_stable(tmp_path: object) -> None:
    suite = load_suite(SUITES / "extraction.yaml")
    run = run_suite(suite, fake_adapter(), clock=CLOCK)
    from pathlib import Path

    p = Path(str(tmp_path)) / "r.json"
    p.write_text(run_to_json(run), encoding="utf-8")
    assert run_to_json(load_run(p)) == run_to_json(run)


@settings(max_examples=50)
@given(st.dictionaries(st.sampled_from([f"i{k}" for k in range(6)]), st.text(max_size=20)))
def test_build_run_deterministic_for_any_outputs(texts: dict[str, str]) -> None:
    from tests.helpers import tiny_suite

    suite = tiny_suite(6)
    outputs = {k: Output(text=v) for k, v in texts.items()}
    # Insertion order of the outputs mapping must not matter either.
    reversed_outputs = dict(reversed(list(outputs.items())))
    assert run_to_json(build_run(suite, TARGET, outputs, clock=CLOCK)) == run_to_json(
        build_run(suite, TARGET, reversed_outputs, clock=CLOCK)
    )
