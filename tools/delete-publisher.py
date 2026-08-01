#!/usr/bin/env python3
"""Apply a PUBLISHER deletion from deletions/pending/_publisher/{slug}/."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def delete_publisher(repo_root: Path, pending_rel: str) -> None:
    pending_dir = repo_root / pending_rel
    meta_path = pending_dir / "deletion.meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing deletion.meta.json in {pending_dir}")
    meta = _load_json(meta_path)
    if str(meta.get("kind") or "").upper() != "PUBLISHER":
        raise ValueError("delete-publisher.py only handles kind=PUBLISHER")

    publisher_slug = str(meta["publisherSlug"])
    cascade = bool(meta.get("cascadeDeleteArtifacts"))

    if cascade:
        for folder in (
            repo_root / "destinations" / publisher_slug,
            repo_root / "schemas" / publisher_slug,
            repo_root / "submissions" / "pending" / publisher_slug,
            repo_root / "deletions" / "pending" / publisher_slug,
        ):
            if folder.is_dir():
                shutil.rmtree(folder)

    publisher_file = repo_root / "publishers" / f"{publisher_slug}.publisher.json"
    if publisher_file.is_file():
        publisher_file.unlink()

    if pending_dir.is_dir():
        shutil.rmtree(pending_dir)

    parent = pending_dir.parent
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete registry publisher")
    parser.add_argument("pending_rel")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    delete_publisher(args.repo_root, args.pending_rel.strip("/"))
    subprocess.run(
        [sys.executable, str(args.repo_root / "tools" / "generate-catalog.py"), "--repo-root", str(args.repo_root)],
        check=True,
    )
    print(f"Deleted publisher from {args.pending_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
