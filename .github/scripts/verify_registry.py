#!/usr/bin/env python3
"""Verify a public XMRegistry tree before it is pushed or deployed.

Standalone on purpose: the public `registry` repo runs a copy of this file in
`.github/scripts/` without access to `registry-ops`.

  python3 verify_registry.py --root ../registry
  python3 verify_registry.py --root ../registry --allow-unsigned-schemas

Exit code 0 when the tree is publishable; 1 with one line per problem otherwise.
Requires openssl 3+ (Ed25519 with -rawin).
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REGISTRY_HOST = "https://xmintake.github.io/registry"
PUBLIC_KEY_FILE = "XMRegistry.public-key.pem"

ALLOWED_TOP_LEVEL = {
    "destinations",
    "schemas",
    "scenarios",
    "catalog",
    "meta",
    "spec",
    "assets",
    "index.html",
    "404.html",
    "CNAME",
    "README.md",
    PUBLIC_KEY_FILE,
    ".gitignore",
    ".github",
    ".nojekyll",
}
FORBIDDEN_TOP_LEVEL = {"publishers", "submissions", "deletions", "tools", "service", "published-index.json"}
PRIVATE_PUBLISHER_KEYS = {"allowedIdentities", "defaultQuotaPolicy", "audiences", "registeredBy"}
PHONE_PRIVATE_TYPES = {"INDIVIDUAL", "COMMUNITY"}
PHONE_NOT_LISTED = "Not listed"
VISIBILITIES = {"PUBLIC", "UNLISTED"}
URL_PARAM_KEYS = {"sourceUrl", "schemaUrl", "url", "scenarioUrl"}


# --- Canonical JSON (must match the app's verifier and the signing tools) ---

def _quote(raw: str) -> str:
    out = ['"']
    for ch in raw:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _canonical_number(number: int | float) -> str:
    if isinstance(number, int):
        return str(number)
    as_long = int(number)
    if float(number) == float(as_long):
        return str(as_long)
    return repr(number)


def canonical_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return canonical_object(value)
    return _quote(str(value))


def canonical_object(obj: dict[str, Any]) -> str:
    return "{" + ",".join(f"{_quote(k)}:{canonical_value(obj[k])}" for k in sorted(obj.keys())) + "}"


def destination_payload(document: dict[str, Any]) -> bytes:
    cert = document.get("certificate")
    if not isinstance(cert, dict):
        raise ValueError("missing certificate")
    cert = dict(cert)
    cert.pop("signature", None)
    root = dict(document)
    root["certificate"] = cert
    return canonical_object(root).encode("utf-8")


def detached_payload(document: dict[str, Any]) -> bytes:
    """Schemas and scenarios: everything except the top-level `signature` object."""
    root = dict(document)
    root.pop("signature", None)
    return canonical_object(root).encode("utf-8")


def destination_signature(document: dict[str, Any]) -> str:
    cert = document.get("certificate")
    return str(cert.get("signature") or "") if isinstance(cert, dict) else ""


def detached_signature(document: dict[str, Any]) -> str:
    sig = document.get("signature")
    if isinstance(sig, dict) and str(sig.get("type") or "ed25519") == "ed25519":
        return str(sig.get("value") or "")
    return ""


def verify_ed25519(public_key_pem: Path, message: bytes, signature_b64: str) -> bool:
    if not signature_b64:
        return False
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except ValueError:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        msg_path = Path(tmp) / "msg.bin"
        sig_path = Path(tmp) / "sig.bin"
        msg_path.write_bytes(message)
        sig_path.write_bytes(signature)
        proc = subprocess.run(
            [
                "openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key_pem),
                "-rawin", "-in", str(msg_path), "-sigfile", str(sig_path),
            ],
            capture_output=True,
        )
    return proc.returncode == 0


# --- Checks ---

def _load(path: Path, problems: list[str], root: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.relative_to(root)}: invalid JSON ({exc})")
        return None
    if not isinstance(doc, dict):
        problems.append(f"{path.relative_to(root)}: top level must be an object")
        return None
    return doc


def _check_distribution(rel: str, doc: dict[str, Any], problems: list[str]) -> None:
    distribution = doc.get("distribution")
    if distribution is not None and distribution != "PUBLIC":
        problems.append(f"{rel}: distribution must be PUBLIC on the public registry (got {distribution})")


def check_top_level(root: Path, problems: list[str], warnings: list[str]) -> None:
    for entry in sorted(root.iterdir()):
        name = entry.name
        if name == ".git":
            continue
        if name in FORBIDDEN_TOP_LEVEL:
            problems.append(f"{name}: must not be in the public registry")
        elif name.endswith(".pem") and name != PUBLIC_KEY_FILE:
            problems.append(f"{name}: key files other than {PUBLIC_KEY_FILE} must not be public")
        elif name not in ALLOWED_TOP_LEVEL and not name.startswith("."):
            warnings.append(f"{name}: unexpected top-level entry")
    for path in root.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.name.endswith(".publisher.json") or path.name.endswith(".private-key.pem"):
            problems.append(f"{path.relative_to(root)}: private file in public tree")


def check_destinations(root: Path, key: Path, problems: list[str]) -> None:
    base = root / "destinations"
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.destination.json")):
        rel = path.relative_to(root).as_posix()
        doc = _load(path, problems, root)
        if doc is None:
            continue
        expected_source = f"{REGISTRY_HOST}/{rel}"
        if str(doc.get("source") or "") != expected_source:
            problems.append(f"{rel}: source must be {expected_source}")
        if str(doc.get("visibility") or "PUBLIC") not in VISIBILITIES:
            problems.append(f"{rel}: visibility must be PUBLIC or UNLISTED")
        _check_distribution(rel, doc, problems)
        schema_url = str(doc.get("schemaUrl") or "")
        if not schema_url.startswith(f"{REGISTRY_HOST}/schemas/"):
            problems.append(f"{rel}: schemaUrl must be a registry schema ({schema_url or 'missing'})")
        elif not (root / schema_url[len(REGISTRY_HOST) + 1:]).is_file():
            problems.append(f"{rel}: schema not found in registry ({schema_url})")
        cert = doc.get("certificate") if isinstance(doc.get("certificate"), dict) else {}
        cert_publisher = cert.get("publisher") if isinstance(cert.get("publisher"), dict) else {}
        if str(cert_publisher.get("type") or "").upper() in PHONE_PRIVATE_TYPES and str(
            cert_publisher.get("supportPhone") or ""
        ) not in {"", PHONE_NOT_LISTED}:
            problems.append(f"{rel}: certificate must not publish the phone of a {cert_publisher.get('type')} publisher")
        try:
            ok = verify_ed25519(key, destination_payload(doc), destination_signature(doc))
        except ValueError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        if not ok:
            problems.append(f"{rel}: signature does not verify")


def check_schemas(root: Path, key: Path, problems: list[str], *, allow_unsigned: bool) -> None:
    base = root / "schemas"
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.schema.json")):
        rel = path.relative_to(root).as_posix()
        doc = _load(path, problems, root)
        if doc is None:
            continue
        _check_distribution(rel, doc, problems)
        if str(doc.get("visibility") or "PUBLIC") not in VISIBILITIES:
            problems.append(f"{rel}: visibility must be PUBLIC or UNLISTED")
        signature = detached_signature(doc)
        if not signature:
            if not allow_unsigned:
                problems.append(f"{rel}: schema is not signed")
            continue
        if not verify_ed25519(key, detached_payload(doc), signature):
            problems.append(f"{rel}: signature does not verify")


def _iter_step_urls(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in URL_PARAM_KEYS and isinstance(v, str) and v.startswith("http"):
                yield k, v
            else:
                yield from _iter_step_urls(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_step_urls(item)


def check_scenarios(root: Path, key: Path, problems: list[str]) -> None:
    base = root / "scenarios"
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.scenario.json")):
        rel = path.relative_to(root).as_posix()
        doc = _load(path, problems, root)
        if doc is None:
            continue
        _check_distribution(rel, doc, problems)
        for name, url in _iter_step_urls(doc.get("scenario")):
            if name in {"sourceUrl", "schemaUrl"} and not url.startswith(REGISTRY_HOST + "/"):
                problems.append(f"{rel}: {name} must point at the registry ({url})")
        if not verify_ed25519(key, detached_payload(doc), detached_signature(doc)):
            problems.append(f"{rel}: signature missing or does not verify")


def check_publishers_catalog(root: Path, problems: list[str]) -> None:
    path = root / "catalog" / "publishers.json"
    if not path.is_file():
        return
    doc = _load(path, problems, root)
    if doc is None:
        return
    for entry in doc.get("publishers") or []:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("publisherSlug")
        leaked = sorted(PRIVATE_PUBLISHER_KEYS & set(entry))
        if leaked:
            problems.append(f"catalog/publishers.json: {slug} exposes private fields {leaked}")
        ptype = str(entry.get("type") or "").upper()
        if ptype in PHONE_PRIVATE_TYPES and entry.get("supportPhone"):
            problems.append(f"catalog/publishers.json: {slug} ({ptype}) must not publish supportPhone")


def verify_tree(root: Path, *, public_key: Path | None = None, allow_unsigned_schemas: bool = False) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    key = public_key or (root / PUBLIC_KEY_FILE)
    if not key.is_file():
        return [f"public key not found: {key}"], warnings
    check_top_level(root, problems, warnings)
    check_destinations(root, key, problems)
    check_schemas(root, key, problems, allow_unsigned=allow_unsigned_schemas)
    check_scenarios(root, key, problems)
    check_publishers_catalog(root, problems)
    return problems, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a public XMRegistry tree")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--public-key", type=Path, default=None)
    parser.add_argument("--allow-unsigned-schemas", action="store_true")
    args = parser.parse_args()
    problems, warnings = verify_tree(
        args.root.resolve(),
        public_key=args.public_key,
        allow_unsigned_schemas=args.allow_unsigned_schemas,
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s); not publishable.", file=sys.stderr)
        return 1
    print("Registry tree verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
