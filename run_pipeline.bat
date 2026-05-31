@echo off
REM DailyTechFlow 流水线启动器。由 Windows 计划任务每天 3:30 调用。
REM 用 %~dp0 切到脚本所在目录，保证 config.yaml / prompts / output 等相对路径正确。
cd /d "%~dp0"
"C:\Python314\python.exe" main.py >> "logs\cron.out" 2>&1
