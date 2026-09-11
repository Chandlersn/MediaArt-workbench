@echo off
chcp 65001 >nul
echo ========================================
echo   媒体艺术展览工作台 - 打包构建
echo ========================================
echo.

echo [1/3] 检查Node.js环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未安装Node.js，请先安装Node.js
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)
echo Node.js 已安装

echo.
echo [2/3] 安装依赖包...
call npm install
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo 依赖安装完成

echo.
echo [3/3] 开始构建安装包...
call npm run build:win
if errorlevel 1 (
    echo [错误] 构建失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   构建完成！
echo ========================================
echo.
echo 安装包位置: dist\媒体艺术展览工作台 Setup 1.0.0.exe
echo.
pause
