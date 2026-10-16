@echo off
cd /d "%~dp0"
echo Building FireMedia for Windows. Internet access is required.
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\fetch-playback.ps1
if errorlevel 1 goto failed
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build.ps1
if errorlevel 1 goto failed
echo.
echo Done. Open dist\FireMedia\FireMedia.exe to test.
pause
exit /b 0
:failed
echo.
echo Build stopped. See the error above. Python 3.12 x64 must be installed.
pause
exit /b 1
