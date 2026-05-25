@echo off
REM Build AETHER HE as a one-folder Windows distribution + zip it for sharing.
REM Output:  dist\AetherHE\AetherHE.exe   (run directly, no Python needed)
REM          dist\AetherHE-windows.zip    (shareable bundle)
setlocal
cd /d "%~dp0"

if not exist venv-web\Scripts\python.exe (
  echo [!] venv-web is missing. Run:  py -3.12 -m venv venv-web ^&^& venv-web\Scripts\pip install -r requirements.txt pyinstaller
  exit /b 1
)

echo === Rebuilding UI runtime ===
venv-web\Scripts\python.exe ui\runtime_src\build_runtime.py || exit /b 1

echo === Running PyInstaller ===
venv-web\Scripts\pyinstaller.exe --clean --noconfirm AetherHE.spec || exit /b 1

echo === Zipping dist\AetherHE -^> dist\AetherHE-windows.zip ===
if exist dist\AetherHE-windows.zip del dist\AetherHE-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path dist\AetherHE\* -DestinationPath dist\AetherHE-windows.zip -Force" || exit /b 1

echo.
echo Done.  Launch: dist\AetherHE\AetherHE.exe
endlocal
