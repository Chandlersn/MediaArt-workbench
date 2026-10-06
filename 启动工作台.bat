@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title 媒体艺术智能工作台
cd /d "%~dp0"

REM ============================================================
REM  本地一键启动（个人单机使用）
REM  真正的逻辑在 scripts\launch.py —— 这里只负责找到可用的 Python。
REM  每个候选都实际运行代码；不能只凭文件存在或 --version 选中商店占位程序。
REM ============================================================

set "PYTHON_EXE="
set "PYTHON_ARGS="

if defined WORKBENCH_PYTHON (
    call :try_python "%WORKBENCH_PYTHON%"
    if not errorlevel 1 goto :found
)

call :try_python "%~dp0.venv\Scripts\python.exe"
if not errorlevel 1 goto :found

for %%P in ("%USERPROFILE%\.local\bin\python*.exe") do (
    call :try_python "%%~fP"
    if not errorlevel 1 goto :found
)

for /f "delims=" %%P in ('where python.exe python3.exe 2^>nul') do (
    call :try_python "%%P"
    if not errorlevel 1 goto :found
)

for /f "delims=" %%P in ('where py.exe 2^>nul') do (
    call :try_python "%%P" "-3"
    if not errorlevel 1 goto :found
)

for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    call :try_python "%%~fP\python.exe"
    if not errorlevel 1 goto :found
)

if defined ACCIO_PYTHON_PATH (
    call :try_python "%ACCIO_PYTHON_PATH%"
    if not errorlevel 1 goto :found
)
for /d %%P in ("%APPDATA%\Accio\pre-install\*") do (
    call :try_python "%%~fP\python\python.exe"
    if not errorlevel 1 goto :found
)

echo.
echo  [x] 未找到能运行代码的 Python 3.8+。
echo.
echo      本工作台需要 Python 3.8 或更高版本。
echo      请从 https://www.python.org/downloads/ 安装，
echo      安装时务必勾选 "Add Python to PATH"，然后重新双击本文件。
echo      也可将 WORKBENCH_PYTHON 设置为 python.exe 的完整路径。
echo.
if /i "%~1"=="--check-python" exit /b 1
pause
exit /b 1

:found
REM  诊断模式只打印解释器路径，不启动服务、不安装依赖。
if /i "%~1"=="--check-python" (
    "%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; print(sys.executable)"
    exit /b
)

"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0scripts\launch.py"
set "LAUNCH_EXIT_CODE=%errorlevel%"

REM 启动器异常退出时停住，让用户看清报错原因
if not "%LAUNCH_EXIT_CODE%"=="0" (
    echo.
    pause
)
exit /b %LAUNCH_EXIT_CODE%

:try_python
REM  跳过常见的 Microsoft Store 执行别名，避免唤起商店窗口。
echo "%~1" | findstr /i /l /c:"\Microsoft\WindowsApps" >nul
if not errorlevel 1 exit /b 1
"%~1" %~2 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS=%~2"
exit /b 0
