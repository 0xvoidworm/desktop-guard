import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from desktop_guard import DesktopGuard


class DesktopGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-guard-test-")
        self.root = Path(self.temporary.name)
        self.personal = self.root / "Personal"
        self.public = self.root / "Public"
        self.personal.mkdir()
        self.public.mkdir()
        self.guard = DesktopGuard({
            "personal_desktop": str(self.personal),
            "public_desktop": str(self.public),
            "allowed_names": ["This PC.lnk", "Terminal.lnk", "wormGPT.lnk"],
            "output_dir": str(self.root / "Output"),
            "enforce_native_icons": False,
        })

    def tearDown(self):
        self.temporary.cleanup()

    def test_hides_files_and_only_top_level_folder(self):
        image = self.personal / "photo.png"
        image.write_bytes(b"unchanged-image")
        folder = self.personal / "New Folder"
        folder.mkdir()
        nested = folder / "keep.txt"
        nested.write_text("untouched")
        self.guard.scan()
        self.assertTrue(image.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
        self.assertTrue(folder.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
        self.assertFalse(nested.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
        self.assertEqual(image.read_bytes(), b"unchanged-image")

    def test_allowed_shortcuts_preserved_case_insensitively(self):
        paths = [self.personal / name for name in ("This PC.lnk", "TERMINAL.LNK", "wormGPT.lnk")]
        for path in paths:
            path.write_bytes(b"shortcut-content")
        self.guard.scan()
        for path in paths:
            self.assertEqual(path.read_bytes(), b"shortcut-content")
            self.assertFalse(path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)

    def test_public_shortcut_permission_fallback_waits_and_preserves_bytes(self):
        link = self.public / "Installer.lnk"
        link.write_bytes(b"public-shortcut")
        with patch("desktop_guard.hide_path", side_effect=PermissionError("test")):
            self.guard.scan()
            self.assertTrue(link.exists())
            signature, started = self.guard.pending[str(link)]
            self.guard.pending[str(link)] = (signature, started - 3)
            self.guard.scan()
        archived = list((self.guard.output / "PublicDesktop").glob("*.lnk"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), b"public-shortcut")
        self.assertFalse(link.exists())

    def test_public_document_and_folder_never_relocated_on_denial(self):
        document = self.public / "notes.txt"
        document.write_text("important")
        folder = self.public / "Folder"
        folder.mkdir()
        with patch("desktop_guard.hide_path", side_effect=PermissionError("test")):
            self.guard.scan()
        self.assertTrue(document.exists())
        self.assertTrue(folder.is_dir())
        self.assertFalse((self.guard.output / "PublicDesktop").exists())

    def test_scan_idempotent_and_status_valid(self):
        item = self.personal / "new.txt"
        item.write_text("same")
        self.guard.scan()
        self.guard.scan()
        self.assertEqual(self.guard.counts["hidden"], 1)
        status = json.loads((self.guard.output / "status.json").read_text())
        self.assertEqual(len(status["allowed"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
