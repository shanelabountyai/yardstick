#!/usr/bin/env python3
"""Fake HTTP target for Yardstick tests and examples: the http twin of ``fake_target.py``.

Offline and deterministic. Standard library only. Listens on 127.0.0.1 only. For each
``POST /answer`` with a JSON body ``{"id": ..., "input": ...}`` it answers with the same canned row
``fake_target.py`` prints for that id (from ``fake_answers.json``)::

    {"id": "q1", "output": "...", "latency_ms": 412, "cost_usd": 0.000213}

  --port N                  port to listen on (default 8808; 0 picks a free one and prints it)
  --degrade                 use the degraded answer wherever one exists, so a regression gate trips
  --no-telemetry            omit latency_ms and cost_usd (YS-04: they must show as "not reported")
  --answers PATH            answers file (default: fake_answers.json next to this script)
  --require-token-env NAME  answer 401 unless the request has "Authorization: Bearer <value of $NAME>"
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
DEFAULT_PORT = 8808
PATH = "/answer"
MAX_REQUEST_BYTES = 1_048_576
DEFAULT_ANSWERS = Path(__file__).with_name("fake_answers.json")


def _fake_latency_ms(item_id: str, degraded: bool) -> int:
    base = 200 + int(hashlib.sha256(item_id.encode()).hexdigest()[:4], 16) % 600
    return base * 2 if degraded else base


def _fake_cost_usd(item_id: str) -> float:
    return round(0.0001 + (int(hashlib.sha256(item_id.encode()).hexdigest()[4:8], 16) % 900) / 1_000_000, 6)


def answer_row(
    answers: dict[str, dict[str, Any]], item_id: str, *, degrade: bool = False, telemetry: bool = True
) -> dict[str, Any]:
    """The row for one item: the same keys and values ``fake_target.py`` prints."""
    entry = answers.get(item_id)
    row: dict[str, Any] = {"id": item_id}
    if entry is None:
        row["error"] = "fake target has no answer for this item"
        return row
    use_degraded = degrade and "degraded" in entry
    row["output"] = entry["degraded"] if use_degraded else entry["healthy"]
    if telemetry:
        row["latency_ms"] = _fake_latency_ms(item_id, use_degraded)
        row["cost_usd"] = _fake_cost_usd(item_id)
    return row


def make_server(
    port: int = DEFAULT_PORT,
    *,
    answers_path: Path = DEFAULT_ANSWERS,
    degrade: bool = False,
    telemetry: bool = True,
    token: str | None = None,
) -> ThreadingHTTPServer:
    """A server bound to 127.0.0.1 (not yet serving). ``server.server_address[1]`` is the port in use."""
    answers: dict[str, dict[str, Any]] = json.loads(answers_path.read_text(encoding="utf-8"))

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, doc: dict[str, Any]) -> None:
            body = json.dumps(doc, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != PATH:
                return self._send(404, {"error": "not found"})
            if token is not None:
                given = self.headers.get("Authorization", "")
                if not hmac.compare_digest(given.encode("utf-8"), f"Bearer {token}".encode()):
                    return self._send(401, {"error": "unauthorized"})
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or int(length) > MAX_REQUEST_BYTES:
                return self._send(400, {"error": "bad Content-Length"})
            try:
                request = json.loads(self.rfile.read(int(length)).decode("utf-8"))
            except ValueError:
                return self._send(400, {"error": "body is not JSON"})
            item_id = request.get("id") if isinstance(request, dict) else None
            if not isinstance(item_id, str):
                return self._send(400, {"error": "body has no string 'id'"})
            return self._send(200, answer_row(answers, item_id, degrade=degrade, telemetry=telemetry))

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--degrade", action="store_true")
    p.add_argument("--no-telemetry", action="store_true")
    p.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    p.add_argument("--require-token-env", metavar="NAME")
    args = p.parse_args(argv)

    token: str | None = None
    if args.require_token_env:
        token = os.environ.get(args.require_token_env)
        if not token:
            p.error(f"environment variable {args.require_token_env} is not set")
    server = make_server(
        args.port,
        answers_path=args.answers,
        degrade=args.degrade,
        telemetry=not args.no_telemetry,
        token=token,
    )
    print(f"listening on http://{HOST}:{server.server_address[1]}{PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
