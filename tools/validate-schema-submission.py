#!/usr/bin/env python3
"""Validate a pending schema-only submission under submissions/pending-schemas/."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REGISTRY_HOST = "https://xmintake.github.io/registry"
SCHEMA_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pending_dir(pending_dir: Path) -> list[str]:
    errors: list[str] = []
    draft_path = pending_dir / "draft.schema.json"
    meta_path = pending_dir / "submission.meta.json"
    if not draft_path.is_file():
        errors.append("missing draft.schema.json")
        return errors
    if not meta_path.is_file():
        errors.append("missing submission.meta.json")
        return errors

    draft = _load_json(draft_path)
    meta = _load_json(meta_path)

    schema_url = str(meta.get("proposedSchemaUrl") or "")
    if not schema_url.startswith(REGISTRY_HOST + "/schemas/"):
        errors.append("proposedSchemaUrl must be under registry schemas path")

    schema_id = str(meta.get("schemaId") or "")
    publisher_slug = str(meta.get("publisherSlug") or "")
    if not SCHEMA_ID_PATTERN.match(schema_id):
        errors.append(f"invalid schemaId: {schema_id}")
    if not publisher_slug:
        errors.append("missing publisherSlug")

    fields = draft.get("fields")
    if not isinstance(fields, dict) or len(fields) == 0:
        errors.append("draft.schema.json must include non-empty fields")

    expected = f"{publisher_slug}.{schema_id}" if publisher_slug and schema_id else ""
    actual = str(draft.get("schemaId") or "").strip()
    if expected and actual and actual != expected:
        errors.append(f"schemaId mismatch: expected {expected}, got {actual}")

    if schema_url.endswith(".schema.json") and publisher_slug and schema_id:
        expected_suffix = f"/schemas/{publisher_slug}/{schema_id}.schema.json"
        if not schema_url.endswith(expected_suffix):
            errors.append("proposedSchemaUrl path must match publisherSlug/schemaId")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate registry pending schema submission")
    parser.add_argument(
        "pending_dir",
        type=Path,
        help="Path to submissions/pending-schemas/{slug}/{id}",
    )
    args = parser.parse_args()
    errors = validate_pending_dir(args.pending_dir)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print(f"OK: {args.pending_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
