@echo off
chcp 65001 >nul
echo ========================================
echo 媒体艺术展览工作台 - 生产构建
echo ========================================
echo.
echo 正在构建前端资源...
call npm run build
if %errorlevel% neq 0 (
    echo.
    echo 构建失败！
    pause
    exit /b 1
)
echo.
echo 前端构建完成！
echo.
echo 正在打包 Electron 应用...
call npm run build:win
if %errorlevel% neq 0 (
    echo.
    echo 打包失败！
    pause
    exit /b 1
)
echo.
echo ========================================
echo 构建完成！
echo ========================================
pause
