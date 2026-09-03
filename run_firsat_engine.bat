@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM ================================================================
REM FIRSAT ENGINE - FULL MULTI CATEGORY RUNNER
REM 22 alt kategoriyi tarar ve run_pipeline.py akisini calistirir.
REM Supabase anahtari bu dosyaya yazilmaz; Windows ortam degiskeninden okunur.
REM ================================================================

set "ROOT=C:\firsat-engine\firsat-engine-main"
set "PYTHON=C:\firsat-engine\.venv\Scripts\python.exe"
set "LOGDIR=%ROOT%\logs"

if not exist "%ROOT%" (
    echo HATA: Proje klasoru bulunamadi: %ROOT%
    exit /b 2
)

if not exist "%PYTHON%" (
    echo HATA: Python bulunamadi: %PYTHON%
    exit /b 2
)

if "%SUPABASE_SERVICE_ROLE_KEY%"=="" (
    echo HATA: SUPABASE_SERVICE_ROLE_KEY ortam degiskeni tanimli degil.
    echo Anahtari bu BAT dosyasina yazmayin. Windows kullanici ortam degiskeni olarak tanimlayin.
    exit /b 2
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "LOGFILE=%LOGDIR%\pipeline_%STAMP%.log"

cd /d "%ROOT%"

REM CATEGORY_LIMIT ve CATEGORY_SLUG temizlenir; boylece tum aktif alt kategoriler calisir.
set "CATEGORY_LIMIT="
set "CATEGORY_SLUG="
set "PYTHONUNBUFFERED=1"

echo ================================================================
echo FIRSAT ENGINE BASLADI
echo Tarih: %date% %time%
echo Log: %LOGFILE%
echo ================================================================

echo ================================================================>>"%LOGFILE%"
echo FIRSAT ENGINE BASLADI>>"%LOGFILE%"
echo Tarih: %date% %time%>>"%LOGFILE%"
echo ================================================================>>"%LOGFILE%"

"%PYTHON%" run_pipeline.py >>"%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

echo.>>"%LOGFILE%"
echo ================================================================>>"%LOGFILE%"
echo FIRSAT ENGINE BITTI - CODE=%EXITCODE%>>"%LOGFILE%"
echo Tarih: %date% %time%>>"%LOGFILE%"
echo ================================================================>>"%LOGFILE%"

echo ================================================================
if "%EXITCODE%"=="0" (
    echo FIRSAT ENGINE TAMAMLANDI - OK
) else (
    echo FIRSAT ENGINE HATA ILE BITTI - CODE=%EXITCODE%
)
echo Log: %LOGFILE%
echo ================================================================

exit /b %EXITCODE%
