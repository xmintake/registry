#!/usr/bin/env python3
"""
Sign an XMRegistry .destination.json file with Ed25519 (canonical JSON payload).

Usage:
  python3 tools/sign-destination.py destinations/xmintake/xmintake-feedback.destination.json \\
    --private-key XMRegistry.private-key.pem

Requires: openssl 3+ (Ed25519), Python 3.9+
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def quote(raw: str) -> str:
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


def canonical_number(number: int | float) -> str:
    if isinstance(number, bool):
        return "true" if number else "false"
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
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return canonical_number(value)
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return canonical_object(value)
    return quote(str(value))


def canonical_object(obj: dict[str, Any]) -> str:
    keys = sorted(obj.keys())
    body = ",".join(f"{quote(k)}:{canonical_value(obj[k])}" for k in keys)
    return "{" + body + "}"


def signing_payload_bytes(document: dict[str, Any]) -> bytes:
    cert = document.get("certificate")
    if not isinstance(cert, dict):
        raise ValueError("Missing certificate object")
    cert = dict(cert)
    cert.pop("signature", None)
    root = dict(document)
    root["certificate"] = cert
    return canonical_object(root).encode("utf-8")


def sign_ed25519(private_key_pem: Path, message: bytes) -> str:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(message)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", str(private_key_pem), "-in", tmp_path, "-rawin"],
            capture_output=True,
            check=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return base64.b64encode(proc.stdout).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign XMRegistry destination JSON")
    parser.add_argument("destination_file", type=Path)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path("XMRegistry.private-key.pem"),
        help="Ed25519 private key PEM (PKCS#8)",
    )
    args = parser.parse_args()

    path = args.destination_file
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = signing_payload_bytes(document)
    signature = sign_ed25519(args.private_key, payload)

    document.setdefault("certificate", {})["signature"] = signature
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Signed {path}")
    print(f"Payload bytes: {len(payload)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
