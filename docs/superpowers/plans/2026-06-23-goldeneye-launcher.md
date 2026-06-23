# GoldenEye Recomp Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single portable Windows .exe launcher with game launch and GitHub-based engine update functionality.

**Architecture:** Single-file Python app (`launcher.py`) with four classes - App (CTk root window), ProgressModal (update overlay), TrayManager (pystray), UpdateManager (GitHub API + download + extract) - compiled to one `.exe` via PyInstaller `--onefile --windowed`. `banner.png` bundled inside and accessed via `sys._MEIPASS` at runtime.

**Tech Stack:** Python 3.11+, customtkinter, Pillow, requests, pystray, PyInstaller

## Global Constraints

- Windows-only target; PyInstaller build must run on Windows
- Portable: single .exe, no installer, no registry writes
- Game directory = `os.path.dirname(sys.executable)` when frozen, `os.path.dirname(__file__)` in dev
- Bundled assets via `sys._MEIPASS` when frozen, script dir in dev
- GitHub repo: `SunJaycy/GoldenEye-Recomp`
- Game binary name: `GoldenEye.exe` (same dir as launcher)
- Version tracking file: `version.txt` (same dir as launcher, auto-created on first update)
- `banner.png` must be in the game dir when running `build.bat`

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `build.bat`

- [ ] **Step 1: Create requirements.txt**

```
customtkinter==5.2.2
Pillow==10.4.0
requests==2.32.3
pystray==0.19.5
pyinstaller==6.10.0
```

- [ ] **Step 2: Create build.bat**

```bat
@echo off
pyinstaller --onefile --windowed --name "GoldenEye Launcher" --add-data "banner.png;." launcher.py
echo Build complete. Output in dist\
pause
```

- [ ] **Step 3: Initialize git and commit**

```bash
git init
git add requirements.txt build.bat
git commit -m "chore: add project scaffold, requirements, and build script"
```

---

### Task 2: UpdateManager

**Files:**
- Create: `launcher.py` (UpdateManager + helpers + error class; App/Modal/Tray added in later tasks)
- Create: `tests/test_updater.py`

**Interfaces:**
- Produces:
  - `get_game_dir() -> str`
  - `get_asset_path(filename: str) -> str`
  - `UpdateError(Exception)`
  - `UpdateManager(game_dir: str, progress_callback: Callable[[str, float], None])`
  - `UpdateManager.check_and_update() -> None` - raises `UpdateError` on failure; calls `progress_callback(status: str, fraction: float)` where fraction is 0.0-1.0

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py` (empty) and `tests/test_updater.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_updater.py -v
```

Expected: `ModuleNotFoundError: No module named 'launcher'`

- [ ] **Step 3: Create launcher.py with UpdateManager**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_updater.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add launcher.py tests/
git commit -m "feat: add UpdateManager with version check, download, and zip extract"
```

---

### Task 3: TrayManager

**Files:**
- Modify: `launcher.py` (append TrayManager class after UpdateManager)

**Interfaces:**
- Consumes: `get_asset_path(filename: str) -> str` from Task 2
- Produces:
  - `TrayManager(on_restore: Callable[[], None], on_quit: Callable[[], None])`
  - `TrayManager.show() -> None`
  - `TrayManager.hide() -> None`

- [ ] **Step 1: Append TrayManager to launcher.py**

