@echo off
setlocal
title Medari Live Kit
cd /d "%~dp0"

rem  Python version installed automatically when none is found (per-user, no admin needed)
set "PY_VER=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
set "PY_LOCAL=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "OKTEST=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"

rem ---------------------------------------------------------------------------
rem 1. Find a Python 3.10+ (skips the fake "python" that opens Microsoft Store)
rem ---------------------------------------------------------------------------
set "PY="
call :try "%PY_LOCAL%"
if not defined PY call :trycmd py -3
if not defined PY call :trycmd python
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :try "%%D\python.exe"
if not defined PY for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PY call :try "%%D\python.exe"
if defined PY goto :have_python

rem ---------------------------------------------------------------------------
rem 2. None found: download and install Python for this Windows user
rem ---------------------------------------------------------------------------
echo.
echo  Python belum terpasang. Sekarang memasang Python %PY_VER%.
echo  Ini hanya sekali dan butuh 2-5 menit. Mohon tunggu ...
echo.
set "PY_SETUP=%TEMP%\python-%PY_VER%-setup.exe"
curl.exe -L --fail -s -o "%PY_SETUP%" "%PY_URL%"
if errorlevel 1 powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing '%PY_URL%' -OutFile '%PY_SETUP%'"
if not exist "%PY_SETUP%" (
  echo  Python tidak bisa diunduh. Periksa koneksi internet lalu coba lagi.
  goto :fail
)
"%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0 Shortcuts=0
del "%PY_SETUP%" >nul 2>nul
call :try "%PY_LOCAL%"
if not defined PY (
  echo  Pemasangan Python belum selesai. Jalankan file ini sekali lagi,
  echo  atau pasang Python dari https://www.python.org/downloads/
  goto :fail
)
echo  Python sudah terpasang.

:have_python
rem ---------------------------------------------------------------------------
rem 3. Private environment for the app (rebuilt if copied from another PC)
rem ---------------------------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "%OKTEST%" >nul 2>nul || rmdir /s /q ".venv"
)
if not exist ".venv\Scripts\python.exe" (
  echo  Pertama kali dibuka: menyiapkan aplikasi, butuh sekitar satu menit ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" -c "import flask, PIL, pymupdf, numpy, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
  echo  Memasang paket yang dibutuhkan ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r app\requirements.txt
  if errorlevel 1 goto :fail
)

rem ---------------------------------------------------------------------------
rem 4. Start the app (opens the browser)
rem ---------------------------------------------------------------------------
".venv\Scripts\python.exe" app\main.py
exit /b 0

rem ---- helpers ----------------------------------------------------------------
:try
if exist "%~1" "%~1" -c "%OKTEST%" >nul 2>nul && set "PY="%~1""
exit /b 0

:trycmd
where %1 >nul 2>nul || exit /b 0
%* -c "%OKTEST%" >nul 2>nul && set "PY=%*"
exit /b 0

:fail
echo.
echo  Ada masalah saat menyiapkan aplikasi.
echo  Periksa koneksi internet lalu klik dua kali file ini lagi.
echo.
pause
exit /b 1
