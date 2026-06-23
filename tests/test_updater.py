import os
import sys
import zipfile
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from launcher import UpdateManager, UpdateError


class TestUpdateManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.events = []
        self.mgr = UpdateManager(self.tmp, lambda s, f: self.events.append((s, f)))

    # --- version helpers ---

    def test_read_version_missing_file(self):
        self.assertIsNone(self.mgr._read_local_version())

    def test_read_version_existing_file(self):
        with open(os.path.join(self.tmp, "version.txt"), "w") as f:
            f.write("v2.0.0\n")
        self.assertEqual(self.mgr._read_local_version(), "v2.0.0")

    def test_write_version(self):
        self.mgr._write_version("v3.0.0")
        with open(os.path.join(self.tmp, "version.txt")) as f:
            self.assertEqual(f.read().strip(), "v3.0.0")

    # --- up-to-date check ---

    def test_already_up_to_date(self):
        self.assertTrue(self.mgr._is_up_to_date("v1.2.0", "v1.2.0"))

    def test_update_needed(self):
        self.assertFalse(self.mgr._is_up_to_date("v1.1.0", "v1.2.0"))

    def test_missing_version_triggers_update(self):
        self.assertFalse(self.mgr._is_up_to_date(None, "v1.2.0"))

    # --- asset finder ---

    def test_find_zip_asset(self):
        assets = [
            {"name": "README.txt", "browser_download_url": "http://example.com/readme"},
            {"name": "release.zip", "browser_download_url": "http://example.com/release.zip"},
        ]
        self.assertEqual(
            self.mgr._find_zip_url(assets),
            "http://example.com/release.zip"
        )

    def test_find_zip_asset_missing_raises(self):
        assets = [{"name": "README.txt", "browser_download_url": "http://example.com/readme"}]
        with self.assertRaises(UpdateError):
            self.mgr._find_zip_url(assets)

    # --- extract ---

    def test_extract_flat_zip(self):
        zip_path = os.path.join(self.tmp, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("GoldenEye.exe", b"fake exe")
            zf.writestr("rexruntimerd.dll", b"fake dll")
        self.mgr._extract_zip(zip_path)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "GoldenEye.exe")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "rexruntimerd.dll")))

    def test_extract_zip_strips_top_level_dir(self):
        zip_path = os.path.join(self.tmp, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("GoldenEye-v1.0/GoldenEye.exe", b"fake exe")
            zf.writestr("GoldenEye-v1.0/rexruntimerd.dll", b"fake dll")
        self.mgr._extract_zip(zip_path)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "GoldenEye.exe")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "rexruntimerd.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "GoldenEye-v1.0")))

    def test_extract_zip_slip_prevented(self):
        zip_path = os.path.join(self.tmp, "evil.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.exe", b"malicious content")
        with self.assertRaises(UpdateError):
            self.mgr._extract_zip(zip_path)


if __name__ == "__main__":
    unittest.main()
