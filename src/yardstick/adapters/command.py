"""``command`` target: run a local program once per suite.

Protocol: Yardstick writes one JSON object per line to the program's stdin, ``{"id": ..., "input": ...}``,
and reads one JSON object per line from its stdout:

    {"id": "q1", "output": "text or any JSON value",
     "refused": false, "latency_ms": 412, "cost_usd": 0.000213, "error": null}

Only ``id`` and ``output`` (or ``error``) are required. Missing telemetry stays ``None`` ("not reported").
The program is executed without a shell. Its environment is inherited; nothing from it is recorded.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from yardstick.adapters.base import AdapterError
from yardstick.hashing import canonical_json
from yardstick.models import Item, Output, TargetInfo


class CommandAdapter:
    def __init__(self, name: str, argv: Sequence[str], timeout_s: float = 300.0) -> None:
        if not argv:
            raise AdapterError("command target needs a non-empty command")
        self.argv = list(argv)
        self.timeout_s = timeout_s
        self.info = TargetInfo(name=name, kind="command", detail=shlex.join(self.argv))

    @classmethod
    def from_string(cls, name: str, command: str, timeout_s: float = 300.0) -> CommandAdapter:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise AdapterError(f"cannot parse --cmd: {exc}") from None
        return cls(name, argv, timeout_s)

    def produce(self, items: Sequence[Item]) -> dict[str, Output]:
        stdin = "".join(canonical_json({"id": i.id, "input": i.input}) + "\n" for i in items)
        try:
            proc = subprocess.run(
                self.argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdapterError(f"command not found: {self.argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"command timed out after {self.timeout_s:g}s") from exc
        except OSError as exc:
            raise AdapterError(f"cannot run command {self.argv[0]}: {exc.strerror or exc}") from exc
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()[-5:]
            raise AdapterError(f"command exited {proc.returncode}: {' | '.join(tail)}")
        return self._parse(proc.stdout, {i.id for i in items})

    @staticmethod
    def _parse(stdout: str, wanted: set[str]) -> dict[str, Output]:
        outputs: dict[str, Output] = {}
        for lineno, line in enumerate(stdout.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AdapterError(f"stdout line {lineno} is not JSON: {exc.msg}") from exc
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise AdapterError(f"stdout line {lineno} has no string 'id'")
            item_id: str = row["id"]
            if item_id not in wanted:
                raise AdapterError(f"stdout line {lineno}: unknown item id {item_id!r}")
            if item_id in outputs:
                raise AdapterError(f"stdout line {lineno}: duplicate output for {item_id!r}")
            raw = row.get("output", "")
            text = raw if isinstance(raw, str) else canonical_json(raw)
            try:
                outputs[item_id] = Output(
                    text=text,
                    refused=row.get("refused"),
                    latency_ms=row.get("latency_ms"),
                    cost_usd=row.get("cost_usd"),
                    error=row.get("error"),
                )
            except ValidationError as exc:
                raise AdapterError(f"stdout line {lineno}: bad output row: {exc.errors()[0]['msg']}") from exc
        return outputs
