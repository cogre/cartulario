@echo off
chcp 65001 >nul
title cartulario
cd /d "%~dp0"
python cartulario.py %*
echo.
pause
