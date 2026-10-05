@echo off
REM ============================================================
REM  start-nate.bat -- launch Nate (5-mode server)
REM ============================================================
setlocal

set NATE_ROOT=D:\Nate
set SERVER_DIR=%NATE_ROOT%\server

echo.
echo  ==============================================
echo   NATE -- local AI tool librarian
echo  ==============================================
echo.

REM --- 1. sanity checks ---
if not exist "%SERVER_DIR%\server.py" (
    echo [ERROR] server.py not found at %SERVER_DIR%\server.py
    echo         Check that D:\Nate is the repo root.
    pause
    exit /b 1
)

if not exist "%NATE_ROOT%\nate.html" (
    echo [WARN] nate.html not found at %NATE_ROOT%\nate.html
)

REM --- 2. is Ollama up? ---
echo [1/3] Checking Ollama...
where ollama >nul 2>nul
if errorlevel 1 (
    echo       [WARN] 'ollama' not on PATH. Will try anyway.
) else (
    ollama list >nul 2>nul
    if errorlevel 1 (
        echo       [ERROR] Ollama not responding. Start Ollama first.
        echo               Then re-run this script.
        pause
        exit /b 1
    )
    echo       OK -- Ollama is up.
)

REM --- 3. is port 5000 already taken? ---
echo [2/3] Checking port 5000...
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo       [WARN] Something is already listening on port 5000.
    echo              Run stop-nate.bat first, or close the other window.
    pause
    exit /b 1
)
echo       OK -- port 5000 is free.

REM --- 4. launch ---
echo [3/3] Starting server...
echo.
cd /d "%SERVER_DIR%"
python server.py

REM --- on exit ---
echo.
echo  Nate stopped.
pause
endlocal