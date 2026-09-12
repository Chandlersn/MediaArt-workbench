@echo off
chcp 65001 >nul
title 媒体艺术展览智能工作台
echo.
echo ========================================
echo    媒体艺术展览智能工作台
echo    正在启动...
echo ========================================
echo.
cd /d "%~dp0"

REM 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请确保已安装 Python 并添加到系统环境变量
    echo.
    pause
    exit /b 1
)

REM 检查 Node 是否可用（前端开发服务器需要）
node --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Node.js，前端需要 Node.js 环境
    echo.
    pause
    exit /b 1
)

echo 正在启动后端服务 (端口 8080)...
start "工作台后端" cmd /k "python -m server.main"

echo 正在启动前端服务 (端口 3004)...
start "工作台前端" cmd /k "npm run dev"

REM 等待服务启动
timeout /t 4 /nobreak >nul

echo 正在打开浏览器...
start "" "http://localhost:3004"

echo.
echo ========================================
echo  后端已启动: http://localhost:8080
echo  前端已启动: http://localhost:3004
echo  默认账号:   admin / admin123
echo.
echo  关闭「工作台后端 / 工作台前端」窗口将停止对应服务
echo ========================================
echo.
pause
