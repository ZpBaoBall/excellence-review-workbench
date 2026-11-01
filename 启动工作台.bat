@echo off
title 卓越绩效评审工作台
cd /d "%~dp0"

REM ── 端口检测：已在运行则只开浏览器，不杀进程（避免顶掉用户已开的实例）──
netstat -ano | findstr ":8765 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo 工作台已在运行，正在打开浏览器...
    start "" http://127.0.0.1:8765
    exit /b
)

REM ── 解释器：本机 venv（若有）优先，否则用 PATH 里的 python ──
REM 首次使用请先装依赖：pip install -r requirements.txt
set "PYEXE=%LOCALAPPDATA%\zp-workbench\Scripts\python.exe"
if exist "C:\Users\10507777\.workbuddy\binaries\python\envs\zp-workbench\Scripts\python.exe" ^
    set "PYEXE=C:\Users\10507777\.workbuddy\binaries\python\envs\zp-workbench\Scripts\python.exe"

echo 正在启动工作台，浏览器将自动打开...
start "" http://127.0.0.1:8765
"%PYEXE%" app\main.py
pause
