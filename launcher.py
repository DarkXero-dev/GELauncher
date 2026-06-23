import os
import sys
import zipfile
import threading
import subprocess
import tempfile
import requests
import customtkinter as ctk
from PIL import Image
from typing import Callable, Optional
import pystray


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_game_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_asset_path(filename: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class UpdateError(Exception):
    pass


# ---------------------------------------------------------------------------
# UpdateManager
# ---------------------------------------------------------------------------

GITHUB_API_URL = "https://api.github.com/repos/SunJaycy/GoldenEye-Recomp/releases/latest"


class UpdateManager:
    def __init__(self, game_dir: str, progress_callback: Callable[[str, float], None]):
        self.game_dir = game_dir
        self.progress = progress_callback

    def check_and_update(self) -> None:
        self.progress("Checking for updates...", 0.0)
        release = self._fetch_latest_release()
        remote_tag = release["tag_name"]
        local_tag = self._read_local_version()

        if self._is_up_to_date(local_tag, remote_tag):
            self.progress("Already up to date.", 1.0)
            return

        zip_url = self._find_zip_url(release["assets"])
        zip_path = self._download(zip_url, remote_tag)
        self._extract_zip(zip_path)
        os.remove(zip_path)
        self._write_version(remote_tag)
        self.progress("Update complete!", 1.0)

    def _fetch_latest_release(self) -> dict:
        try:
            resp = requests.get(GITHUB_API_URL, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise UpdateError(f"Failed to fetch release info: {e}")

    def _is_up_to_date(self, local: Optional[str], remote: str) -> bool:
        return local is not None and local.strip() == remote.strip()

    def _read_local_version(self) -> Optional[str]:
        path = os.path.join(self.game_dir, "version.txt")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return f.read().strip() or None

    def _write_version(self, tag: str) -> None:
        with open(os.path.join(self.game_dir, "version.txt"), "w") as f:
            f.write(tag)

    def _find_zip_url(self, assets: list) -> str:
        for asset in assets:
            if asset["name"].endswith(".zip"):
                return asset["browser_download_url"]
        raise UpdateError("No .zip asset found in release.")

    def _download(self, url: str, tag: str) -> str:
        self.progress(f"Downloading {tag}...", 0.0)
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            received = 0
            for chunk in resp.iter_content(chunk_size=65536):
                tmp.write(chunk)
                received += len(chunk)
                if total:
                    self.progress(f"Downloading {tag}...", received / total)
            tmp.close()
            return tmp.name
        except Exception as e:
            raise UpdateError(f"Download failed: {e}")

    def _extract_zip(self, zip_path: str) -> None:
        self.progress("Extracting...", 0.0)
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            # Detect and strip common top-level directory (e.g. GoldenEye-v1.0/)
            top_dirs = {m.split("/")[0] for m in members if "/" in m}
            has_single_root = (
                len(top_dirs) == 1
                and all(m.startswith(list(top_dirs)[0] + "/") for m in members if m)
            )
            strip_prefix = (list(top_dirs)[0] + "/") if has_single_root else ""

            for i, member in enumerate(members):
                if not member.endswith("/"):
                    target = member[len(strip_prefix):] if strip_prefix and member.startswith(strip_prefix) else member
                    if target:
                        dest = os.path.join(self.game_dir, target)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(member) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                self.progress("Extracting...", (i + 1) / len(members))
