"""Portable preview must reject incomplete or modified copies before launch."""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required for the portable launcher")
class PreviewVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = pathlib.Path(self.temporary.name)
        entry = self.package / "viewer/citywide-v1.html"
        entry.parent.mkdir()
        entry.write_bytes(b"preview")
        manifest = {
            "schema": "therabby.geoengine.citywide-static-preview.v0.1",
            "status": "internal_preview; v1.0 acceptance pending",
            "entry": "viewer/citywide-v1.html",
            "acceptance_complete": False,
            "files": [{"path": "viewer/citywide-v1.html", "byte_length": 7,
                       "sha256": hashlib.sha256(b"preview").hexdigest()}],
        }
        (self.package / "preview_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def verify(self):
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ROOT / "verify_citywide_preview.ps1"), "-PackageRoot", str(self.package)],
            capture_output=True, text=True, timeout=30,
        )

    def test_accepts_complete_copy_and_rejects_changed_or_unlisted_files(self):
        valid = self.verify()
        self.assertEqual(valid.returncode, 0, valid.stderr + valid.stdout)
        (self.package / "geoengine-citywide-2026-11-01T05-33-54-406Z.json").write_text(
            '{"schema":"therabby.geoengine.citywide-browser-measurement.v0.1"}', encoding="utf-8")
        with_result = self.verify()
        self.assertEqual(with_result.returncode, 0, with_result.stderr + with_result.stdout)
        (self.package / "viewer/citywide-v1.html").write_bytes(b"changed")
        changed = self.verify()
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("SHA-256 differs", changed.stderr)
        (self.package / "viewer/citywide-v1.html").write_bytes(b"preview")
        (self.package / "unexpected.txt").write_bytes(b"stale")
        unlisted = self.verify()
        self.assertNotEqual(unlisted.returncode, 0)
        self.assertIn("Unlisted preview file", unlisted.stderr)

    def test_rejects_missing_entry(self):
        (self.package / "viewer/citywide-v1.html").unlink()
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.stderr)
