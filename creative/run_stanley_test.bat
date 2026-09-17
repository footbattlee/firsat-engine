@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ROOT=C:\firsat-engine\firsat-engine-main"
set "PYTHON=C:\firsat-engine\.venv\Scripts\python.exe"
cd /d "%ROOT%"
"%PYTHON%" creative\test_renderer.py
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" exit /b %CODE%
echo.
echo Stanley creative hazir: %ROOT%\creative_output\stanley_smoke_test.png
exit /b 0
