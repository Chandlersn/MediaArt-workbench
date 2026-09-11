@echo off
chcp 65001 >nul
echo ========================================
echo 媒体艺术展览工作台 - 开发环境启动
echo ========================================
echo.
echo 正在启动 Python 后端服务...
start "Python Server" cmd /k "python server.py"
timeout /t 2 /nobreak >nul
echo.
echo 正在启动 Vite 开发服务器...
echo 前端地址: http://localhost:3000
echo 后端地址: http://localhost:8080
echo.
npm run dev
