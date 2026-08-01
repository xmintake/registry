#!/usr/bin/env python3
"""Regenerate catalog/index.json, catalog/browse.json, and catalog/publishers.json."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REGISTRY_HOST = "https://xmintake.github.io/registry"
APP_SHARE_BASE = "https://xmintake.xmarin.dev/x/share?text="

STRING_VARIANT_KINDS = {
    "single_line": "text",
    "multi_line": "long_text",
    "url": "url",
    "qr_code": "qr_scan",
    "barcode": "barcode",
    "nfc_tag": "nfc",
    "identifier_code": "identifier",
}

ATTACHMENT_VARIANT_KINDS = {
    "photo": "photo",
    "file": "file",
    "video": "video",
    "document_scan": "document_scan",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _install_url(target_url: str) -> str:
    return APP_SHARE_BASE + quote(target_url, safe="")


def _iter_schema_fields(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    fields = schema.get("fields")
    if isinstance(fields, dict):
        return [(str(name), cfg) for name, cfg in fields.items() if isinstance(cfg, dict)]
    if isinstance(fields, list):
        out: list[tuple[str, dict[str, Any]]] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or field.get("label") or "field")
            out.append((name, field))
        return out
    return []


def _preview_kind(field: dict[str, Any]) -> tuple[str, str | None]:
    if field.get("hidden") is True:
        return "hidden", None
    ftype = str(field.get("type") or "").lower()
    variant = str(field.get("uiVariant") or "").lower()
    if ftype == "enum":
        enum_cfg = field.get("enum")
        hint: str | None = None
        if isinstance(enum_cfg, dict):
            values = enum_cfg.get("values")
            count = len(values) if isinstance(values, list) else 0
            if count:
                hint = f"{count} option{'s' if count != 1 else ''}"
            if enum_cfg.get("acceptNewValues"):
                hint = (hint + "; custom values allowed") if hint else "custom values allowed"
        return "choice", hint
    if ftype == "string":
        return STRING_VARIANT_KINDS.get(variant, "text"), None
    if ftype == "attachment":
        return ATTACHMENT_VARIANT_KINDS.get(variant, "attachment"), None
    if ftype == "boolean":
        return "yes_no", None
    if ftype == "number":
        return "number", None
    if ftype == "date":
        return "date", None
    if ftype == "location":
        return "location", None
    return ftype or "unknown", None


def _preview_fields(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not schema:
        return []
    out: list[dict[str, Any]] = []
    for name, field in _iter_schema_fields(schema):
        kind, hint = _preview_kind(field)
        if kind == "hidden":
            continue
        entry: dict[str, Any] = {
            "name": str(field.get("label") or name),
            "kind": kind,
            "required": field.get("nullable") is False,
        }
        if hint:
            entry["hint"] = hint
        out.append(entry)
    return out


def _schema_has_attachments(schema: dict[str, Any] | None) -> bool:
    if not schema:
        return False
    for _, field in _iter_schema_fields(schema):
        if str(field.get("type") or "").lower() == "attachment":
            return True
    return False


def _publisher_name(doc: dict[str, Any]) -> str:
    cert = doc.get("certificate")
    if isinstance(cert, dict):
        pub = cert.get("publisher")
        if isinstance(pub, dict):
            return str(pub.get("name") or "")
    return ""


def _resolve_schema_path(repo_root: Path, schema_url: str) -> Path | None:
    prefix = REGISTRY_HOST + "/"
    if not schema_url.startswith(prefix):
        return None
    rel = schema_url[len(prefix) :]
    path = repo_root / rel
    return path if path.is_file() else None


def _load_categories(repo_root: Path) -> list[dict[str, str]]:
    path = repo_root / "catalog" / "categories.json"
    doc = _load_json(path)
    if not doc:
        return []
    categories = doc.get("categories")
    if not isinstance(categories, list):
        return []
    out: list[dict[str, str]] = []
    for item in categories:
        if isinstance(item, dict) and item.get("id") and item.get("label"):
            out.append({"id": str(item["id"]), "label": str(item["label"])})
    return out


def generate_publishers(repo_root: Path) -> dict[str, Any]:
    publishers_dir = repo_root / "publishers"
    entries: list[dict[str, Any]] = []
    if publishers_dir.is_dir():
        for path in sorted(publishers_dir.glob("*.publisher.json")):
            doc = _load_json(path)
            if not doc:
                continue
            slug = str(doc.get("publisherSlug") or path.stem.replace(".publisher", ""))
            publisher = doc.get("publisher")
            browse = doc.get("browse") if isinstance(doc.get("browse"), dict) else {}
            profile = publisher if isinstance(publisher, dict) else {}
            entries.append(
                {
                    "publisherSlug": slug,
                    "publisherId": doc.get("publisherId"),
                    "publisherStatus": str(doc.get("publisherStatus") or "ACTIVE"),
                    "name": profile.get("name"),
                    "type": profile.get("type"),
                    "website": profile.get("website"),
                    "supportEmail": profile.get("supportEmail"),
                    "supportPhone": profile.get("supportPhone"),
                    "tagline": browse.get("tagline"),
                }
            )
    return {"generatedAt": _utc_now_iso(), "publishers": entries}


def generate_catalog(repo_root: Path) -> dict[str, Any]:
    destinations_dir = repo_root / "destinations"
    entries: list[dict[str, Any]] = []
    if destinations_dir.is_dir():
        for path in sorted(destinations_dir.rglob("*.destination.json")):
            doc = _load_destination(path)
            if not doc:
                continue
            visibility = str(doc.get("visibility") or "PUBLIC")
            if visibility != "PUBLIC":
                continue
            rel = path.relative_to(destinations_dir)
            publisher_slug = rel.parts[0] if len(rel.parts) > 1 else "unknown"
            entries.append(
                {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "description": doc.get("description"),
                    "destinationType": doc.get("destinationType"),
                    "source": doc.get("source"),
                    "publisherSlug": publisher_slug,
                    "publisherName": _publisher_name(doc),
                    "tags": doc.get("tags") or [],
                    "primaryCategory": doc.get("primaryCategory"),
                }
            )
    return {"generatedAt": _utc_now_iso(), "destinations": entries}


def _load_destination(path: Path) -> dict[str, Any] | None:
    return _load_json(path)


def _humanize_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part)


def _schema_title(
    doc: dict[str, Any],
    *,
    schema_id: str,
    linked_dest: dict[str, Any] | None,
) -> str:
    title = doc.get("title")
    if isinstance(title, str) and title.strip() and title.strip().lower() != "intake form":
        return title.strip()
    if linked_dest and linked_dest.get("title"):
        return str(linked_dest["title"])
    schema_id_value = doc.get("schemaId")
    if isinstance(schema_id_value, str) and schema_id_value.strip():
        tail = schema_id_value.split(".")[-1]
        if tail and tail != schema_id_value:
            return _humanize_slug(tail)
    return _humanize_slug(schema_id)


def _schema_description(
    doc: dict[str, Any],
    *,
    linked_dest: dict[str, Any] | None,
) -> str:
    description = doc.get("description")
    if isinstance(description, str) and description.strip().lower() not in {"", "intake form"}:
        return description.strip()
    if linked_dest and linked_dest.get("description"):
        return str(linked_dest["description"])
    return str(description or "").strip()


def generate_browse(repo_root: Path) -> dict[str, Any]:
    categories = _load_categories(repo_root)
    category_ids = {c["id"] for c in categories}

    destination_by_schema_url: dict[str, list[str]] = {}
    browse_destinations: list[dict[str, Any]] = []

    destinations_dir = repo_root / "destinations"
    if destinations_dir.is_dir():
        for path in sorted(destinations_dir.rglob("*.destination.json")):
            doc = _load_destination(path)
            if not doc:
                continue
            visibility = str(doc.get("visibility") or "PUBLIC")
            if visibility != "PUBLIC":
                continue
            rel = path.relative_to(destinations_dir)
            publisher_slug = rel.parts[0] if len(rel.parts) > 1 else "unknown"
            dest_id = str(doc.get("id") or "")
            schema_url = str(doc.get("schemaUrl") or "")
            if schema_url:
                destination_by_schema_url.setdefault(schema_url, []).append(dest_id)
            schema_path = _resolve_schema_path(repo_root, schema_url)
            schema_doc = _load_json(schema_path) if schema_path else None
            source = str(doc.get("source") or "")
            browse_destinations.append(
                {
                    "id": dest_id,
                    "publisherSlug": publisher_slug,
                    "publisherName": _publisher_name(doc),
                    "title": doc.get("title"),
                    "description": doc.get("description"),
                    "color": doc.get("color"),
                    "destinationType": doc.get("destinationType"),
                    "visibility": visibility,
                    "source": source,
                    "schemaUrl": schema_url,
                    "installUrl": _install_url(source) if source else None,
                    "tags": doc.get("tags") or [],
                    "primaryCategory": doc.get("primaryCategory"),
                    "issuedAt": doc.get("issuedAt"),
                    "hasAttachments": _schema_has_attachments(schema_doc),
                    "previewFields": _preview_fields(schema_doc),
                }
            )

    browse_schemas: list[dict[str, Any]] = []
    schemas_dir = repo_root / "schemas"
    if schemas_dir.is_dir():
        for path in sorted(schemas_dir.rglob("*.schema.json")):
            doc = _load_json(path)
            if not doc:
                continue
            rel = path.relative_to(schemas_dir)
            publisher_slug = rel.parts[0] if len(rel.parts) > 1 else "unknown"
            schema_id = path.stem.replace(".schema", "")
            schema_url = f"{REGISTRY_HOST}/schemas/{rel.as_posix()}"
            linked_ids = destination_by_schema_url.get(schema_url, [])
            linked_dest = next(
                (
                    d
                    for d in browse_destinations
                    if d["id"] in linked_ids and d["publisherSlug"] == publisher_slug
                ),
                None,
            )
            browse_schemas.append(
                {
                    "id": schema_id,
                    "publisherSlug": publisher_slug,
                    "publisherName": linked_dest.get("publisherName") if linked_dest else "",
                    "title": _schema_title(doc, schema_id=schema_id, linked_dest=linked_dest),
                    "description": _schema_description(doc, linked_dest=linked_dest),
                    "schemaUrl": schema_url,
                    "useSchemaUrl": _install_url(schema_url),
                    "linkedDestinationIds": linked_ids,
                    "tags": doc.get("tags") or [],
                    "primaryCategory": doc.get("primaryCategory"),
                    "previewFields": _preview_fields(doc),
                }
            )

    return {
        "generatedAt": _utc_now_iso(),
        "categories": categories,
        "destinations": browse_destinations,
        "schemas": browse_schemas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate registry catalog artifacts")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    repo_root = args.repo_root

    index = generate_catalog(repo_root)
    browse = generate_browse(repo_root)
    publishers = generate_publishers(repo_root)

    catalog_dir = repo_root / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    (catalog_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (catalog_dir / "browse.json").write_text(
        json.dumps(browse, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (catalog_dir / "publishers.json").write_text(
        json.dumps(publishers, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote catalog/index.json ({len(index['destinations'])} public destinations), "
        f"browse.json ({len(browse['destinations'])} destinations, {len(browse['schemas'])} schemas), "
        f"publishers.json ({len(publishers['publishers'])} publishers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
