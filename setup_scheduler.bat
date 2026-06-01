@echo off
:: 注册 DailyTechFlow 自动运行的 Windows 任务计划
:: 周一~周六 03:30 运行；周日 22:10 运行（拆成两个周计划，覆盖七天不重叠）
:: 跑 run_pipeline.bat（内部会 cd 到项目目录、写日志），以当前登录用户身份、
:: 普通权限即可注册，无需管理员。任务在「用户登录时」运行。

set PROJECT_DIR=I:\AI\DailyTechFlow
set LAUNCHER=%PROJECT_DIR%\run_pipeline.bat
set CMD="\"%LAUNCHER%\""

echo 正在注册 DailyTechFlow 任务计划...
echo   执行：%LAUNCHER%
echo   周一~周六 03:30 ；周日 22:10
echo.

:: 删除旧的单一每日任务（不存在则忽略报错）
schtasks /delete /tn "DailyTechFlow" /f >nul 2>&1

:: 周一~周六 03:30
schtasks /create ^
  /tn "DailyTechFlow_MonSat" ^
  /tr %CMD% ^
  /sc weekly ^
  /d MON,TUE,WED,THU,FRI,SAT ^
  /st 03:30 ^
  /sd 01/01/2026 ^
  /f
set ERR1=%errorlevel%

:: 周日 22:10
schtasks /create ^
  /tn "DailyTechFlow_Sun" ^
  /tr %CMD% ^
  /sc weekly ^
  /d SUN ^
  /st 22:10 ^
  /sd 01/01/2026 ^
  /f
set ERR2=%errorlevel%

echo.
if %ERR1% equ 0 if %ERR2% equ 0 (
    echo [OK] 两个任务都注册成功。
    echo      DailyTechFlow_MonSat ^(周一~周六 03:30^)
    echo      DailyTechFlow_Sun    ^(周日 22:10^)
    echo      可在「任务计划程序」中查看。
    goto :end
)
echo [ERROR] 注册失败（MonSat=%ERR1% Sun=%ERR2%），请确认以管理员身份运行此脚本。

:end
echo.
pause
