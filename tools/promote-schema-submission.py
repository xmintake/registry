#!/usr/bin/env python3
"""
Promote a pending schema-only submission to schemas/ and refresh catalog.

Expects:
  submissions/pending-schemas/{publisherSlug}/{schemaId}/draft.schema.json
  submissions/pending-schemas/{publisherSlug}/{schemaId}/submission.meta.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REGISTRY_HOST = "https://xmintake.github.io/registry"


def promote(repo_root: Path, pending_rel: str) -> None:
    pending_dir = repo_root / pending_rel
    draft_path = pending_dir / "draft.schema.json"
    meta_path = pending_dir / "submission.meta.json"
    if not draft_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"Pending schema submission incomplete: {pending_dir}")

    draft: dict[str, Any] = json.loads(draft_path.read_text(encoding="utf-8"))
    meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    publisher_slug = str(meta.get("publisherSlug") or "")
    schema_id = str(meta.get("schemaId") or "")
    schema_url = str(meta.get("proposedSchemaUrl") or "")

    prefix = REGISTRY_HOST + "/"
    if schema_url.startswith(prefix):
        schema_rel = schema_url[len(prefix) :]
    else:
        if not publisher_slug or not schema_id:
            raise ValueError("Missing publisherSlug/schemaId in submission.meta.json")
        schema_rel = f"schemas/{publisher_slug}/{schema_id}.schema.json"

    if publisher_slug and schema_id:
        draft["schemaId"] = f"{publisher_slug}.{schema_id}"
        draft["$schema"] = f"{REGISTRY_HOST}/meta/xmintake-schema.v1.json"

    schema_out = repo_root / schema_rel
    schema_out.parent.mkdir(parents=True, exist_ok=True)
    schema_out.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    shutil.rmtree(pending_dir)

    subprocess.run(
        [sys.executable, str(repo_root / "tools" / "generate-catalog.py"), "--repo-root", str(repo_root)],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote pending schema-only registry submission")
    parser.add_argument(
        "pending_rel",
        help="Relative path, e.g. submissions/pending-schemas/acme/item-list",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    promote(args.repo_root, args.pending_rel)
    print(f"Promoted {args.pending_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
