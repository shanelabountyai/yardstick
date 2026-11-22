"""HTML report: one static file, no scripts or external URLs, escaped, deterministic, charts inline (as HTML
and CSS rows since D-90; they were inline SVG before)."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from tests.helpers import CLOCK, ROOT, TARGET, run_from_passes
from yardstick import gate as gate_mod
from yardstick.cli import app
from yardstick.models import GateConfig, GateRule, Item, Output, ScorerSpec, Suite
from yardstick.report.html import render_html
from yardstick.runner import build_run
from yardstick.suite_io import save_run


def _assert_static(html: str) -> None:
    assert html.startswith("<!doctype html>")
    assert "<script" not in html.lower()
    assert not re.search(r"(src|href)\s*=", html, re.IGNORECASE)
    assert not re.search(r"https?://", html)
    assert "@import" not in html


def test_html_is_static_and_has_charts() -> None:
    base = run_from_passes([True] * 10)
    cur = run_from_passes([True] * 7 + [False] * 3)
    cfg = GateConfig(rules=[GateRule(metric="pass_rate", floor=0.9, max_drop=0.02)])
    html = render_html(cur, baseline=base, gate=gate_mod.evaluate(cfg, cur, base))
    _assert_static(html)
    # D-90 (decision 8 (b)): the charts are HTML/CSS rows, not SVG. Two charts (slices + rates), each row a
    # label, a track with a bar and a baseline marker, and a value with a text alternative for the baseline.
    assert "<svg" not in html
    assert html.count('<figure class="chart"') == 2
    rows = re.findall(r'<li><span class="label[^"]*">.*?</li>', html)
    assert len(rows) == 2  # one slice ("s") and one rate ("exact")
    for row in rows:
        assert '<span class="track" aria-hidden="true">' in row
        assert re.search(r'<span class="bar" style="width: [\d.]+%"></span>', row)
        assert re.search(r'<span class="base" style="left: [\d.]+%"></span>', row)
        assert '<span class="sr">, baseline 100.0%</span>' in row
    assert "Gate failed" in html
    assert "not reported" in html  # no telemetry in this run (YS-04)
    assert html == render_html(cur, baseline=base, gate=gate_mod.evaluate(cfg, cur, base))


def test_html_escapes_untrusted_text() -> None:
    evil = "<script>alert(1)</script>"
    suite = Suite(
        name="x<b>",
        scorers=[ScorerSpec(name="exact")],
        items=[Item(id=evil, input=1, expected={"exact": "ok"}, slices=['"><img onerror=1>'])],
    )
    run = build_run(suite, TARGET, {evil: Output(text="nope")}, clock=CLOCK)
    html = render_html(run)
    _assert_static(html)
    assert "&lt;script&gt;" in html and "<img" not in html


def test_cli_report_html_and_gate_html(tmp_path: Path) -> None:
    run = tmp_path / "run.json"
    save_run(run_from_passes([True] * 10), run)
    out = tmp_path / "r.html"
    res = CliRunner().invoke(app, ["report", str(run), "--format", "html", "-o", str(out)])
    assert res.exit_code == 0, res.output
    _assert_static(out.read_text(encoding="utf-8"))
    gate_cfg = tmp_path / "g.yaml"
    gate_cfg.write_text("rules:\n  - metric: pass_rate\n    floor: 0.5\n", encoding="utf-8")
    out2 = tmp_path / "g.html"
    res = CliRunner().invoke(app, ["gate", str(run), "-c", str(gate_cfg), "--html-report", str(out2)])
    assert res.exit_code == 0, res.output
    assert "Gate passed" in out2.read_text(encoding="utf-8")


def test_committed_footnote_html_example_is_static() -> None:
    html = (ROOT / "examples" / "footnote" / "report.html").read_text(encoding="utf-8")
    _assert_static(html)
    assert "footnote-golden" in html and '<figure class="chart"' in html and "<svg" not in html
