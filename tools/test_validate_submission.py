#!/usr/bin/env python3
"""Smoke tests for tools/validate-submission.py sheetMode rules."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_validate_module():
    path = Path(__file__).with_name("validate-submission.py")
    spec = importlib.util.spec_from_file_location("validate_submission", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_submission = _load_validate_module()


def _write_pending(
    root: Path,
    *,
    sheet_mode: str,
    attachment_policy: dict | None,
    schema_has_attachment: bool,
) -> Path:
    pending = root / "submissions" / "pending" / "acme" / "travel-feedback"
    pending.mkdir(parents=True)
    source = "https://xmintake.github.io/registry/destinations/acme/travel-feedback.destination.json"
    draft: dict = {
        "source": source,
        "sheetMode": sheet_mode,
        "visibility": "PUBLIC",
        "spreadsheetId": "1abc1234567890abcdefghijklmnop",
        "gid": "0",
        "schemaUrl": "https://xmintake.github.io/registry/schemas/acme/travel-feedback.schema.json",
    }
    if attachment_policy is not None:
        draft["attachmentPolicy"] = attachment_policy
    (pending / "draft.destination.json").write_text(json.dumps(draft), encoding="utf-8")
    (pending / "submission.meta.json").write_text(
        json.dumps({"proposedSource": source, "publisherSlug": "acme"}),
        encoding="utf-8",
    )
    fields = (
        [{"name": "photo", "type": "attachment"}]
        if schema_has_attachment
        else [{"name": "note", "type": "text"}]
    )
    (pending / "schema.json").write_text(json.dumps({"version": 1, "fields": fields}), encoding="utf-8")
    (root / "catalog").mkdir(parents=True, exist_ok=True)
    (root / "catalog" / "categories.json").write_text(
        json.dumps({"categories": [{"id": "feedback"}]}),
        encoding="utf-8",
    )
    return pending


class ValidateSubmissionSheetModeTests(unittest.TestCase):
    def test_template_without_attachment_policy_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = _write_pending(
                root,
                sheet_mode="TEMPLATE",
                attachment_policy=None,
                schema_has_attachment=True,
            )
            self.assertEqual(validate_submission.validate_pending_dir(pending, repo_root=root), [])

    def test_template_with_attachment_policy_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = _write_pending(
                root,
                sheet_mode="TEMPLATE",
                attachment_policy={
                    "required": True,
                    "folderUrl": "https://drive.google.com/drive/folders/x",
                },
                schema_has_attachment=True,
            )
            errors = validate_submission.validate_pending_dir(pending, repo_root=root)
            self.assertTrue(any("attachmentPolicy must be omitted" in e for e in errors))

    def test_shared_requires_attachment_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = _write_pending(
                root,
                sheet_mode="SHARED",
                attachment_policy=None,
                schema_has_attachment=True,
            )
            errors = validate_submission.validate_pending_dir(pending, repo_root=root)
            self.assertTrue(any("attachmentPolicy required" in e for e in errors))

    def test_shared_with_attachment_policy_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = _write_pending(
                root,
                sheet_mode="SHARED",
                attachment_policy={
                    "required": True,
                    "folderUrl": "https://drive.google.com/drive/folders/x",
                },
                schema_has_attachment=True,
            )
            self.assertEqual(validate_submission.validate_pending_dir(pending, repo_root=root), [])


if __name__ == "__main__":
    unittest.main()
