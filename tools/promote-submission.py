#!/usr/bin/env python3
"""
Promote a pending submission to signed destinations/ (+ optional schemas/).

Used by GitHub Actions on merge. Expects:
  submissions/pending/{publisherSlug}/{destinationId}/draft.destination.json
  submissions/pending/{publisherSlug}/{destinationId}/submission.meta.json
  optional schema.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_expiry(issued: str) -> str:
    issued_dt = datetime.fromisoformat(issued.replace("Z", "+00:00"))
    return (issued_dt + timedelta(days=365)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_publisher(repo_root: Path, slug: str) -> dict[str, Any]:
    path = repo_root / "publishers" / f"{slug}.publisher.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _destination_rel_path(source_url: str) -> str:
    prefix = "https://xmintake.github.io/registry/"
    if not source_url.startswith(prefix):
        raise ValueError(f"Unsupported source URL: {source_url}")
    return source_url[len(prefix) :]


def promote(repo_root: Path, pending_rel: str, *, private_key: Path, quota_policy: str | None) -> None:
    pending_dir = repo_root / pending_rel
    draft_path = pending_dir / "draft.destination.json"
    meta_path = pending_dir / "submission.meta.json"
    if not draft_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"Pending submission incomplete: {pending_dir}")

    draft: dict[str, Any] = json.loads(draft_path.read_text(encoding="utf-8"))
    meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    publisher_slug = str(meta.get("publisherSlug") or "")
    publisher_doc = _load_publisher(repo_root, publisher_slug)

    issued = _utc_now_iso()
    created = str(draft.get("createdAt") or issued)
    expires = str(draft.get("expiresAt") or _default_expiry(issued))

    destination: dict[str, Any] = dict(draft)
    destination["registryStatus"] = "ACTIVE"
    destination["createdAt"] = created
    destination["issuedAt"] = issued
    destination["expiresAt"] = expires
    destination["certificate"] = {
        "publisher": publisher_doc["publisher"],
        "quotaPolicy": quota_policy or publisher_doc.get("defaultQuotaPolicy", "NORMAL"),
        "createdAt": created,
        "issuedAt": issued,
        "expiresAt": expires,
        "signature": "",
    }

    rel_dest = _destination_rel_path(str(destination["source"]))
    dest_path = repo_root / rel_dest
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(destination, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    sign_cmd = [
        sys.executable,
        str(repo_root / "tools" / "sign-destination.py"),
        str(dest_path),
        "--private-key",
        str(private_key),
    ]
    subprocess.run(sign_cmd, check=True)

    schema_pending = pending_dir / "schema.json"
    if schema_pending.is_file():
        schema_url = str(draft.get("schemaUrl") or meta.get("schemaUrl") or "")
        prefix = "https://xmintake.github.io/registry/"
        if schema_url.startswith(prefix):
            schema_rel = schema_url[len(prefix) :]
            schema_out = repo_root / schema_rel
            schema_out.parent.mkdir(parents=True, exist_ok=True)
            schema_doc = json.loads(schema_pending.read_text(encoding="utf-8"))
            destination_id = str(draft.get("id") or meta.get("destinationId") or "")
            if publisher_slug and destination_id:
                schema_doc["schemaId"] = f"{publisher_slug}.{destination_id}"
                schema_doc["$schema"] = f"{prefix}meta/xmintake-schema.v1.json"
            schema_out.write_text(
                json.dumps(schema_doc, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    shutil.rmtree(pending_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote pending registry submission")
    parser.add_argument(
        "pending_rel",
        help="Relative path, e.g. submissions/pending/acme/travel-feedback",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path("XMRegistry.private-key.pem"),
    )
    parser.add_argument(
        "--quota-policy",
        default=None,
        help="Override quota policy (NORMAL, SPONSORED, EXEMPT)",
    )
    args = parser.parse_args()
    promote(
        args.repo_root,
        args.pending_rel.strip("/"),
        private_key=args.private_key,
        quota_policy=args.quota_policy,
    )
    generate = subprocess.run(
        [sys.executable, str(args.repo_root / "tools" / "generate-catalog.py"), "--repo-root", str(args.repo_root)],
        check=True,
    )
    _ = generate
    print(f"Promoted {args.pending_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
