@echo off
echo Stopping any process listening on port 5000...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo Done.
timeout /t 2 >nul