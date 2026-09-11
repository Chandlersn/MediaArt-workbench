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

echo 正在启动本地服务器...
start "工作台服务器" python server.py

REM 等待服务器启动
timeout /t 3 /nobreak >nul

echo 正在打开浏览器...
start "" "http://localhost:8080"

echo.
echo ========================================
echo  服务器已启动: http://localhost:8080
echo  素材目录: %~dp0assets
echo  归档目录: %~dp0MediaArt_Archives
echo.
echo  点击素材文件将使用本地软件打开
echo  关闭此窗口将停止服务器
echo ========================================
echo.
pause
