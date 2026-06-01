@echo off
REM DailyTechFlow pipeline launcher. Invoked by Windows Task Scheduler.
REM ASCII-only on purpose: non-ASCII chars in a .bat can be mis-parsed under
REM the scheduler's code page and abort the script. Keep this file ASCII.
REM %~dp0 changes to the script's own dir so config.yaml / prompts / output resolve.
cd /d "%~dp0"
"C:\Python314\python.exe" main.py >> "logs\cron.out" 2>&1
