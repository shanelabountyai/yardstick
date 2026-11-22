"""``http`` target: send one request per suite item and read the answer from the JSON response.

A target config (YAML, :class:`HttpTargetConfig`) says where and how::

    url: http://127.0.0.1:8808/answer   # http or https; no user:password@ part
    method: POST                        # POST (default) or PUT
    body: {id: $id, input: $input}      # default; a JSON template, see below
    headers:                            # header name -> environment variable NAME, never a literal value
      Authorization: {env: MY_API_TOKEN, scheme: Bearer}      # sends "Bearer <value of $MY_API_TOKEN>"
      X-Api-Version: {env: MY_API_VERSION, secret: false}
    response:                           # dotted paths into the JSON response (defaults: the command protocol)
      text: output
      refused: refused                  # a boolean path, or {path: status, values: [refused]}
      latency_ms: latency_ms
      cost_usd: cost_usd
      error: error
      fields: {citations: citations}
    timeout_s: 30                       # per request
    max_response_bytes: 1048576
    on_error: fail                      # fail (default) | record

**Body template.** Any JSON value. A string that is exactly ``$id``, ``$input`` or ``$input.<dotted path>`` is
replaced by that value, keeping its JSON type; ``$$x`` is the literal string ``$x``. Nothing is substituted
inside a longer string. All bodies are rendered before the first request is sent.

**Response.** The body must be JSON. ``text`` must be present unless the mapped ``error`` is non-null (which
marks the item as a target error, like the ``command`` protocol's ``error``). The optional values stay
``None`` ("not reported", YS-04) when their path is absent or null. Latency is recorded only if the endpoint
reports it: Yardstick does not measure it, because a measured value would differ between identical runs
(YS-01, D-65).

**Failures.** Connection failure, timeout, a non-2xx status (redirects are not followed), a body that is not
JSON, a missing ``text``, a wrongly typed value or a body over ``max_response_bytes`` fail the whole run
(:class:`AdapterError`, exit 2), like a crashed ``command`` target (D-14, D-62). With ``on_error: record`` the
item is recorded as an errored item instead and the run goes on. There are no retries. Requests go one at a
time, in suite order.

**Secrets.** Header values are read from the environment when the run starts. They are never stored on the
adapter's ``info``, and any occurrence of a secret value in a recorded text, field or error message is
replaced by ``[redacted:$NAME]``. The recorded target detail is the method and the URL without its query
string.
Proxies from the environment are not used.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from yardstick import __version__
from yardstick.adapters.base import AdapterError
from yardstick.adapters.results_file import MISSING, RefusedRule, get_path
from yardstick.hashing import canonical_json
from yardstick.models import Item, Output, TargetInfo

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576

# \Z, not $: "$" also matches before a trailing newline, which let "X-Foo\n" through (PRD-E).
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}\Z")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
#: Deepest nesting accepted in a response's mapped ``fields`` (deeper values could not be stored).
MAX_FIELD_DEPTH = 64
#: Headers the adapter (or the HTTP library) sets itself.
_RESERVED_HEADERS = frozenset({"content-type", "content-length", "host", "transfer-encoding", "connection"})
_URL_RULE = "url must be http(s)://host[:port]/path, with no spaces and no user:password@ part"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HeaderSource(_Model):
    """Where a request header's value comes from: an environment variable, by name."""

    env: str
    #: Optional auth scheme put before the value, e.g. ``Bearer`` -> ``Bearer <value>``.
    scheme: str | None = None
    #: Secret values are scrubbed from everything recorded. Set false for plain values such as a version.
    secret: bool = True

    @field_validator("env")
    @classmethod
    def _env_name(cls, v: str) -> str:
        if not _ENV_NAME.match(v):
            raise ValueError("env must be an environment variable name (letters, digits, underscore)")
        return v

    @field_validator("scheme")
    @classmethod
    def _scheme(cls, v: str | None) -> str | None:
        if v is not None and not _SCHEME.match(v):
            raise ValueError("scheme must be one short word such as Bearer")
        return v


class HttpResponseMapping(_Model):
    """Dotted paths into the JSON response. The defaults are the ``command`` protocol's key names."""

    text: str = "output"
    refused: str | RefusedRule | None = "refused"
    latency_ms: str | None = "latency_ms"
    cost_usd: str | None = "cost_usd"
    error: str | None = "error"
    fields: dict[str, str] = Field(default_factory=dict)


