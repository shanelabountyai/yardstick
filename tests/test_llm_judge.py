"""llm-judge scorer, budget cap, recorded and scripted judges, and the live client on a fake transport."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from tests.helpers import CLOCK, TARGET
from yardstick.judge.anthropic import API_URL, KEY_ENV, AnthropicJudge, parse_label, prompt_hash
from yardstick.judge.base import JudgeError, JudgeRequest
from yardstick.judge.budget import Budget
from yardstick.judge.recorded import RecordedJudge, ScriptedJudge, VerdictFile, load_verdicts
from yardstick.kappa import verdicts_from_run
from yardstick.metrics import compute
from yardstick.models import Item, Output, Run, ScorerSpec, Suite
from yardstick.runner import build_run
from yardstick.scorers import ScorerConfigError
from yardstick.scorers.llm_judge import JudgeSession

LABELS = ["supported", "partial", "unsupported"]
OPTS: dict[str, Any] = {"rubric": "Is it supported?", "labels": LABELS, "positive": ["supported"]}


def judged_suite(n: int = 3, units_field: str | None = "sentences", report_only: bool = True) -> Suite:
    opts = dict(OPTS) | ({"units_field": units_field} if units_field else {})
    return Suite(
        name="judged",
        scorers=[
            ScorerSpec(name="exact"),
            ScorerSpec(name="llm-judge", key="j", options=opts, report_only=report_only),
        ],
        items=[
            Item(id=f"i{k}", input={"q": k}, expected={"exact": "ok", "j": 1.0}, slices=["s"])
            for k in range(n)
        ],
    )


def outputs(n: int = 3, sentences: int = 2) -> dict[str, Output]:
    return {
        f"i{k}": Output(text="ok", fields={"sentences": [f"s{k}.{j}" for j in range(sentences)]})
        for k in range(n)
    }


def run_with(judge: Any, cap: float = 1.0, n: int = 3, sentences: int = 2, **kw: Any) -> Run:
    suite = judged_suite(n, **kw)
    return build_run(
        suite, TARGET, outputs(n, sentences), clock=CLOCK, judge=JudgeSession(judge, Budget(cap))
    )


# --------------------------------------------------------------------------- scorer


def test_judge_labels_units_and_pools_a_rate() -> None:
    judge = ScriptedJudge({"i0:0": "supported", "i0:1": "partial", "i1:0": "supported", "i1:1": "supported"})
    r = run_with(judge, n=3)
    j = {it.item_id: next(s for s in it.scores if s.key == "j") for it in r.items}
    assert j["i0"].labels == ["supported", "partial"] and (j["i0"].hits, j["i0"].total) == (1, 2)
    assert not j["i0"].passed and j["i1"].passed
    # i2: the scripted judge returns None (no valid label) for both units: counted out, named in the detail
    assert j["i2"].labels == [None, None] and (j["i2"].hits, j["i2"].total) == (0, 0)
    assert "2 without a valid label" in j["i2"].detail
    rate = compute(r).rates["j"]
    assert (rate.hits, rate.total, rate.value) == (3, 4, 0.75)
    assert all(it.passed for it in r.items)  # exact passes; the judge is report-only (D-36)
    rec = r.judges["j"]
    assert (rec.model, rec.calls, rec.units_judged, rec.units_invalid, rec.units_skipped_budget) == (
        "scripted",
        6,
        4,
        2,
        0,
    )


def test_whole_text_is_one_unit_without_units_field() -> None:
    judge = ScriptedJudge(lambda req: "supported" if req.unit_text == "ok" else "unsupported")
    r = run_with(judge, units_field=None)
    assert judge.calls == ["i0:0", "i1:0", "i2:0"]
    assert compute(r).rates["j"].value == 1.0


def test_missing_units_field_or_empty_list_does_not_apply() -> None:
    suite = judged_suite(2)
    outs = {"i0": Output(text="ok"), "i1": Output(text="ok", fields={"sentences": []})}
    r = build_run(suite, TARGET, outs, clock=CLOCK, judge=JudgeSession(ScriptedJudge({}), Budget(1)))
    assert all(s.key != "j" for it in r.items for s in it.scores)
    assert "j" not in compute(r).rates and r.judges["j"].calls == 0


def test_a_target_error_counts_zero_of_zero() -> None:
    suite = judged_suite(1)
    r = build_run(
        suite,
        TARGET,
        {"i0": Output(error="boom")},
        clock=CLOCK,
        judge=JudgeSession(ScriptedJudge({}), Budget(1)),
    )
    s = next(s for s in r.items[0].scores if s.key == "j")
    assert (s.hits, s.total, s.labels) == (0, 0, None)


def test_llm_judge_needs_a_session_and_report_only() -> None:
    with pytest.raises(ScorerConfigError, match="pass --judge"):
        build_run(judged_suite(1), TARGET, outputs(1), clock=CLOCK)
    with pytest.raises(ValidationError, match="report_only: true"):
        judged_suite(1, report_only=False)


@pytest.mark.parametrize(
    ("bad", "msg"),
    [
        ({"rubric": ""}, "rubric"),
        ({"labels": ["a", "a"]}, "distinct"),
        ({"positive": ["nope"]}, "must be in 'labels'"),
        ({"units_field": 3}, "units_field"),
        ({"temperature": 0}, "unknown options"),
    ],
)
def test_option_validation(bad: dict[str, Any], msg: str) -> None:
    suite = Suite(
        name="x",
        scorers=[ScorerSpec(name="llm-judge", options=OPTS | bad, report_only=True)],
        items=[Item(id="i0", input=None, expected={"llm-judge": 1.0})],
    )
    with pytest.raises(ScorerConfigError, match=msg):
        build_run(
            suite,
            TARGET,
            {"i0": Output(text="t")},
            clock=CLOCK,
            judge=JudgeSession(ScriptedJudge({}), Budget(1)),
        )


def test_labels_round_trip_and_feed_kappa(tmp_path: Path) -> None:
    r = run_with(ScriptedJudge(lambda req: "supported"), n=2)
    path = tmp_path / "run.json"
    path.write_text(r.model_dump_json(), encoding="utf-8")
    again = Run.model_validate_json(path.read_text(encoding="utf-8"))
    assert again == r
    identity, verdicts = verdicts_from_run(again, "j")
    assert identity.model == "scripted" and verdicts == {
        f"i{k}:{u}": "supported" for k in range(2) for u in range(2)
    }
    with pytest.raises(ValueError, match="no llm-judge record"):
        verdicts_from_run(again, "exact")


def test_judge_identity_is_part_of_the_run_id() -> None:
    a = run_with(ScriptedJudge(lambda req: "supported", model="m1"))
    b = run_with(ScriptedJudge(lambda req: "supported", model="m2"))
    assert a.run_id != b.run_id


# --------------------------------------------------------------------------- budget


def test_budget_stops_at_the_cap_and_counts_the_rest() -> None:
    judge = ScriptedJudge(lambda req: "supported", estimate_usd=0.01, cost_usd=0.01)
    r = run_with(judge, cap=0.05, n=4, sentences=2)  # 8 units, room for 5
    assert len(judge.calls) == 5 and judge.calls == ["i0:0", "i0:1", "i1:0", "i1:1", "i2:0"]
    rec = r.judges["j"]
    assert (rec.calls, rec.units_judged, rec.units_skipped_budget, rec.spent_usd, rec.cap_usd) == (
        5,
        5,
        3,
        0.05,
        0.05,
    )
    i2 = next(s for s in r.items[2].scores if s.key == "j")
    assert i2.labels == ["supported", None] and "1 not judged: budget cap reached" in i2.detail
    i3 = next(s for s in r.items[3].scores if s.key == "j")
    assert (i3.hits, i3.total) == (0, 0) and "2 not judged: budget cap reached" in i3.detail


def test_unknown_cost_is_charged_at_the_estimate() -> None:
    judge = ScriptedJudge(lambda req: "supported", estimate_usd=0.02, cost_usd=None)
    r = run_with(judge, cap=0.05, n=3, sentences=1)
    assert len(judge.calls) == 2 and r.judges["j"].spent_usd == 0.04


def test_a_call_over_its_estimate_stops_judging_and_is_flagged() -> None:
    judge = ScriptedJudge(lambda req: "supported", estimate_usd=0.01, cost_usd=0.03)
    r = run_with(judge, cap=1.0, n=3, sentences=2)
    assert len(judge.calls) == 1
    assert r.judges["j"].overrun and r.judges["j"].units_skipped_budget == 5


def test_zero_cap_allows_replay_and_refuses_paid_calls() -> None:
    free = ScriptedJudge(lambda req: "supported", estimate_usd=0.0, cost_usd=0.0)
    assert run_with(free, cap=0.0).judges["j"].units_judged == 6
    paid = ScriptedJudge(lambda req: "supported", estimate_usd=0.000001)
    r = run_with(paid, cap=0.0)
    assert paid.calls == [] and r.judges["j"].units_skipped_budget == 6


@pytest.mark.parametrize("cap", [-0.01, float("nan"), float("inf")])
def test_cap_must_be_finite_and_non_negative(cap: float) -> None:
    with pytest.raises(ValueError):
        Budget(cap)


@given(
    cap=st.floats(min_value=0, max_value=1, allow_nan=False),
    calls=st.lists(
        st.tuples(st.floats(min_value=0, max_value=0.3), st.floats(min_value=0, max_value=1)), max_size=40
    ),
)
def test_spend_never_exceeds_the_cap_when_estimates_hold(
    cap: float, calls: list[tuple[float, float]]
) -> None:
    b = Budget(cap)
    made = 0
    for estimate, frac in calls:
        if b.allows(estimate):
            b.charge(estimate, estimate * frac)  # actual <= estimate
            made += 1
        else:
            assert b.stopped
    assert b.spent_usd <= cap + 1e-9
    assert b.calls == made and not b.overrun


# --------------------------------------------------------------------------- recorded judge


def test_recorded_judge_replays_and_validates(tmp_path: Path) -> None:
    vf = VerdictFile(
        model="m", prompt_hash="h", source="s", labels=LABELS, verdicts={"i0:0": "partial", "i0:1": None}
    )
    judge = RecordedJudge(vf, "v.json")
    r = run_with(judge, n=2)
    j = [next(s for s in it.scores if s.key == "j") for it in r.items]
    assert j[0].labels == ["partial", None] and j[1].labels == [None, None]
    assert r.judges["j"].prompt_hash == "h" and r.judges["j"].spent_usd == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(vf.model_dump() | {"verdicts": {"i0:0": "maybe"}}), encoding="utf-8")
    with pytest.raises(JudgeError, match="maybe"):
        load_verdicts(bad)
    with pytest.raises(ValidationError, match="not '<item id>:<unit index>'"):
        VerdictFile(model="m", prompt_hash="h", source="s", labels=LABELS, verdicts={"x": "supported"})
    with pytest.raises(JudgeError, match="does not declare"):
        judge.identity("r", ["supported"])


# --------------------------------------------------------------------------- live client, fake transport


class FakeTransport:
    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def __call__(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
        self.calls.append((url, headers, json.loads(body)))
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return self.status, raw


def reply(text: str, tin: int = 1000, tout: int = 50) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": tin, "output_tokens": tout},
    }


REQ = JudgeRequest("i0", 0, "The rate is 70 cents.", {"q": "rate?"}, "Is it supported?", tuple(LABELS))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.delenv(KEY_ENV, raising=False)


def live(transport: FakeTransport, **kw: Any) -> AnthropicJudge:
    return AnthropicJudge(
        "claude-test",
        price_in_per_mtok=2.0,
        price_out_per_mtok=10.0,
        api_key="test-key",
        transport=transport,
        **kw,
    )


def test_live_client_request_cost_and_label() -> None:
    t = FakeTransport(body=reply('{"label": "partial", "reason": "year missing"}'))
    j = live(t)
    out = j.judge(REQ)
    assert out.label == "partial"
    assert out.cost_usd == pytest.approx(1000 * 2 / 1e6 + 50 * 10 / 1e6)
    url, headers, body = t.calls[0]
    assert url == API_URL and headers["x-api-key"] == "test-key" and headers["anthropic-version"]
    assert body["model"] == "claude-test" and body["max_tokens"] == 256
    assert "Is it supported?" in body["system"] and "The rate is 70 cents." in body["messages"][0]["content"]
    assert "test-key" not in repr(j)
    ident = j.identity("Is it supported?", LABELS)
    assert ident.prompt_hash == prompt_hash("Is it supported?", LABELS) and len(ident.prompt_hash) == 12
    assert prompt_hash("Other rubric", LABELS) != ident.prompt_hash


def test_live_estimate_is_an_upper_bound_on_the_reported_cost() -> None:
    j = live(FakeTransport(body=reply('{"label": "supported"}', tin=300, tout=256)))
    out = j.judge(REQ)
    assert out.cost_usd is not None and out.cost_usd <= j.estimate_usd(REQ)


@pytest.mark.parametrize(
    ("status", "body", "detail"),
    [
        (529, {"error": "overloaded"}, "HTTP 529"),
        (200, b"not json", "unreadable"),
        (200, {"content": []}, "unreadable"),
    ],
)
def test_live_client_failures_give_no_label_and_unknown_cost(status: int, body: Any, detail: str) -> None:
    out = live(FakeTransport(status, body)).judge(REQ)
    assert out.label is None and out.cost_usd is None and detail in out.detail


def test_live_client_unparseable_reply_is_invalid_but_costed() -> None:
    out = live(FakeTransport(body=reply("I think it is supported."))).judge(REQ)
    assert out.label is None and out.cost_usd is not None


def test_parse_label() -> None:
    assert parse_label('```json\n{"label": "supported"}\n```', LABELS) == "supported"
    assert parse_label('```{"label": "partial"}```', LABELS) == "partial"
    assert parse_label('{"label": "maybe"}', LABELS) is None
    assert parse_label("[1]", LABELS) is None


def test_live_client_needs_a_key_and_sane_prices() -> None:
    with pytest.raises(JudgeError, match=KEY_ENV):
        AnthropicJudge("m", price_in_per_mtok=1, price_out_per_mtok=1)
    with pytest.raises(JudgeError, match="price"):
        AnthropicJudge("m", price_in_per_mtok=-1, price_out_per_mtok=1, api_key="k")


def test_live_client_under_a_budget_through_the_runner() -> None:
    t = FakeTransport(body=reply('{"label": "supported"}', tin=100, tout=10))
    j = live(t)
    per_call = j.estimate_usd(JudgeRequest("i0", 0, "s0.0", {"q": 0}, OPTS["rubric"], tuple(LABELS)))
    r = run_with(j, cap=per_call * 1.01, n=2, sentences=2)
    # Before each call the worst case (the estimate) must fit; after it, the actual cost is charged. One call
    # fits; the second's worst case would not, though its actual cost would have: the cap is never risked.
    assert len(t.calls) == 1 and r.judges["j"].units_skipped_budget == 3
    assert r.judges["j"].spent_usd == pytest.approx(100 * 2 / 1e6 + 10 * 10 / 1e6)
