#!/usr/bin/env python3
"""Apply a DESTINATION deletion from deletions/pending/{slug}/{id}/."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_rel_from_url(schema_url: str) -> str | None:
    prefix = "https://xmintake.github.io/registry/"
    if schema_url.startswith(prefix):
        return schema_url[len(prefix) :]
    parsed = urlparse(schema_url)
    if parsed.path.startswith("/"):
        # Custom domain /registry/... is uncommon; keep host-relative paths under destinations/schemas only.
        path = parsed.path.lstrip("/")
        if path.startswith("schemas/") or path.startswith("destinations/"):
            return path
    return None


def delete_artifact(repo_root: Path, pending_rel: str) -> None:
    pending_dir = repo_root / pending_rel
    meta_path = pending_dir / "deletion.meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing deletion.meta.json in {pending_dir}")
    meta = _load_json(meta_path)
    if str(meta.get("kind") or "").upper() != "DESTINATION":
        raise ValueError("delete-artifact.py only handles kind=DESTINATION")

    publisher_slug = str(meta["publisherSlug"])
    destination_id = str(meta["destinationId"])
    dest_path = repo_root / "destinations" / publisher_slug / f"{destination_id}.destination.json"
    if dest_path.is_file():
        dest_path.unlink()

    schema_url = str(meta.get("schemaUrl") or "").strip()
    if schema_url:
        schema_rel = _schema_rel_from_url(schema_url)
        if schema_rel:
            schema_path = repo_root / schema_rel
            if schema_path.is_file():
                schema_path.unlink()
    else:
        default_schema = repo_root / "schemas" / publisher_slug / f"{destination_id}.schema.json"
        if default_schema.is_file():
            default_schema.unlink()

    submit_pending = repo_root / "submissions" / "pending" / publisher_slug / destination_id
    if submit_pending.is_dir():
        shutil.rmtree(submit_pending)

    if pending_dir.is_dir():
        shutil.rmtree(pending_dir)

    # Clean empty parent dirs under destinations/schemas/submissions when possible.
    for parent in (
        dest_path.parent,
        repo_root / "schemas" / publisher_slug,
        repo_root / "submissions" / "pending" / publisher_slug,
        pending_dir.parent,
    ):
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete registry destination artifact")
    parser.add_argument("pending_rel")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    delete_artifact(args.repo_root, args.pending_rel.strip("/"))
    subprocess.run(
        [sys.executable, str(args.repo_root / "tools" / "generate-catalog.py"), "--repo-root", str(args.repo_root)],
        check=True,
    )
    print(f"Deleted artifact from {args.pending_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
