import os
import sys
import shutil
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

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def test_find_rar_asset_by_exact_name(self):
        assets = [
            {"name": "README.txt", "browser_download_url": "http://example.com/readme"},
            {"name": "GoldenEye-Recomp-Win.rar", "browser_download_url": "http://example.com/GoldenEye-Recomp-Win.rar"},
        ]
        self.assertEqual(
            self.mgr._find_rar_url(assets),
            "http://example.com/GoldenEye-Recomp-Win.rar"
        )

    def test_find_rar_asset_fallback_any_rar(self):
        assets = [
            {"name": "README.txt", "browser_download_url": "http://example.com/readme"},
            {"name": "other-release.rar", "browser_download_url": "http://example.com/other.rar"},
        ]
        self.assertEqual(
            self.mgr._find_rar_url(assets),
            "http://example.com/other.rar"
        )

    def test_find_rar_asset_missing_raises(self):
        assets = [{"name": "README.txt", "browser_download_url": "http://example.com/readme"}]
        with self.assertRaises(UpdateError):
            self.mgr._find_rar_url(assets)

    # --- _copy_files ---

    def _make_src(self, files: dict) -> str:
        src = tempfile.mkdtemp()
        for rel_path, content in files.items():
            full = os.path.join(src, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
        return src

    def test_copy_files_flat(self):
        src = self._make_src({"GoldenEye.exe": "exe", "rexruntimerd.dll": "dll"})
        self.mgr._copy_files(src)
        shutil.rmtree(src)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "GoldenEye.exe")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "rexruntimerd.dll")))

    def test_copy_files_strips_top_level_dir(self):
        src = self._make_src({
            os.path.join("GoldenEye-v1.0", "GoldenEye.exe"): "exe",
            os.path.join("GoldenEye-v1.0", "rexruntimerd.dll"): "dll",
        })
        self.mgr._copy_files(src)
        shutil.rmtree(src)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "GoldenEye.exe")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "GoldenEye-v1.0")))

    def test_copy_files_skips_assets(self):
        src = self._make_src({
            os.path.join("GoldenEye-v1.0", "GoldenEye.exe"): "exe",
            os.path.join("GoldenEye-v1.0", "assets", "music.xwb"): "music",
            os.path.join("GoldenEye-v1.0", "assets", "sfx.xwb"): "sfx",
        })
        self.mgr._copy_files(src)
        shutil.rmtree(src)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "GoldenEye.exe")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "assets")))

    def test_copy_files_progress_reported(self):
        src = self._make_src({
            os.path.join("GoldenEye-v1.0", "GoldenEye.exe"): "exe",
            os.path.join("GoldenEye-v1.0", "rexruntimerd.dll"): "dll",
        })
        self.mgr._copy_files(src)
        shutil.rmtree(src)
        fractions = [f for _, f in self.events if _ == "Extracting..."]
        self.assertTrue(len(fractions) > 0)
        self.assertEqual(fractions[-1], 1.0)


if __name__ == "__main__":
    unittest.main()
