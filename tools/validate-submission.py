#!/usr/bin/env python3
"""Validate a pending submission folder under submissions/pending/."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REGISTRY_HOST = "https://xmintake.github.io/registry"
TAG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_category_ids(repo_root: Path) -> set[str]:
    path = repo_root / "catalog" / "categories.json"
    if not path.is_file():
        return set()
    doc = _load_json(path)
    categories = doc.get("categories")
    if not isinstance(categories, list):
        return set()
    return {str(item["id"]) for item in categories if isinstance(item, dict) and item.get("id")}


def _iter_schema_fields(schema: dict[str, Any]):
    fields = schema.get("fields")
    if isinstance(fields, dict):
        for name, cfg in fields.items():
            if isinstance(cfg, dict):
                yield name, cfg
    elif isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict):
                yield field.get("name") or field.get("label") or "field", field


def schema_has_attachments(schema: dict[str, Any]) -> bool:
    for _, field in _iter_schema_fields(schema):
        if str(field.get("type", "")).lower() == "attachment":
            return True
    return False


def validate_tags(tags: Any) -> list[str]:
    errors: list[str] = []
    if tags is None:
        return errors
    if not isinstance(tags, list):
        return ["tags must be an array"]
    if len(tags) > 5:
        errors.append("tags supports at most 5 entries")
    seen: set[str] = set()
    for tag in tags:
        slug = str(tag).strip().lower()
        if not TAG_PATTERN.match(slug):
            errors.append(f"invalid tag slug: {tag}")
        if slug in seen:
            errors.append(f"duplicate tag: {tag}")
        seen.add(slug)
    return errors


def validate_pending_dir(pending_dir: Path, *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    draft_path = pending_dir / "draft.destination.json"
    meta_path = pending_dir / "submission.meta.json"
    if not draft_path.is_file():
        errors.append("missing draft.destination.json")
        return errors
    if not meta_path.is_file():
        errors.append("missing submission.meta.json")
        return errors

    draft = _load_json(draft_path)
    meta = _load_json(meta_path)

    source = str(draft.get("source") or "")
    if not source.startswith(REGISTRY_HOST + "/destinations/"):
        errors.append("draft.source must be under registry destinations path")
    if source != str(meta.get("proposedSource") or ""):
        errors.append("submission.meta proposedSource must match draft.source")

    schema_path = pending_dir / "schema.json"
    sheet_mode = str(draft.get("sheetMode") or "SHARED").strip().upper()
    if sheet_mode not in ("SHARED", "TEMPLATE"):
        errors.append("sheetMode must be SHARED or TEMPLATE")

    if schema_path.is_file():
        schema = _load_json(schema_path)
        # SHARED destinations with attachments need a shared Drive folder.
        # TEMPLATE installs provision per-user storage, so attachmentPolicy must be omitted.
        if sheet_mode == "SHARED" and schema_has_attachments(schema) and not draft.get("attachmentPolicy"):
            errors.append("attachmentPolicy required when sheetMode is SHARED and schema has attachment fields")
        if sheet_mode == "TEMPLATE" and draft.get("attachmentPolicy") is not None:
            errors.append("attachmentPolicy must be omitted when sheetMode is TEMPLATE")

    visibility = draft.get("visibility") or "PUBLIC"
    if visibility not in ("PUBLIC", "UNLISTED"):
        errors.append("visibility must be PUBLIC or UNLISTED")

    errors.extend(validate_tags(draft.get("tags")))

    primary_category = draft.get("primaryCategory")
    if primary_category is not None:
        category_ids = _load_category_ids(repo_root)
        if category_ids and str(primary_category) not in category_ids:
            errors.append(f"unknown primaryCategory: {primary_category}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate registry pending submission")
    parser.add_argument("pending_dir", type=Path, help="Path to submissions/pending/{slug}/{id}")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = validate_pending_dir(args.pending_dir, repo_root=args.repo_root)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print(f"OK: {args.pending_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
