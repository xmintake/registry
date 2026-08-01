#!/usr/bin/env python3
"""Validate a pending deletion manifest under deletions/pending/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_deletion_dir(pending_dir: Path, *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    meta_path = pending_dir / "deletion.meta.json"
    if not meta_path.is_file():
        return ["missing deletion.meta.json"]

    try:
        meta = _load_json(meta_path)
    except json.JSONDecodeError as exc:
        return [f"invalid deletion.meta.json: {exc}"]

    kind = str(meta.get("kind") or "").strip().upper()
    publisher_slug = str(meta.get("publisherSlug") or "").strip()
    if not publisher_slug:
        errors.append("publisherSlug is required")

    rel = pending_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    if kind == "DESTINATION":
        destination_id = str(meta.get("destinationId") or "").strip()
        if not destination_id:
            errors.append("destinationId is required for DESTINATION deletions")
        expected = f"deletions/pending/{publisher_slug}/{destination_id}"
        if publisher_slug and destination_id and rel != expected:
            errors.append(f"path mismatch: expected {expected}, got {rel}")
        proposed = str(meta.get("proposedSource") or "")
        if publisher_slug and destination_id:
            needle = f"/destinations/{publisher_slug}/{destination_id}.destination.json"
            if needle not in proposed:
                errors.append("proposedSource must include publisher/destination path")
        dest_file = repo_root / "destinations" / publisher_slug / f"{destination_id}.destination.json"
        if publisher_slug and destination_id and not dest_file.is_file():
            errors.append(f"destination not on main: {dest_file.relative_to(repo_root)}")
    elif kind == "PUBLISHER":
        expected = f"deletions/pending/_publisher/{publisher_slug}"
        if publisher_slug and rel != expected:
            errors.append(f"path mismatch: expected {expected}, got {rel}")
        publisher_file = repo_root / "publishers" / f"{publisher_slug}.publisher.json"
        if publisher_slug and not publisher_file.is_file():
            errors.append(f"publisher file missing: {publisher_file.relative_to(repo_root)}")
        if "cascadeDeleteArtifacts" not in meta:
            errors.append("cascadeDeleteArtifacts is required for PUBLISHER deletions")
    else:
        errors.append(f"unsupported kind: {kind or '(empty)'}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pending registry deletion")
    parser.add_argument("pending_rel", help="Relative path under repo root")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    pending_dir = args.repo_root / args.pending_rel.strip("/")
    errors = validate_deletion_dir(pending_dir, repo_root=args.repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.pending_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
