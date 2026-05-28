@echo off
:: 注册 DailyTechFlow 每天 03:30 自动运行的 Windows 任务计划
:: 需要以管理员身份运行

set TASK_NAME=DailyTechFlow
set PROJECT_DIR=I:\AI\DailyTechFlow
set PYTHON_EXE=C:\Python314\python.exe
set MAIN_SCRIPT=%PROJECT_DIR%\main.py
set RUN_TIME=03:30

echo 正在注册任务计划：%TASK_NAME%
echo   执行路径：%PYTHON_EXE% %MAIN_SCRIPT%
echo   触发时间：每天 %RUN_TIME%
echo.

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON_EXE%\" \"%MAIN_SCRIPT%\"" ^
  /sc daily ^
  /st %RUN_TIME% ^
  /sd 01/01/2026 ^
  /ru "%USERNAME%" ^
  /rl highest ^
  /f

if %errorlevel% equ 0 (
    echo.
    echo [OK] 任务计划注册成功。
    echo      可在「任务计划程序」中查看：%TASK_NAME%
) else (
    echo.
    echo [ERROR] 注册失败，请确认以管理员身份运行此脚本。
)

echo.
pause
