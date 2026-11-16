"""Live judge over the Anthropic Messages API (D-34).

Built and tested only against a fake transport: no live call and no API key in this repository's tests or
CI. Running it live is an owner step (README). Cost is computed from the reply's token usage and the
per-million-token prices the caller passes, never from a built-in price list, so a stale price cannot be
invented (YS-04).
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

from yardstick.hashing import canonical_json, content_hash
from yardstick.judge.base import JudgeError, JudgeIdentity, JudgeReply, JudgeRequest

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
KEY_ENV = "ANTHROPIC_API_KEY"

SYSTEM_TEMPLATE = (
    "You grade one unit of an AI system's output against a rubric. Grade only against the rubric and the "
    "material shown.\n\nRubric:\n{rubric}\n\nReply with JSON only, no prose and no code fence: "
    '{{"label": <one of {labels}>, "reason": "<one sentence>"}}'
)
#: Added to the byte count of the prompt for message framing, so the estimate stays an upper bound.
FRAMING_TOKENS = 64

#: (url, headers, body, timeout seconds) -> (HTTP status, response body)
Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def system_prompt(rubric: str, labels: Sequence[str]) -> str:
    return SYSTEM_TEMPLATE.format(rubric=rubric.strip(), labels=", ".join(json.dumps(x) for x in labels))


def prompt_hash(rubric: str, labels: Sequence[str]) -> str:
    """12 hex chars of the hash of the full system prompt (template + rubric + labels)."""
    return content_hash(system_prompt(rubric, labels)).removeprefix("sha256:")[:12]


def user_message(request: JudgeRequest) -> str:
    return f"Item input:\n{canonical_json(request.context)}\n\nUnit to grade:\n{request.unit_text}"


class AnthropicJudge:
    def __init__(
        self,
        model: str,
        *,
        price_in_per_mtok: float,
        price_out_per_mtok: float,
        max_tokens: int = 256,
        api_key: str | None = None,
        transport: Transport | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        for name, price in (("input", price_in_per_mtok), ("output", price_out_per_mtok)):
            if not math.isfinite(price) or price < 0:
                raise JudgeError(f"{name} price per million tokens must be a finite number >= 0")
        if max_tokens < 1:
            raise JudgeError("max_tokens must be >= 1")
        key = api_key if api_key is not None else os.environ.get(KEY_ENV)
        if not key:
            raise JudgeError(f"the live judge needs an API key in ${KEY_ENV}")
        self.model = model
        self.price_in = price_in_per_mtok
        self.price_out = price_out_per_mtok
        self.max_tokens = max_tokens
        self._key = key
        self._transport = transport or urllib_transport
        self._timeout = timeout_s

    def __repr__(self) -> str:  # never show the key
        return f"AnthropicJudge(model={self.model!r})"

    def identity(self, rubric: str, labels: Sequence[str]) -> JudgeIdentity:
        return JudgeIdentity(model=self.model, prompt_hash=prompt_hash(rubric, labels), source="anthropic")

    def _cost(self, tokens_in: int, tokens_out: int) -> float:
        return round(tokens_in * self.price_in / 1e6 + tokens_out * self.price_out / 1e6, 9)

    def estimate_usd(self, request: JudgeRequest) -> float:
        """Upper bound: one token per prompt byte plus framing, and ``max_tokens`` out."""
        size = len(system_prompt(request.rubric, request.labels).encode()) + len(
            user_message(request).encode()
        )
        return self._cost(size + FRAMING_TOKENS, self.max_tokens)

    def judge(self, request: JudgeRequest) -> JudgeReply:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system_prompt(request.rubric, request.labels),
                "messages": [{"role": "user", "content": user_message(request)}],
            }
        ).encode()
        headers = {
            "content-type": "application/json",
            "x-api-key": self._key,
            "anthropic-version": API_VERSION,
        }
        try:
            status, raw = self._transport(API_URL, headers, body, self._timeout)
        except (OSError, TimeoutError) as exc:
            return JudgeReply(None, None, f"transport error: {type(exc).__name__}")
        if status != 200:
            return JudgeReply(None, None, f"HTTP {status}")
        try:
            data = json.loads(raw)
            usage = data["usage"]
            cost = self._cost(int(usage["input_tokens"]), int(usage["output_tokens"]))
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (ValueError, KeyError, TypeError):
            return JudgeReply(None, None, "unreadable API response")
        return JudgeReply(parse_label(text, request.labels), cost)


def parse_label(text: str, labels: Sequence[str]) -> str | None:
    """The ``label`` of a JSON reply, after stripping one surrounding code fence; ``None`` if invalid."""
    t = text.strip()
    if t.startswith("```") and t.endswith("```") and len(t) > 6:
        t = t[3:-3]
        t = t.split("\n", 1)[1] if "\n" in t and not t.lstrip().startswith("{") else t
    try:
        data = json.loads(t)
    except ValueError:
        return None
    label = data.get("label") if isinstance(data, dict) else None
    return label if isinstance(label, str) and label in labels else None
