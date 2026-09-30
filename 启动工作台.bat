@echo off
chcp 65001 >nul
title 媒体艺术智能工作台
cd /d "%~dp0"

REM ============================================================
REM  本地一键启动（个人单机使用）
REM  真正的逻辑在 scripts\launch.py —— 这里只负责找到可用的 Python。
REM  查找顺序：项目自带虚拟环境 > PATH 里的 python > py 启动器。
REM ============================================================

set "PY="

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    goto :found
)

python --version >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto :found
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto :found
)

echo.
echo  [x] 未找到 Python。
echo.
echo      本工作台需要 Python 3.8 或更高版本。
echo      请从 https://www.python.org/downloads/ 安装，
echo      安装时务必勾选 "Add Python to PATH"，然后重新双击本文件。
echo.
pause
exit /b 1

:found
%PY% "scripts\launch.py"

REM 启动器异常退出时停住，让用户看清报错原因
if errorlevel 1 (
    echo.
    pause
)
