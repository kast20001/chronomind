@echo off
cd /d "%~dp0"
echo ChronoMind - local server
py -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Install Python from https://www.python.org/downloads/ and run again.
  pause
  exit /b 1
)
echo Open in browser: http://127.0.0.1:5000
echo Stop server: Ctrl+C
py agent.py
