@echo off
cd /d "%~dp0"
echo ===== ForexLab setup (one time only) =====
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed yet.
  echo Go to https://www.python.org/downloads/ , install it, and TICK the box
  echo "Add python.exe to PATH" on the first screen. Then double-click this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\activate.bat py -m venv .venv
call .venv\Scripts\activate.bat
echo Installing needed parts, please wait...
pip install -r requirements.txt
echo.
echo Running self-check...
python -m unittest discover -s tests -t .
echo.
echo If you see OK above, setup worked. Now double-click ForexLab.bat
pause