def _check_template(value: Any, where: str = "body") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(f"{where}: object keys must be strings")
            _check_template(v, f"{where}.{k}")
    elif isinstance(value, list):
        for n, v in enumerate(value):
            _check_template(v, f"{where}.{n}")
    elif isinstance(value, str):
        if value.startswith("$") and not (
            value.startswith("$$") or value in {"$id", "$input"} or value.startswith("$input.")
        ):
            raise ValueError(f"{where}: unknown placeholder (use $id, $input, $input.<path>, or $$ for a $)")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{where}: not a finite number")


class HttpTargetConfig(_Model):
    url: str
    method: Literal["POST", "PUT"] = "POST"
    body: Any = Field(default_factory=lambda: {"id": "$id", "input": "$input"})
    headers: dict[str, HeaderSource] = Field(default_factory=dict)
    response: HttpResponseMapping = Field(default_factory=HttpResponseMapping)
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    on_error: Literal["fail", "record"] = "fail"

    # Validation messages never repeat the offending value: a URL or header entry may hold a credential.

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not v.isascii() or any(ch.isspace() or ord(ch) < 0x21 or ord(ch) == 0x7F for ch in v):
            raise ValueError(_URL_RULE)
        try:
            parts = urlsplit(v)
            _ = parts.port
        except ValueError:
            raise ValueError(_URL_RULE) from None
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError(_URL_RULE)
        if parts.username is not None or parts.password is not None:
            raise ValueError(_URL_RULE)
        return v

    @field_validator("body")
    @classmethod
    def _body(cls, v: Any) -> Any:
        _check_template(v)
        return v

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, HeaderSource]) -> dict[str, HeaderSource]:
        seen: set[str] = set()
        for name in v:
            low = name.lower()
            if not _HEADER_NAME.match(name):
                raise ValueError("a header name has characters that are not allowed")
            if low in _RESERVED_HEADERS:
                raise ValueError(f"header {name} is set by Yardstick and cannot be configured")
            if low in seen:
                raise ValueError(f"header {name} is configured twice")
            seen.add(low)
        return v

    @field_validator("timeout_s")
    @classmethod
    def _timeout(cls, v: float) -> float:
        if not (math.isfinite(v) and v > 0):
            raise ValueError("timeout_s must be a positive number of seconds")
        return v

    @field_validator("max_response_bytes")
    @classmethod
    def _max_bytes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_response_bytes must be >= 1")
        return v


def safe_url(url: str) -> str:
    """The URL as it may be recorded: scheme, host, port and path, without the query string or fragment."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


def _validation_summary(exc: ValidationError) -> str:
    """Locations and messages only: pydantic's own text also prints the input values."""
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'config'}: {e['msg']}" for e in exc.errors())


def parse_http_config(data: Any, url: str | None = None) -> HttpTargetConfig:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AdapterError("bad http target config: the file must hold a mapping")
    if url is not None:
        data = {**data, "url": url}
    try:
        return HttpTargetConfig.model_validate(data)
    except ValidationError as exc:
        raise AdapterError(f"bad http target config: {_validation_summary(exc)}") from None


def load_http_config(path: Path, url: str | None = None) -> HttpTargetConfig:
    """Load a target config file. ``url`` replaces (or supplies) the file's ``url``."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterError(f"cannot read http target config {path}: {exc.strerror}") from exc
    except yaml.YAMLError:
        raise AdapterError(f"cannot parse http target config {path}: not valid YAML") from None
    try:
        return parse_http_config(data, url)
    except AdapterError as exc:
        raise AdapterError(f"{path}: {exc}") from None


class _RequestFailed(Exception):
    """One request did not give a usable response. The message is safe to record."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would resend the configured headers (credentials included) to another URL: never follow."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _render(template: Any, item: Item) -> Any:
    if isinstance(template, dict):
        return {k: _render(v, item) for k, v in template.items()}
    if isinstance(template, list):
        return [_render(v, item) for v in template]
    if not isinstance(template, str) or not template.startswith("$"):
        return template
    if template.startswith("$$"):
        return template[1:]
    if template == "$id":
        return item.id
    if template == "$input":
        return item.input
    value = get_path(item.input, template[len("$input.") :])
    if value is MISSING:
        raise AdapterError(f"http target: item {item.id!r}: the input has no value at {template[1:]!r}")
    return value


