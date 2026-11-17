"""Post or update one pull-request comment with a Yardstick report (used by `action.yml`).

Stdlib only. The comment carries a hidden marker ``<!-- yardstick:<tag> -->``; a later run with the same tag
edits that comment instead of adding another. Outside a pull request (a push), nothing is posted. A token
without write access (a fork's pull request) gets a warning, not a failure: the job summary still holds the
report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_BODY = 65536  # GitHub's limit on an issue comment body, in characters
TRUNCATED_NOTE = "\n\n… report truncated to fit a GitHub comment; the full report is in the job summary.\n"
PER_PAGE = 100


def marker(tag: str) -> str:
    return f"<!-- yardstick:{tag} -->"


def build_body(report: str, tag: str) -> str:
    """The comment body: marker, then the report, cut to GitHub's limit with a note when needed."""
    head = marker(tag) + "\n"
    body = head + report
    if len(body) <= MAX_BODY:
        return body
    keep = MAX_BODY - len(head) - len(TRUNCATED_NOTE)
    return head + report[:keep] + TRUNCATED_NOTE


def pr_number(event_name: str | None, event_path: str | None) -> int | None:
    """The pull request number for pull_request / pull_request_target events, else None."""
    if event_name not in ("pull_request", "pull_request_target") or not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    number = event.get("pull_request", {}).get("number") if isinstance(event, dict) else None
    return number if isinstance(number, int) else None


@dataclass(frozen=True)
class Response:
    status: int
    body: Any


Transport = Callable[[str, str, Mapping[str, str], bytes | None], Response]


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def urllib_transport(method: str, url: str, headers: Mapping[str, str], data: bytes | None) -> Response:
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return Response(resp.status, json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raise HttpError(exc.code, exc.reason) from None


@dataclass
class Client:
    api_url: str
    repo: str
    token: str
    transport: Transport = urllib_transport

    def _call(self, method: str, path: str, payload: dict[str, str] | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "yardstick-action",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        resp = self.transport(method, f"{self.api_url.rstrip('/')}{path}", headers, data)
        if resp.status >= 400:
            raise HttpError(resp.status, "request failed")
        return resp.body

    def find_comment(self, number: int, tag: str) -> int | None:
        mark = marker(tag)
        page = 1
        while True:
            rows = self._call(
                "GET", f"/repos/{self.repo}/issues/{number}/comments?per_page={PER_PAGE}&page={page}"
            )
            if not isinstance(rows, list):
                return None
            for row in rows:
                if isinstance(row, dict) and mark in str(row.get("body", "")):
                    cid = row.get("id")
                    return cid if isinstance(cid, int) else None
            if len(rows) < PER_PAGE:
                return None
            page += 1

    def upsert(self, number: int, tag: str, report: str) -> str:
        body = build_body(report, tag)
        existing = self.find_comment(number, tag)
        if existing is None:
            self._call("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})
            return "created"
        self._call("PATCH", f"/repos/{self.repo}/issues/comments/{existing}", {"body": body})
        return "updated"


def post(report: str, tag: str, env: Mapping[str, str], transport: Transport = urllib_transport) -> str:
    """Post or update the comment. Returns what happened, as a one-line status."""
    number = pr_number(env.get("GITHUB_EVENT_NAME"), env.get("GITHUB_EVENT_PATH"))
    if number is None:
        return "skipped: not a pull request event"
    token = env.get("GITHUB_TOKEN", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return "skipped: GITHUB_TOKEN or GITHUB_REPOSITORY not set"
    client = Client(env.get("GITHUB_API_URL", "https://api.github.com"), repo, token, transport)
    try:
        action = client.upsert(number, tag, report)
    except HttpError as exc:
        if exc.status in (401, 403, 404):
            return f"warning: could not comment on #{number} ({exc}); the token may be read-only (fork PR)"
        raise
    return f"{action} comment on #{number}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Markdown report to post.")
    parser.add_argument("--tag", default="gate", help="Distinguishes several Yardstick comments on one PR.")
    args = parser.parse_args(argv)
    report = args.report.read_text(encoding="utf-8")
    try:
        status = post(report, args.tag, os.environ)
    except (HttpError, OSError) as exc:
        print(f"::warning::yardstick comment: {exc}", file=sys.stderr)
        return 0
    if status.startswith("warning"):
        print(f"::warning::yardstick comment: {status}", file=sys.stderr)
    else:
        print(f"yardstick comment: {status}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
