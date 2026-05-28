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

if not exist vendor\ViGEmBus_Setup.exe (
  echo === Downloading ViGEmBus_Setup.exe ===
  if not exist vendor mkdir vendor
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe' -OutFile 'vendor\ViGEmBus_Setup.exe'" || exit /b 1
)

echo === Rebuilding UI runtime ===
venv-web\Scripts\python.exe ui\runtime_src\build_runtime.py || exit /b 1

echo === Running PyInstaller ===
venv-web\Scripts\pyinstaller.exe --clean --noconfirm AetherHE.spec || exit /b 1

echo === Zipping dist\AetherHE -^> dist\AetherHE-windows.zip ===
if exist dist\AetherHE-windows.zip del dist\AetherHE-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path dist\AetherHE\* -DestinationPath dist\AetherHE-windows.zip -Force" || exit /b 1

REM === Inno Setup: produce the real installer (single-file setup .exe with
REM shortcuts, Add/Remove entry, ViGEmBus driver install on first run).
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  echo === Building installer with Inno Setup ===
  "%ISCC%" installer.iss || exit /b 1
  echo Installer: dist\AetherHE-Setup.exe
) else (
  echo [!] Inno Setup 6 not found. Install it ^(winget install JRSoftware.InnoSetup^) and re-run to get dist\AetherHE-Setup.exe.
)

echo.
echo Done.
echo   Folder app:   dist\AetherHE\AetherHE.exe
echo   Shareable:    dist\AetherHE-windows.zip
echo   Installer:    dist\AetherHE-Setup.exe
endlocal