def _scrub(text: str, secrets: Mapping[str, str]) -> str:
    for value, name in secrets.items():
        text = text.replace(value, f"[redacted:${name}]")
    return text


def _scrub_any(value: Any, secrets: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _scrub(value, secrets)
    if isinstance(value, dict):
        return {_scrub(str(k), secrets): _scrub_any(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_any(v, secrets) for v in value]
    return value


def _depth(value: Any, limit: int = MAX_FIELD_DEPTH + 1) -> int:
    """Nesting depth of a JSON value, counted up to ``limit`` (iterative, so it cannot recurse too deep)."""
    deepest = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, d = stack.pop()
        deepest = max(deepest, d)
        if deepest >= limit:
            return deepest
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        stack.extend((c, d + 1) for c in children)
    return deepest


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _no_constants(name: str) -> Any:
    raise ValueError(name)


class HttpAdapter:
    def __init__(
        self,
        name: str,
        config: HttpTargetConfig,
        config_name: str = "custom",
        *,
        timeout_s: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if timeout_s is not None and not (math.isfinite(timeout_s) and timeout_s > 0):
            raise AdapterError("http target: the timeout must be a positive number of seconds")
        self.config = config
        self.timeout_s = config.timeout_s if timeout_s is None else timeout_s
        self._env = env
        self.info = TargetInfo(
            name=name, kind="http", detail=f"{config.method} {safe_url(config.url)} (config: {config_name})"
        )

    @classmethod
    def from_file(
        cls, name: str, path: Path, *, url: str | None = None, timeout_s: float | None = None
    ) -> HttpAdapter:
        return cls(name, load_http_config(path, url), path.name, timeout_s=timeout_s)

    # -- request -----------------------------------------------------------------------------------------

    def _headers(self) -> tuple[dict[str, str], dict[str, str]]:
        """Request headers, and ``{secret value: env var name}`` for scrubbing."""
        env = os.environ if self._env is None else self._env
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"yardstick/{__version__}",
        }
        secrets: dict[str, str] = {}
        for name, src in self.config.headers.items():
            value = env.get(src.env)
            if not value:
                raise AdapterError(f"http target: environment variable {src.env} (header {name}) is not set")
            try:
                value.encode("latin-1")
                sendable = "\r" not in value and "\n" not in value and value == value.strip()
            except UnicodeEncodeError:
                sendable = False
            if not sendable:
                raise AdapterError(
                    f"http target: environment variable {src.env} (header {name}) has characters that "
                    "cannot be sent in a header, or leading or trailing whitespace"
                )
            headers[name] = value if src.scheme is None else f"{src.scheme} {value}"
            if src.secret:
                secrets[value] = src.env
        return headers, secrets

    def _body(self, item: Item) -> bytes:
        try:
            return canonical_json(_render(self.config.body, item)).encode("utf-8")
        except ValueError:
            raise AdapterError(
                f"http target: item {item.id!r}: the request body has a non-finite number"
            ) from None

    def _fetch(self, opener: urllib.request.OpenerDirector, body: bytes, headers: Mapping[str, str]) -> bytes:
        cfg = self.config
        timed_out = f"timed out after {self.timeout_s:g}s"
        req = urllib.request.Request(cfg.url, data=body, method=cfg.method, headers=dict(headers))
        deadline = time.monotonic() + self.timeout_s
        try:
            with opener.open(req, timeout=self.timeout_s) as resp:
                declared = resp.headers.get("Content-Length")
                too_big = f"response larger than {cfg.max_response_bytes} bytes"
                valid = declared is not None and declared.isascii() and declared.isdigit()
                if valid and int(declared) > cfg.max_response_bytes:
                    raise _RequestFailed(too_big)
                chunks: list[bytes] = []
                total = 0
                while True:
                    # The socket timeout only bounds each read; this bounds the whole request (a slow drip).
                    if time.monotonic() > deadline:
                        raise _RequestFailed(timed_out)
                    chunk: bytes = resp.read1(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > cfg.max_response_bytes:
                        raise _RequestFailed(too_big)
                    chunks.append(chunk)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            exc.close()
            note = " (redirects are not followed)" if 300 <= exc.code < 400 else ""
            raise _RequestFailed(f"HTTP {exc.code}{note}") from None
        except TimeoutError:
            raise _RequestFailed(timed_out) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise _RequestFailed(timed_out) from None
            kind = type(exc.reason).__name__ if isinstance(exc.reason, BaseException) else "URLError"
            raise _RequestFailed(f"connection failed ({kind})") from None
        except (http.client.HTTPException, OSError) as exc:
            raise _RequestFailed(f"connection failed ({type(exc).__name__})") from None

    # -- response ----------------------------------------------------------------------------------------

    def _output(self, raw: bytes) -> Output:
        m = self.config.response
        try:
            doc = json.loads(raw.decode("utf-8"), parse_constant=_no_constants)
        except UnicodeDecodeError:
            raise _RequestFailed("response is not JSON: not UTF-8") from None
        except json.JSONDecodeError as exc:
            raise _RequestFailed(f"response is not JSON: {exc.msg}") from None
        except (ValueError, RecursionError):
            raise _RequestFailed("response is not JSON: non-finite number or nesting too deep") from None

        def opt(path: str | None) -> Any:
            if path is None:
                return None
            v = get_path(doc, path)
            return None if v is MISSING else v

        try:
            err = opt(m.error)
            text_v = opt(m.text)
            if text_v is None and err is None:
                raise _RequestFailed(f"response has no value at {m.text!r}")
            text = "" if text_v is None else (text_v if isinstance(text_v, str) else canonical_json(text_v))
            refused: bool | None = None
            if isinstance(m.refused, RefusedRule):
                rv = get_path(doc, m.refused.path)
                refused = None if rv is MISSING else rv in m.refused.values
            elif m.refused is not None:
                refused = opt(m.refused)
                if refused is not None and not isinstance(refused, bool):
                    raise _RequestFailed(f"response value at {m.refused!r} is not a boolean")
            latency = opt(m.latency_ms)
            if latency is not None and (isinstance(latency, bool) or not isinstance(latency, int)):
                raise _RequestFailed(f"response value at {m.latency_ms!r} is not an integer")
            cost = opt(m.cost_usd)
            if cost is not None and not _number(cost):
                raise _RequestFailed(f"response value at {m.cost_usd!r} is not a number")
            fields = {name: v for name, path in sorted(m.fields.items()) if (v := opt(path)) is not None}
            if _depth(fields) > MAX_FIELD_DEPTH:
                raise _RequestFailed(f"response fields nested deeper than {MAX_FIELD_DEPTH} levels")
            canonical_json(fields)  # rejects non-finite numbers now, not when the run is written
            return Output(
                text=text,
                refused=refused,
                latency_ms=latency,
                cost_usd=None if cost is None else float(cost),
                error=None if err is None else (err if isinstance(err, str) else canonical_json(err)),
                fields=fields,
            )
        except ValidationError as exc:
            raise _RequestFailed(f"bad response value: {exc.errors()[0]['msg']}") from None
        except ValueError:
            raise _RequestFailed("response has a non-finite number") from None
        except RecursionError:
            raise _RequestFailed("response is nested too deeply") from None

    # -- adapter -----------------------------------------------------------------------------------------

    def produce(self, items: Sequence[Item]) -> dict[str, Output]:
        headers, secrets = self._headers()
        bodies = [(item, self._body(item)) for item in items]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
        outputs: dict[str, Output] = {}
        for item, body in bodies:
            try:
                out = self._output(self._fetch(opener, body, headers))
            except _RequestFailed as exc:
                reason = _scrub(str(exc), secrets)
                if self.config.on_error != "record":
                    raise AdapterError(f"http target: item {item.id!r}: {reason}") from None
                out = Output(error=reason)
            if secrets:
                out = out.model_copy(
                    update={
                        "text": _scrub(out.text, secrets),
                        "error": None if out.error is None else _scrub(out.error, secrets),
                        "fields": _scrub_any(out.fields, secrets),
                    }
                )
            outputs[item.id] = out
        return outputs
