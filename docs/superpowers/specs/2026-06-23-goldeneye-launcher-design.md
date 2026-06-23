# GoldenEye Recomp Launcher - Design Spec

**Date:** 2026-06-23

## Summary

A Windows-only portable launcher for GoldenEye Recomp. Distributed as a single `.exe` (PyInstaller one-file). Sits alongside `GoldenEye.exe` in the game directory. Provides two actions: launch the game and update the ReComp engine from GitHub releases.

## Architecture

Single-file Python app (`launcher.py`), class-based, compiled to one portable `.exe`.

```
launcher.py
  App            - CTk root window, banner, buttons
  ProgressModal  - CTkToplevel, progress bar, background thread
  TrayManager    - pystray icon, Restore/Quit menu
  UpdateManager  - GitHub API, download, extract
```

## Components

### App (main window)

- CustomTkinter root window, dark theme
- Fixed size: 600x320
- Title: "GoldenEye Recomp Launcher"
- No resize
- Top: `banner.png` displayed full-width
- Bottom: two buttons side by side
  - "Launch Game" - runs `GoldenEye.exe` from same dir as launcher, then minimizes to tray
  - "Update ReComp Engine" - opens ProgressModal

### ProgressModal

- CTkToplevel (modal, blocks parent interaction)
- Status label (e.g. "Checking for updates...", "Downloading...", "Extracting...")
- CTkProgressBar (determinate during download, indeterminate during extract)
- Runs update on a `threading.Thread` so UI stays responsive
- On success: status label changes to "Update complete!", auto-closes after 2s
- On "already up to date": shows message, auto-closes after 2s
- On error: shows error message, adds Close button

### TrayManager

- Uses `pystray` with `PIL` icon (banner.png resized to 64x64)
- System tray icon appears when game is launched
- Right-click menu: "Restore" (show window), "Quit" (exit app)
- Double-click tray icon: restore window

### UpdateManager

- `GET https://api.github.com/repos/SunJaycy/GoldenEye-Recomp/releases/latest`
- Reads `version.txt` in game dir for currently installed version tag
- Compares `tag_name` from API response to stored version
- If up to date: report "Already up to date"
- If update available:
  - Find first `.zip` asset in release assets
  - Stream-download with `requests`, report progress via callback (bytes received / total)
  - Extract zip to game directory (same dir as launcher), overwriting existing files
  - Write new `tag_name` to `version.txt`
  - Report complete

## File Layout

```
GoldenEye-Release-Win/
  GoldenEye.exe          - game binary (launched by launcher)
  banner.png             - bundled into launcher exe, also used as tray icon source
  version.txt            - written/read by UpdateManager (auto-created if missing)
  GoldenEye Launcher.exe - compiled output
  ge.toml                - game config (untouched by launcher)
  assets/                - game assets (untouched by launcher)
```

## Build

```
pyinstaller --onefile --windowed --name "GoldenEye Launcher" \
  --add-data "banner.png;." launcher.py
```

`banner.png` is accessed at runtime via `sys._MEIPASS` when running from the compiled exe.

## Dependencies

- `customtkinter` - modern dark UI widgets
- `Pillow` - image loading for banner and tray icon
- `requests` - GitHub API + file download
- `pystray` - Windows system tray integration

## Error Handling

- Game exe not found: show error dialog, do not launch
- No internet / GitHub API fail: show error in modal
- Download interrupted: show error, do not write version.txt
- Zip extract fail: show error, do not write version.txt
- `version.txt` missing: treat as "no version installed", force update check

## Out of Scope

- Settings UI (ge.toml editing)
- Multiple game profiles
- Auto-update of the launcher itself
- Linux/macOS support
