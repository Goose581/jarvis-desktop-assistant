@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "REPORT=%~dp0ollama-diagnostic.txt"
(
  echo J.A.R.V.I.S. Ollama diagnostics
  echo Date: %DATE% %TIME%
  echo Computer: %COMPUTERNAME%
  echo.
  echo === OLLAMA_HOST ===
  if defined OLLAMA_HOST (echo %OLLAMA_HOST%) else (echo Not set; default local endpoint is used.)
  echo.
  echo === Ollama executable ===
  where ollama
  echo.
  echo === Ollama version ===
  ollama --version
  echo.
  echo === Installed models ===
  ollama list
  echo.
  echo === Local API checks (direct connection) ===
  echo localhost:
  curl.exe --noproxy "*" --connect-timeout 3 --max-time 5 -sS "http://localhost:11434/api/tags"
  echo.
  echo IPv4 loopback:
  curl.exe --noproxy "*" --connect-timeout 3 --max-time 5 -sS "http://127.0.0.1:11434/api/tags"
  echo.
  echo IPv6 loopback:
  curl.exe --noproxy "*" --connect-timeout 3 --max-time 5 -sS "http://[::1]:11434/api/tags"
  echo.
  echo === J.A.R.V.I.S. settings ===
  if exist "%LOCALAPPDATA%\JARVIS\settings.json" (type "%LOCALAPPDATA%\JARVIS\settings.json") else (echo No settings.json found.)
  echo.
  echo === Recent J.A.R.V.I.S. log ===
  if exist "%LOCALAPPDATA%\JARVIS\jarvis.log" (powershell -NoProfile -Command "Get-Content -LiteralPath '%LOCALAPPDATA%\JARVIS\jarvis.log' -Tail 60") else (echo No jarvis.log found.)
) > "%REPORT%" 2>&1

echo.
echo Diagnostics saved to:
echo %REPORT%
echo.
type "%REPORT%"
echo.
echo Review the report for personal paths before sharing it.
pause
endlocal
