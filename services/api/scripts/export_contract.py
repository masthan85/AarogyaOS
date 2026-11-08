"""Writes the response fields of every JSON endpoint to apps/mobile/src/api/contract.json.

The mobile app's jest suite checks its zod schemas against this file, and tests/test_contract.py
checks the file is current, so a renamed or removed response field fails a build instead of
failing on a phone. Regenerate after changing a response model:

    PYTHONPATH=. python scripts/export_contract.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("AAROGYA_ENVIRONMENT", "test")

from app.main import create_app  # noqa: E402

TARGET = Path(__file__).resolve().parents[3] / "apps/mobile/src/api/contract.json"
PREFIX = "/api/v1"


def _resolve(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return _resolve(spec, spec["components"]["schemas"][name])
    return node


def _fields(spec: dict[str, Any], node: dict[str, Any]) -> list[str] | None:
    node = _resolve(spec, node)
    if node.get("type") == "array" and "items" in node:
        return _fields(spec, node["items"])
    for key in ("anyOf", "oneOf"):
        if key in node:  # optional or union response: take the object member, if exactly one
            objs = [_resolve(spec, n) for n in node[key] if _resolve(spec, n).get("type") != "null"]
            return _fields(spec, objs[0]) if len(objs) == 1 else None
    props = node.get("properties")
    return sorted(props) if props else None


def build() -> dict[str, list[str]]:
    spec = create_app().openapi()
    out: dict[str, list[str]] = {}
    for path, methods in spec["paths"].items():
        if not path.startswith(PREFIX):
            continue
        for method, op in methods.items():
            for code in ("200", "201"):
                body = op.get("responses", {}).get(code, {}).get("content", {})
                schema = body.get("application/json", {}).get("schema")
                if schema is None:
                    continue
                fields = _fields(spec, schema)
                if fields is not None:
                    out[f"{method.upper()} {path[len(PREFIX) :]}"] = fields
                break
    return dict(sorted(out.items()))


if __name__ == "__main__":
    TARGET.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"Wrote {len(json.loads(TARGET.read_text()))} endpoints to {TARGET}")
    sys.exit(0)