Add after the UpdateManager class (before `if __name__ == "__main__"` - which doesn't exist yet):

```python
# ---------------------------------------------------------------------------
# TrayManager
# ---------------------------------------------------------------------------

class TrayManager:
    def __init__(self, on_restore: Callable[[], None], on_quit: Callable[[], None]):
        self._on_restore = on_restore
        self._on_quit = on_quit
        self._icon: Optional[pystray.Icon] = None

    def show(self) -> None:
        if self._icon is not None:
            return
        img = Image.open(get_asset_path("banner.png")).resize((64, 64))
        menu = pystray.Menu(
            pystray.MenuItem("Restore", lambda icon, item: self._on_restore()),
            pystray.MenuItem("Quit", lambda icon, item: self._on_quit()),
        )
        self._icon = pystray.Icon("GoldenEye Launcher", img, "GoldenEye Launcher", menu)
        self._icon.on_activate = lambda icon: self._on_restore()
        t = threading.Thread(target=self._icon.run, daemon=True)
        t.start()

    def hide(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
```

- [ ] **Step 2: Verify tests still pass**

```bash
python -m pytest tests/test_updater.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add launcher.py
git commit -m "feat: add TrayManager with pystray icon, Restore and Quit menu"
```

---

### Task 4: ProgressModal

**Files:**
- Modify: `launcher.py` (append ProgressModal class after TrayManager)

**Interfaces:**
- Consumes:
  - `UpdateManager(game_dir, progress_callback)` from Task 2
  - `get_game_dir() -> str` from Task 2
- Produces:
  - `ProgressModal(parent: ctk.CTk)`
  - `ProgressModal.run_update() -> None`

- [ ] **Step 1: Append ProgressModal to launcher.py**

Add after TrayManager:

```python
# ---------------------------------------------------------------------------
# ProgressModal
# ---------------------------------------------------------------------------

class ProgressModal:
    def __init__(self, parent: ctk.CTk):
        self._parent = parent
        self._win: Optional[ctk.CTkToplevel] = None
        self._status_label: Optional[ctk.CTkLabel] = None
        self._bar: Optional[ctk.CTkProgressBar] = None

    def run_update(self) -> None:
        self._win = ctk.CTkToplevel(self._parent)
        self._win.title("Updating ReComp Engine")
        self._win.geometry("420x140")
        self._win.resizable(False, False)
        self._win.grab_set()
        self._win.focus_force()

        self._status_label = ctk.CTkLabel(
            self._win, text="Starting...", font=("Segoe UI", 13)
        )
        self._status_label.pack(pady=(20, 8), padx=20)

        self._bar = ctk.CTkProgressBar(self._win, width=380)
        self._bar.set(0)
        self._bar.pack(pady=(0, 20), padx=20)

        mgr = UpdateManager(get_game_dir(), self._on_progress)
        t = threading.Thread(target=self._run_thread, args=(mgr,), daemon=True)
        t.start()

    def _on_progress(self, status: str, fraction: float) -> None:
        if self._win is None:
            return
        self._win.after(0, lambda: self._status_label.configure(text=status))
        self._win.after(0, lambda: self._bar.set(fraction))

    def _run_thread(self, mgr: UpdateManager) -> None:
        try:
            mgr.check_and_update()
            self._win.after(2000, self._win.destroy)
        except UpdateError as e:
            err_msg = str(e)  # capture before except block exits (Python 3 deletes `e` after)
            self._win.after(0, lambda: self._show_error(err_msg))

    def _show_error(self, msg: str) -> None:
        self._status_label.configure(text=f"Error: {msg}")
        self._bar.configure(progress_color="red")
        ctk.CTkButton(self._win, text="Close", command=self._win.destroy).pack(pady=8)
```

- [ ] **Step 2: Verify tests still pass**

```bash
python -m pytest tests/test_updater.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add launcher.py
git commit -m "feat: add ProgressModal with threaded update and error display"
```

---

### Task 5: App window + entry point

**Files:**
- Modify: `launcher.py` (append App class and `__main__` block)

**Interfaces:**
- Consumes:
  - `get_game_dir() -> str` from Task 2
  - `get_asset_path(filename: str) -> str` from Task 2
  - `TrayManager(on_restore, on_quit)` from Task 3
  - `ProgressModal(parent)` from Task 4

- [ ] **Step 1: Append App class and entry point to launcher.py**

```python
# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("GoldenEye Recomp Launcher")
        self.geometry("600x320")
        self.resizable(False, False)

        self._tray = TrayManager(on_restore=self._restore, on_quit=self._quit)
        self.protocol("WM_DELETE_WINDOW", self._do_quit)

        self._build_ui()

    def _build_ui(self) -> None:
        banner_path = get_asset_path("banner.png")
        banner_img = ctk.CTkImage(
            light_image=Image.open(banner_path),
            dark_image=Image.open(banner_path),
            size=(600, 220),
        )
        banner_label = ctk.CTkLabel(self, image=banner_img, text="")
        banner_label.pack()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkButton(
            btn_frame,
            text="Launch Game",
            width=260,
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._launch_game,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Update ReComp Engine",
            width=260,
            height=44,
            font=("Segoe UI", 14, "bold"),
            fg_color="#2a5e2a",
            hover_color="#1e441e",
            command=self._start_update,
        ).pack(side="left")

    def _launch_game(self) -> None:
        game_exe = os.path.join(get_game_dir(), "GoldenEye.exe")
        if not os.path.exists(game_exe):
            self._show_error("GoldenEye.exe not found in launcher directory.")
            return
        subprocess.Popen([game_exe], cwd=get_game_dir())
        self._to_tray()

    def _start_update(self) -> None:
        ProgressModal(self).run_update()

    def _to_tray(self) -> None:
        self.withdraw()
        self._tray.show()

    def _restore(self) -> None:
        # Called from pystray thread - dispatch tkinter ops to main thread
        self.after(0, self._do_restore)

    def _do_restore(self) -> None:
        self._tray.hide()
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit(self) -> None:
        # Called from pystray thread - dispatch tkinter ops to main thread
        self.after(0, self._do_quit)

    def _do_quit(self) -> None:
        self._tray.hide()
        self.destroy()

    def _show_error(self, msg: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.geometry("360x120")
        win.resizable(False, False)
        win.grab_set()
        ctk.CTkLabel(win, text=msg, wraplength=320, font=("Segoe UI", 12)).pack(pady=20, padx=20)
        ctk.CTkButton(win, text="OK", command=win.destroy).pack(pady=4)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
```

- [ ] **Step 2: Verify tests still pass**

```bash
python -m pytest tests/test_updater.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add launcher.py
git commit -m "feat: add App window with banner, launch game, update engine, tray minimize"
```

---

### Task 6: Build portable exe (Windows)

> **Note:** This task must run on a Windows machine with Python 3.11+ installed. Copy the project directory to Windows first, or run via WSL with a Windows Python install.

**Files:**
- No new source files

- [ ] **Step 1: Install dependencies**

```bat
pip install -r requirements.txt
```

Expected: All packages install without error.

- [ ] **Step 2: Run build**

Run from the game directory (`GoldenEye-Release-Win\`) where `banner.png` lives:

```bat
build.bat
```

Expected output ends with:
```
Building EXE from EXE-00.toc completed successfully.
Build complete. Output in dist\
```

- [ ] **Step 3: Copy exe to game directory**

```bat
copy "dist\GoldenEye Launcher.exe" "."
```

- [ ] **Step 4: Manual smoke test**

Double-click `GoldenEye Launcher.exe` and verify:

1. Window opens at 600x320, dark theme
2. banner.png displays full-width at top
3. "Launch Game" and "Update ReComp Engine" buttons visible side by side
4. Click "Launch Game" - GoldenEye.exe launches, window minimizes to tray
5. Tray icon appears, right-click shows Restore / Quit
6. Double-click tray icon - window restores
7. Click "Update ReComp Engine" - progress modal opens
8. Modal shows status label and progress bar, updates live
9. If already up to date: modal shows "Already up to date." and closes after 2s
10. If update available: modal shows download %, then "Extracting...", then "Update complete!" and closes

- [ ] **Step 5: Commit exe (optional)**

If you want the binary in git:

```bash
git add "GoldenEye Launcher.exe"
git commit -m "build: add compiled GoldenEye Launcher exe"
```

If not, add to `.gitignore`:
```
dist/
build/
*.spec
GoldenEye Launcher.exe
```
