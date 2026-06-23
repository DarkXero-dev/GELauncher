import os
import sys
import shutil
import threading
import subprocess
import tempfile
import requests
import customtkinter as ctk
from PIL import Image, ImageTk
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

        rar_url = self._find_rar_url(release["assets"])
        rar_path = self._download(rar_url, remote_tag)
        try:
            self._extract_rar(rar_path)
        finally:
            if os.path.exists(rar_path):
                os.remove(rar_path)
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

    def _find_rar_url(self, assets: list) -> str:
        for asset in assets:
            if asset["name"] == "GoldenEye-Recomp-Win.rar":
                return asset["browser_download_url"]
        for asset in assets:
            if asset["name"].endswith(".rar"):
                return asset["browser_download_url"]
        raise UpdateError("No RAR asset found in release.")

    def _download(self, url: str, tag: str) -> str:
        self.progress(f"Downloading {tag}...", 0.0)
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".rar")
            try:
                received = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    tmp.write(chunk)
                    received += len(chunk)
                    if total:
                        self.progress(f"Downloading {tag}...", received / total)
                tmp.close()
                return tmp.name
            except Exception:
                tmp.close()
                os.unlink(tmp.name)
                raise
        except UpdateError:
            raise
        except Exception as e:
            raise UpdateError(f"Download failed: {e}")

    def _extract_rar(self, rar_path: str) -> None:
        self.progress("Extracting...", 0.0)
        tmp_dir = tempfile.mkdtemp()
        try:
            self._run_extractor(rar_path, tmp_dir)
            self._copy_files(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _run_extractor(self, rar_path: str, dest_dir: str) -> None:
        candidates = [
            ["7z", "x", rar_path, f"-o{dest_dir}", "-y"],
            [r"C:\Program Files\7-Zip\7z.exe", "x", rar_path, f"-o{dest_dir}", "-y"],
            [r"C:\Program Files (x86)\7-Zip\7z.exe", "x", rar_path, f"-o{dest_dir}", "-y"],
            ["unrar", "x", "-y", rar_path, dest_dir + os.sep],
            [r"C:\Program Files\WinRAR\UnRAR.exe", "x", "-y", rar_path, dest_dir + os.sep],
            [r"C:\Program Files\WinRAR\WinRAR.exe", "x", "-y", rar_path, dest_dir + os.sep],
        ]
        for cmd in candidates:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                if result.returncode == 0:
                    return
            except FileNotFoundError:
                continue
        raise UpdateError(
            "No extraction tool found. Install 7-Zip (7-zip.org) or WinRAR to enable updates."
        )

    def _copy_files(self, src_dir: str) -> None:
        # Strip single top-level directory if present (e.g. GoldenEye-Recomp-Win/)
        entries = os.listdir(src_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(src_dir, entries[0])):
            src_dir = os.path.join(src_dir, entries[0])

        # Count files to copy (excluding assets/)
        total = sum(
            len(files)
            for root, dirs, files in os.walk(src_dir)
            if os.path.relpath(root, src_dir).split(os.sep)[0].lower() != "assets"
        )

        copied = 0
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d.lower() != "assets"]
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, src_dir)
                dest = os.path.join(self.game_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                copied += 1
                self.progress("Extracting...", copied / max(total, 1))


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
        img = Image.open(get_asset_path("icon.png")).resize((64, 64))
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


# ---------------------------------------------------------------------------
# ProgressModal
# ---------------------------------------------------------------------------

class ProgressModal:
    def __init__(self, parent: ctk.CTk, on_close: Optional[Callable[[], None]] = None):
        self._parent = parent
        self._on_close = on_close
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

        self._parent._updating = True
        mgr = UpdateManager(get_game_dir(), self._on_progress)
        t = threading.Thread(target=self._run_thread, args=(mgr,), daemon=True)
        t.start()

    def _on_progress(self, status: str, fraction: float) -> None:
        try:
            if self._win is None or not self._win.winfo_exists():
                return
            self._win.after(0, lambda: self._status_label.configure(text=status))
            self._win.after(0, lambda: self._bar.set(fraction))
        except Exception:
            pass

    def _close_modal(self) -> None:
        if self._on_close:
            self._on_close()
        if self._win is not None and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    def _run_thread(self, mgr: UpdateManager) -> None:
        try:
            mgr.check_and_update()
            self._win.after(2000, self._close_modal)
        except UpdateError as e:
            err_msg = str(e)
            self._win.after(0, lambda: self._show_error(err_msg))

    def _show_error(self, msg: str) -> None:
        self._status_label.configure(text=f"Error: {msg}")
        self._bar.configure(progress_color="red")
        ctk.CTkButton(self._win, text="Close", command=self._close_modal).pack(pady=8)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("GoldenEye Recomp Launcher")
        self._icon_img = ImageTk.PhotoImage(Image.open(get_asset_path("icon.png")))
        self.iconphoto(True, self._icon_img)
        self.geometry("600x320")
        self.resizable(False, False)

        self._tray = TrayManager(on_restore=self._restore, on_quit=self._quit)
        self._active_modal: Optional[ProgressModal] = None
        self._updating: bool = False
        self.protocol("WM_DELETE_WINDOW", self._do_quit)

        self._build_ui()

    def _build_ui(self) -> None:
        banner_path = get_asset_path("banner.png")
        self._banner_img = ctk.CTkImage(
            light_image=Image.open(banner_path),
            dark_image=Image.open(banner_path),
            size=(600, 220),
        )
        self._banner_label = ctk.CTkLabel(self, image=self._banner_img, text="")
        self._banner_label.pack()

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
        if self._active_modal is not None:
            return
        self._active_modal = ProgressModal(self, on_close=self._on_modal_close)
        self._active_modal.run_update()

    def _on_modal_close(self) -> None:
        self._updating = False
        self._active_modal = None

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
        if getattr(self, "_updating", False):
            self._show_error("Update in progress. Please wait for it to complete.")
            return
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
