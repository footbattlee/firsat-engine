@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ================================================================
REM FIRSAT ENGINE - FULL MULTI CATEGORY RUNNER
REM Tum aktif alt kategorileri ve firsat sayfalarini tarar.
REM Supabase anahtari .env veya Windows ortam degiskeninden okunur.
REM ================================================================

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "LOGDIR=%ROOT%\logs"

if not exist "%ROOT%" (
    echo HATA: Proje klasoru bulunamadi: %ROOT%
    exit /b 2
)

if not exist "%PYTHON%" (
    echo HATA: Python bulunamadi: %PYTHON%
    exit /b 2
)

cd /d "%ROOT%"
"%PYTHON%" -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); raise SystemExit(0 if os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip() else 1)"
if errorlevel 1 (
    echo HATA: SUPABASE_SERVICE_ROLE_KEY eksik veya Python paketleri kurulu degil.
    echo .env.example dosyasini .env olarak kopyalayin ve gerekli ayarlari tamamlayin.
    exit /b 2
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "LOGFILE=%LOGDIR%\pipeline_!STAMP!.log"

cd /d "%ROOT%"

REM CATEGORY_LIMIT ve CATEGORY_SLUG temizlenir; boylece tum aktif alt kategoriler calisir.
set "CATEGORY_LIMIT="
set "CATEGORY_SLUG="

REM Windows konsol/log encoding farklari collector'lari dusurmesin.
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo FIRSAT ENGINE BASLADI
echo Tarih: %date% %time%
echo Log: !LOGFILE!
echo ================================================================

echo ================================================================>>"!LOGFILE!"
echo FIRSAT ENGINE BASLADI>>"!LOGFILE!"
echo Tarih: %date% %time%>>"!LOGFILE!"
echo ================================================================>>"!LOGFILE!"

"%PYTHON%" run_pipeline.py >>"!LOGFILE!" 2>&1
set "EXITCODE=!ERRORLEVEL!"

REM ERRORLEVEL her durumda sayisal bir deger olmali; beklenmedik boslukta hata say.
if not defined EXITCODE set "EXITCODE=1"

echo.>>"!LOGFILE!"
echo ================================================================>>"!LOGFILE!"
echo FIRSAT ENGINE BITTI - CODE=!EXITCODE!>>"!LOGFILE!"
echo Tarih: %date% %time%>>"!LOGFILE!"
echo ================================================================>>"!LOGFILE!"

echo ================================================================
if "!EXITCODE!"=="0" (
    echo FIRSAT ENGINE TAMAMLANDI - OK
) else (
    echo FIRSAT ENGINE HATA ILE BITTI - CODE=!EXITCODE!
)
echo Log: !LOGFILE!
echo ================================================================

exit /b !EXITCODE!
