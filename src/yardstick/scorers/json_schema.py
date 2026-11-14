from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from yardstick.models import Output
from yardstick.scorers.base import Outcome, ScorerConfigError, unknown_options


class JsonSchema:
    """Output parses as JSON and validates against the expected JSON Schema (Draft 2020-12)."""

    name = "json-schema"

    def __call__(self, expected: Any, output: Output, options: dict[str, Any]) -> Outcome:
        unknown_options(options, set(), self.name)
        if not isinstance(expected, dict):
            raise ScorerConfigError("json-schema: expected must be a JSON Schema object")
        try:
            Draft202012Validator.check_schema(expected)
        except SchemaError as exc:
            raise ScorerConfigError(f"json-schema: invalid schema: {exc.message}") from exc
        try:
            value = json.loads(output.text)
        except json.JSONDecodeError as exc:
            return Outcome.binary(False, f"output is not JSON: {exc.msg}")
        errors = sorted(Draft202012Validator(expected).iter_errors(value), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "(root)"
            return Outcome.binary(False, f"{len(errors)} schema error(s); first at {where}: {first.message}")
        return Outcome.binary(True)
