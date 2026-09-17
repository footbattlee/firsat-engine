@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ROOT=C:\firsat-engine\firsat-engine-main"
set "PYTHON=C:\firsat-engine\.venv\Scripts\python.exe"
if "%SUPABASE_SERVICE_ROLE_KEY%"=="" (
  echo HATA: SUPABASE_SERVICE_ROLE_KEY tanimli degil.
  exit /b 2
)
cd /d "%ROOT%"
"%PYTHON%" run_creative_generator.py
exit /b %ERRORLEVEL%
