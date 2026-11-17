@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0interfaz\iniciar.ps1"
if errorlevel 1 pause
