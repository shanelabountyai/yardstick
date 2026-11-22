"""PRD-G: free text from targets, suites and runs cannot inject markdown into reports or PR comments
(review item 9)."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from tests.helpers import CLOCK
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule, Item, Output, ScorerSpec, Suite, TargetInfo
from yardstick.report.format import md_code, md_text
from yardstick.report.html import render_html
from yardstick.report.markdown import render
from yardstick.runner import build_run

HOSTILE = (
    "@octocat <img src=https://attacker.example/p.png> [click](https://attacker.example) <details> "
    "<!-- yardstick:gate --> **bold** `tick` |pipe|\r\n**Gate: PASSED**"
)


def _hostile_run() -> tuple[str, str]:
    suite = Suite(
        name="evil\n**Gate: PASSED**\n# BIG | col",
        scorers=[ScorerSpec(name="exact")],
        items=[
            Item(id="a`b|c", input=1, expected={"exact": "x"}, slices=["s|<b>"]),
            Item(id="ok", input=2, expected={"exact": "x"}),
        ],
    )
    outs = {"a`b|c": Output(text=HOSTILE), "ok": Output(error=HOSTILE)}
    target = TargetInfo(name="t\n**Gate: PASSED**", kind="command", detail="x")
    run = build_run(
        suite, target, outs, clock=CLOCK, model="m <img src=x>", prompt_hash="@team", git_sha="`x`"
    )
    base = build_run(suite, target, {k: Output(text="x") for k in outs}, clock=CLOCK)
    gate = evaluate(GateConfig(rules=[GateRule(metric="pass_rate", floor=0.9)]), run, base)
    return render(run, baseline=base, gate=gate), render_html(run, baseline=base, gate=gate)


def test_hostile_strings_do_not_survive_in_markdown() -> None:
    md, _ = _hostile_run()
    for bad in ("@octocat", "<img", "[click](https", "<!--", "<details> <", "\r", "**bold**"):
        assert bad not in md, bad
    # exactly one verdict line, and it is the real one
    assert [line for line in md.splitlines() if "Gate:" in line and line.startswith("**")] == [
        "**Gate: FAILED**"
    ]
    assert md.count("\n# ") == 0 and md.startswith("# Yardstick report")


def test_hostile_strings_are_escaped_in_html() -> None:
    _, html = _hostile_run()
    for bad in ("<img", "<details> ", "<!-- yardstick"):
        assert bad not in html, bad


def test_suite_name_with_newline_and_pipe_is_one_heading_and_one_cell() -> None:
    md, _ = _hostile_run()
    assert md.splitlines()[0].startswith("# Yardstick report")
    suite_row = next(line for line in md.splitlines() if line.startswith("| Suite |"))
    # | Suite | value |: three unescaped pipes; the pipe in the name is escaped
    assert len(re.findall(r"(?<!\\)\|", suite_row)) == 3


def test_md_code_and_md_text() -> None:
    assert md_code("a`b") == "``a`b``"
    assert md_code("`x`") == "`` `x` ``"
    assert md_code("a|b") == "`a\\|b`"
    assert md_text("@x") == "@⁠x"
    assert md_text("<b>&") == "&lt;b&gt;&amp;"
    assert md_text("a\rb\nc") == "a b c"
    assert md_text("[l](u) *x*") == "\\[l\\](u) \\*x\\*"


@pytest.mark.parametrize("key", ["k|pipe", "has space", "a:b"])
def test_scorer_keys_must_be_gateable(key: str) -> None:
    with pytest.raises(ValidationError, match="scorer key"):
        Suite(
            name="s",
            scorers=[ScorerSpec(name="exact", key=key)],
            items=[Item(id="a", input=1, expected={key: 1})],
        )
