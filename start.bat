@echo off
chcp 65001 >nul
title Order Flow Trading Agent
cd /d "%~dp0"
powershell -Command "Unblock-File '%~dp0run_trading_agent.ps1' 2>nul"
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0run_trading_agent.ps1"
pause
