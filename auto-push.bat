@echo off
REM Double-click this file to start auto-pushing changes to GitHub.
REM Keep the window open; close it (or Ctrl+C) to stop.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto-push.ps1"
pause
