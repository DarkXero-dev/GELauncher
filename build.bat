@echo off
pyinstaller --onefile --windowed --name "GoldenEye Launcher" --add-data "banner.png;." launcher.py
echo Build complete. Output in dist\
pause
