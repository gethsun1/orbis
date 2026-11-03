"""Stable input normalization and JSON serialization for persisted identities."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
HASH32 = re.compile(r"^0x[0-9a-fA-F]{64}$")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def normalize_parameters(parameters: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    schema = schema or {}
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(parameters) - set(properties)
        if extra:
            raise ValueError(f"unknown parameters: {', '.join(sorted(extra))}")
    result = {}
    for key, value in parameters.items():
        spec = properties.get(key, {})
        if value is None:
            result[key] = None
        elif spec.get("format") == "address":
            if not isinstance(value, str) or not ADDRESS.fullmatch(value): raise ValueError(f"invalid address parameter: {key}")
            result[key] = value.lower()
        elif spec.get("format") == "hash32":
            if not isinstance(value, str) or not HASH32.fullmatch(value): raise ValueError(f"invalid hash parameter: {key}")
            result[key] = value.lower()
        elif spec.get("type") == "integer" or isinstance(value, int) and not isinstance(value, bool):
            if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r"-?(0|[1-9][0-9]*)", str(value)):
                raise ValueError(f"invalid integer parameter: {key}")
            result[key] = str(int(value))
        elif spec.get("type") == "number" or isinstance(value, Decimal):
            try: n = Decimal(str(value))
            except Exception as exc: raise ValueError(f"invalid decimal parameter: {key}") from exc
            if not n.is_finite(): raise ValueError(f"invalid decimal parameter: {key}")
            result[key] = format(n.normalize(), "f")
        elif isinstance(value, list) and spec.get("x-collection") == "set":
            normalized = [normalize_scalar(v) for v in value]
            result[key] = sorted({canonical_json(v).decode(): v for v in normalized}.values(), key=lambda x: canonical_json(x))
        else:
            result[key] = normalize_scalar(value)
    for key, spec in properties.items():
        if key not in result and "default" in spec:
            result[key] = normalize_scalar(spec["default"])
    missing = set(schema.get("required", [])) - set(result)
    if missing: raise ValueError(f"missing parameters: {', '.join(sorted(missing))}")
    canonical_json(result)
    return result


def normalize_subject(kind: str, value: str) -> str:
    if kind == "address":
        if not isinstance(value, str) or not ADDRESS.fullmatch(value): raise ValueError("address subject must be a 20-byte hex address")
        return value.lower()
    if not isinstance(value, str) or not value: raise ValueError("subject key must be a non-empty string")
    return value


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)): return value
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError("non-finite number")
        return format(value.normalize(), "f")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")): raise ValueError("non-finite number")
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, list): return [normalize_scalar(v) for v in value]
    if isinstance(value, dict): return {str(k): normalize_scalar(v) for k, v in value.items()}
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")
