@echo off
title Just Search — AI Poster Generator
cd /d "%~dp0"
echo.
echo  =============================================
echo   Just Search - AI Poster Generator
echo   Starting server at http://localhost:3000
echo  =============================================
echo.
timeout /t 2 /nobreak >nul
start "" "http://localhost:3000"
node server.js
pause
