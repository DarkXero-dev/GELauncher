#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "==> Setting up venv..."
python -m venv .venv --system-site-packages
source .venv/bin/activate

echo "==> Installing Python deps..."
# System packages (Pillow, customtkinter) are inherited via --system-site-packages
# Only install what's not available system-wide
pip install -q requests pystray pyinstaller

echo "==> Building binary with PyInstaller..."
pyinstaller \
  --onefile \
  --name "GoldenEye Launcher" \
  --add-data "banner.png:." \
  --add-data "icon.png:." \
  --hidden-import=tkinter \
  --hidden-import=_tkinter \
  --hidden-import=PIL._tkinter_finder \
  --collect-all=customtkinter \
  launcher.py

echo "==> Creating AppDir..."
rm -rf AppDir
mkdir -p AppDir/usr/bin
cp "dist/GoldenEye Launcher" "AppDir/usr/bin/GoldenEye Launcher"
cp icon.png "AppDir/GoldenEye Launcher.png"

cat > "AppDir/GoldenEye Launcher.desktop" << 'EOF'
[Desktop Entry]
Name=GoldenEye Launcher
Exec=GoldenEye Launcher
Icon=GoldenEye Launcher
Type=Application
Categories=Game;
EOF

cat > AppDir/AppRun << 'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/GoldenEye Launcher" "$@"
APPRUN
chmod +x AppDir/AppRun

echo "==> Fetching appimagetool..."
if ! command -v appimagetool &>/dev/null; then
  wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O /tmp/appimagetool
  chmod +x /tmp/appimagetool
  APPIMAGETOOL="/tmp/appimagetool"
else
  APPIMAGETOOL="appimagetool"
fi

echo "==> Building AppImage..."
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$APPIMAGETOOL" AppDir "GoldenEye-Launcher.AppImage"

echo ""
echo "Done: $(pwd)/GoldenEye-Launcher.AppImage"
echo "Test: chmod +x GoldenEye-Launcher.AppImage && ./GoldenEye-Launcher.AppImage"
