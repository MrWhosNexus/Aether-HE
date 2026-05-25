@echo off
REM Launch the AETHER HE Keyboard Hub on Windows (Edge WebView2 + pywebview).
cd /d "%~dp0"
venv-web\Scripts\python.exe app_web.py %*
