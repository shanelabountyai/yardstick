from __future__ import annotations

from tests.helpers import run_from_passes
from yardstick.compare import compare


def test_flips_and_directions() -> None:
    a = run_from_passes([True, True, False, True], latency=[100, 100, 100, 100])
    b = run_from_passes([True, False, True, True], latency=[100, 100, 100, 300])
    c = compare(a, b)
    assert c.newly_failing == ["i1"]
    assert c.newly_passing == ["i2"]
    d = {(x.metric, x.slice): x for x in c.deltas}
    assert d[("pass_rate", None)].direction == "same"
    assert d[("latency_p95_ms", None)].direction == "worse"
    assert d[("cost_total_usd", None)].direction == "n/a"
    assert d[("cost_total_usd", None)].delta is None


def test_better_for_higher_pass_rate() -> None:
    a = run_from_passes([False, False])
    b = run_from_passes([True, False])
    d = {(x.metric, x.slice): x for x in compare(a, b).deltas}
    assert d[("pass_rate", None)].direction == "better"
    assert d[("pass_rate", None)].delta == 0.5
