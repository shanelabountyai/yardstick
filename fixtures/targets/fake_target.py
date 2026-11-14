#!/usr/bin/env python3
"""Fake command target for Yardstick tests and examples. Offline and deterministic.

Reads ``{"id", "input"}`` JSON lines on stdin and prints canned outputs from ``fake_answers.json``.

  --degrade        use the degraded answer wherever one exists (wrong totals, missing fields,
                   ungrounded citations, failed refusals) so a regression gate trips
  --no-telemetry   omit latency_ms and cost_usd (YS-04: they must show as "not reported")
  --answers PATH   answers file (default: fake_answers.json next to this script)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _fake_latency_ms(item_id: str, degraded: bool) -> int:
    base = 200 + int(hashlib.sha256(item_id.encode()).hexdigest()[:4], 16) % 600
    return base * 2 if degraded else base


def _fake_cost_usd(item_id: str) -> float:
    return round(0.0001 + (int(hashlib.sha256(item_id.encode()).hexdigest()[4:8], 16) % 900) / 1_000_000, 6)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--degrade", action="store_true")
    p.add_argument("--no-telemetry", action="store_true")
    p.add_argument("--answers", type=Path, default=Path(__file__).with_name("fake_answers.json"))
    args = p.parse_args(argv)

    answers: dict[str, dict[str, Any]] = json.loads(args.answers.read_text(encoding="utf-8"))
    for line in sys.stdin:
        if not line.strip():
            continue
        item_id = json.loads(line)["id"]
        entry = answers.get(item_id)
        row: dict[str, Any] = {"id": item_id}
        if entry is None:
            row["error"] = "fake target has no answer for this item"
        else:
            use_degraded = args.degrade and "degraded" in entry
            row["output"] = entry["degraded"] if use_degraded else entry["healthy"]
            if not args.no_telemetry:
                row["latency_ms"] = _fake_latency_ms(item_id, use_degraded)
                row["cost_usd"] = _fake_cost_usd(item_id)
        sys.stdout.write(json.dumps(row, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
