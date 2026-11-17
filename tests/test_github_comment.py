"""The PR comment poster used by action.yml: one comment per tag, created once and then updated."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from yardstick import github_comment as gc


class FakeGitHub:
    """An in-memory issue-comment API. Records every request."""

    def __init__(self, comments: list[dict[str, Any]] | None = None, fail_status: int | None = None) -> None:
        self.comments = comments or []
        self.calls: list[tuple[str, str, dict[str, str], Any]] = []
        self.fail_status = fail_status
        self.next_id = 1000

    def __call__(self, method: str, url: str, headers: Mapping[str, str], data: bytes | None) -> gc.Response:
        payload: dict[str, Any] = json.loads(data) if data else {}
        self.calls.append((method, url, dict(headers), payload))
        if self.fail_status is not None:
            raise gc.HttpError(self.fail_status, "denied")
        if method == "GET":
            page = int(url.split("page=")[-1])
            start = (page - 1) * gc.PER_PAGE
            return gc.Response(200, self.comments[start : start + gc.PER_PAGE])
        if method == "POST":
            self.next_id += 1
            row = {"id": self.next_id, "body": payload["body"]}
            self.comments.append(row)
            return gc.Response(201, row)
        if method == "PATCH":
            cid = int(url.rsplit("/", 1)[-1])
            for row in self.comments:
                if row["id"] == cid:
                    row["body"] = payload["body"]
                    return gc.Response(200, row)
            return gc.Response(404, None)
        raise AssertionError(method)


def _env(tmp_path: Path, event: str = "pull_request", number: int = 7) -> dict[str, str]:
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"pull_request": {"number": number}}), encoding="utf-8")
    return {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_EVENT_PATH": str(path),
        "GITHUB_TOKEN": "t0ken-value",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_API_URL": "https://api.example.test",
    }


def test_creates_a_comment_when_none_has_the_marker(tmp_path: Path) -> None:
    gh = FakeGitHub([{"id": 1, "body": "an unrelated comment"}])
    status = gc.post("# Report\n", "gate", _env(tmp_path), gh)
    assert status == "created comment on #7"
    assert len(gh.comments) == 2
    assert gh.comments[-1]["body"] == "<!-- yardstick:gate -->\n# Report\n"
    assert gh.calls[-1][1] == "https://api.example.test/repos/owner/repo/issues/7/comments"


def test_updates_the_comment_with_the_same_tag_only(tmp_path: Path) -> None:
    gh = FakeGitHub(
        [
            {"id": 1, "body": "<!-- yardstick:judge -->\nold judge report"},
            {"id": 2, "body": "<!-- yardstick:gate -->\nold gate report"},
        ]
    )
    status = gc.post("new gate report", "gate", _env(tmp_path), gh)
    assert status == "updated comment on #7"
    assert [c["body"] for c in gh.comments] == [
        "<!-- yardstick:judge -->\nold judge report",
        "<!-- yardstick:gate -->\nnew gate report",
    ]
    assert gh.calls[-1][0] == "PATCH"
    assert gh.calls[-1][1].endswith("/repos/owner/repo/issues/comments/2")


def test_running_twice_leaves_one_comment(tmp_path: Path) -> None:
    gh = FakeGitHub()
    gc.post("first", "gate", _env(tmp_path), gh)
    gc.post("second", "gate", _env(tmp_path), gh)
    assert [c["body"] for c in gh.comments] == ["<!-- yardstick:gate -->\nsecond"]


def test_finds_the_marker_past_the_first_page(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = [{"id": i, "body": f"c{i}"} for i in range(gc.PER_PAGE)]
    rows.append({"id": 9999, "body": "<!-- yardstick:gate -->\nold"})
    gh = FakeGitHub(rows)
    assert gc.post("new", "gate", _env(tmp_path), gh) == "updated comment on #7"
    assert [c[1].split("page=")[-1] for c in gh.calls if c[0] == "GET"] == ["1", "2"]


def test_skips_outside_a_pull_request(tmp_path: Path) -> None:
    gh = FakeGitHub()
    assert gc.post("r", "gate", _env(tmp_path, event="push"), gh) == "skipped: not a pull request event"
    assert gh.calls == []


def test_skips_without_token(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["GITHUB_TOKEN"] = ""
    gh = FakeGitHub()
    assert gc.post("r", "gate", env, gh).startswith("skipped")
    assert gh.calls == []


@pytest.mark.parametrize("status", [401, 403, 404])
def test_read_only_token_is_a_warning_not_a_failure(tmp_path: Path, status: int) -> None:
    gh = FakeGitHub(fail_status=status)
    assert gc.post("r", "gate", _env(tmp_path), gh).startswith("warning: could not comment on #7")


def test_other_http_errors_propagate(tmp_path: Path) -> None:
    gh = FakeGitHub(fail_status=500)
    with pytest.raises(gc.HttpError):
        gc.post("r", "gate", _env(tmp_path), gh)


def test_token_goes_in_a_header_only(tmp_path: Path) -> None:
    gh = FakeGitHub()
    gc.post("r", "gate", _env(tmp_path), gh)
    for _method, url, headers, payload in gh.calls:
        assert headers["Authorization"] == "Bearer t0ken-value"
        assert "t0ken-value" not in url
        assert "t0ken-value" not in json.dumps(payload)


def test_long_reports_are_truncated_to_the_limit() -> None:
    body = gc.build_body("x" * (gc.MAX_BODY * 2), "gate")
    assert len(body) == gc.MAX_BODY
    assert body.startswith("<!-- yardstick:gate -->\n")
    assert body.endswith(gc.TRUNCATED_NOTE)
    short = gc.build_body("short", "gate")
    assert short == "<!-- yardstick:gate -->\nshort"


def test_pr_number_reads_the_event(tmp_path: Path) -> None:
    env = _env(tmp_path, number=42)
    assert gc.pr_number("pull_request", env["GITHUB_EVENT_PATH"]) == 42
    assert gc.pr_number("pull_request_target", env["GITHUB_EVENT_PATH"]) == 42
    assert gc.pr_number("push", env["GITHUB_EVENT_PATH"]) is None
    assert gc.pr_number("pull_request", str(tmp_path / "missing.json")) is None
    assert gc.pr_number("pull_request", None) is None


def test_main_never_fails_the_job_on_comment_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text("# r\n", encoding="utf-8")
    for key, value in _env(tmp_path).items():
        monkeypatch.setenv(key, value)

    def boom(
        report: str, tag: str, env: Mapping[str, str], transport: gc.Transport = gc.urllib_transport
    ) -> str:
        raise gc.HttpError(500, "server error")

    monkeypatch.setattr(gc, "post", boom)
    assert gc.main(["--report", str(report), "--tag", "gate"]) == 0
    assert "::warning::" in capsys.readouterr().err
