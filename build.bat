@echo off
pyinstaller --onefile --windowed --name "GoldenEye Launcher" --icon "icon.png" --add-data "banner.png;." --add-data "icon.png;." launcher.py
echo Build complete. Output in dist\
pause
