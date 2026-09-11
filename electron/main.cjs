const { app, BrowserWindow, Menu, shell, dialog, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let loadingWindow;
let pythonProcess;
let serverCheckInterval;

// 判断是否为开发模式
const isDev = !app.isPackaged;
// Vite 开发服务器端口（与 vite.config.js server.port 保持一致）
const VITE_DEV_SERVER_PORT = 3004;
// Python 后端端口
const PYTHON_SERVER_PORT = 8080;

function getServerPath() {
    if (app.isPackaged) {
        const serverPath = path.join(process.resourcesPath, 'server', 'main.py');
        console.log('Server path:', serverPath);
        return serverPath;
    }
    return path.join(__dirname, '..', 'server', 'main.py');
}

function getBasePath() {
    if (app.isPackaged) {
        console.log('Resources path:', process.resourcesPath);
        return process.resourcesPath;
    }
    return path.join(__dirname, '..');
}

function createLoadingWindow() {
    loadingWindow = new BrowserWindow({
        width: 400,
        height: 220,
        frame: false,
        transparent: true,
        resizable: false,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: false,      // 禁止渲染进程访问 Node.js
            contextIsolation: true,      // 启用上下文隔离
            sandbox: true                // 启用沙箱
        }
    });

    loadingWindow.loadURL(`data:text/html,
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    border-radius: 12px;
                }
                .container {
                    text-align: center;
                    color: white;
                }
                .spinner {
                    width: 36px;
                    height: 36px;
                    border: 3px solid rgba(255,255,255,0.3);
                    border-top-color: white;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                    margin: 0 auto 16px;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                h2 { margin: 0 0 8px; font-weight: 600; font-size: 18px; }
                p { margin: 0; opacity: 0.9; font-size: 13px; }
                .status { margin-top: 12px; font-size: 11px; opacity: 0.7; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="spinner"></div>
                <h2>媒体艺术展览工作台</h2>
                <p>正在启动服务...</p>
                <p class="status" id="status">初始化中</p>
            </div>
        </body>
        </html>
    `);

    loadingWindow.on('closed', () => {
        loadingWindow = null;
    });
}

function updateLoadingStatus(status) {
    if (loadingWindow) {
        loadingWindow.webContents.executeJavaScript(`
            document.getElementById('status').textContent = '${status}';
        `).catch(() => {});
    }
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1200,
        minHeight: 700,
        title: '媒体艺术展览工作台',
        show: false,
        webPreferences: {
            nodeIntegration: false,      // 禁止渲染进程访问 Node.js
            contextIsolation: true,      // 启用上下文隔离
            sandbox: true,               // 启用沙箱
            webSecurity: true,           // 启用 Web 安全策略
            backgroundThrottling: false,
            preload: path.join(__dirname, 'preload.js')
        }
    });

    // 开发模式：加载 Vite 开发服务器
    // 生产模式：加载打包后的文件
    if (isDev) {
        mainWindow.loadURL(`http://localhost:${VITE_DEV_SERVER_PORT}`);
        // 开发模式下打开 DevTools
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadURL(`http://localhost:${PYTHON_SERVER_PORT}`);
        // 生产模式也打开 DevTools 方便调试
        mainWindow.webContents.openDevTools();
    }

    mainWindow.once('ready-to-show', () => {
        if (loadingWindow) {
            loadingWindow.close();
        }
        mainWindow.show();
        mainWindow.focus();
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    mainWindow.webContents.on('new-window', (event, url) => {
        event.preventDefault();
        shell.openExternal(url);
    });

    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        if (loadingWindow) {
            loadingWindow.close();
        }
        dialog.showErrorBox('加载失败',
            '无法加载应用页面。\n\n' +
            '错误代码: ' + errorCode + '\n' +
            '错误描述: ' + errorDescription + '\n\n' +
            '请确保Python服务器已启动。'
        );
    });

    createMenu();
}

function createMenu() {
    // 隐藏菜单栏
    Menu.setApplicationMenu(null);
}

function startPythonServer() {
    const serverPath = getServerPath();
    const basePath = getBasePath();

    console.log('=== Electron 启动调试 ===');
    console.log('isDev:', isDev);
    console.log('isPackaged:', app.isPackaged);
    console.log('Server path:', serverPath);
    console.log('Base path:', basePath);
    console.log('File exists:', require('fs').existsSync(serverPath));
    console.log('process.resourcesPath:', process.resourcesPath);
    console.log('=========================');

    updateLoadingStatus('启动Python服务...');

    const fs = require('fs');
    let pythonCmd;

    if (process.platform === 'win32') {
        const accioPythonPath = process.env.ACCIO_PYTHON_PATH;
        if (accioPythonPath && fs.existsSync(accioPythonPath)) {
            pythonCmd = accioPythonPath;
        } else {
            const localAppData = process.env.LOCALAPPDATA || '';
            const roamingAppData = process.env.APPDATA || '';
            const possiblePaths = [
                path.join(roamingAppData, 'Accio', 'pre-install'),
            ];
            let foundAccio = false;
            for (const accioDir of possiblePaths) {
                if (fs.existsSync(accioDir)) {
                    try {
                        const subDirs = fs.readdirSync(accioDir);
                        for (const sub of subDirs) {
                            const pythonExe = path.join(accioDir, sub, 'python', 'python.exe');
                            if (fs.existsSync(pythonExe)) {
                                pythonCmd = pythonExe;
                                foundAccio = true;
                                break;
                            }
                        }
                    } catch (e) { /* ignore */ }
                }
                if (foundAccio) break;
            }
            if (!foundAccio) {
                pythonCmd = 'python';
            }
        }
    } else {
        pythonCmd = 'python3';
    }

    // 添加 resources 目录到 Python 路径
    const pythonEnv = {
        ...process.env,
        PYTHONPATH: basePath,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1'
    };

    console.log('PYTHONPATH:', basePath);
    console.log('尝试启动 Python:', pythonCmd, serverPath);

    try {
        pythonProcess = spawn(pythonCmd, [serverPath], {
            cwd: basePath,
            env: pythonEnv,
            stdio: ['ignore', 'pipe', 'pipe'],  // 使用 pipe 以便能监听输出
            detached: false,
            shell: true
        });

        if (!pythonProcess) {
            throw new Error('spawn 返回 null，无法启动 Python 进程');
        }

        console.log('Python 进程已启动，PID:', pythonProcess.pid);
    } catch (err) {
        console.error('启动 Python 失败:', err);
        if (loadingWindow) {
            loadingWindow.close();
        }
        dialog.showErrorBox('启动错误',
            '无法启动 Python 服务器。\n\n' +
            '请确保已正确安装 Python：\n\n' +
            '1. 从 python.org 下载并安装 Python 3.8+\n' +
            '2. 安装时勾选 "Add Python to PATH"\n' +
            '3. 重启电脑后再次运行\n\n' +
            '错误信息：' + err.message
        );
        app.quit();
        return;
    }

    // 将 Python 输出转发到控制台
    pythonProcess.stdout.on('data', (data) => {
        const output = data.toString();
        process.stdout.write(output);  // 转发到控制台
        console.log('Python stdout:', output);
        if (output.includes('运行中') || output.includes('localhost:8080')) {
            updateLoadingStatus('服务已启动，正在连接...');
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        const output = data.toString();
        process.stderr.write(output);  // 转发到控制台
        console.error('Python stderr:', output);
    });

    pythonProcess.on('error', (err) => {
        console.error('Failed to start Python:', err);
        if (loadingWindow) {
            loadingWindow.close();
        }
        dialog.showErrorBox('启动错误',
            '无法启动 Python 服务器。\n\n' +
            '请确保已正确安装 Python：\n\n' +
            '1. 从 python.org 下载并安装 Python 3.8+\n' +
            '2. 安装时勾选 "Add Python to PATH"\n' +
            '3. 重启电脑后再次运行\n\n' +
            '错误信息：' + err.message
        );
        app.quit();
    });

    pythonProcess.on('exit', (code, signal) => {
        console.log('Python process exited with code:', code, 'signal:', signal);
        pythonProcess = null;
    });
}

function checkServerReady(port) {
    return new Promise((resolve) => {
        const options = {
            hostname: '127.0.0.1',
            port: port || PYTHON_SERVER_PORT,
            path: '/',
            method: 'GET',
            timeout: 3000
        };

        const req = http.request(options, (res) => {
            console.log('Server response:', res.statusCode);
            // 只要收到响应就认为服务器就绪
            resolve(true);
        });

        req.on('error', (e) => {
            console.log('Server check error:', e.message);
            resolve(false);
        });

        req.on('timeout', () => {
            console.log('Server check timeout');
            req.destroy();
            resolve(false);
        });

        req.end();
    });
}

async function waitForServer(maxAttempts = 120) {
    updateLoadingStatus('等待服务就绪... (最多等待60秒)');

    // 开发模式：检查 Vite 开发服务器
    // 生产模式：检查 Python 后端服务器
    const portToCheck = isDev ? VITE_DEV_SERVER_PORT : PYTHON_SERVER_PORT;
    console.log('等待服务器启动，端口:', portToCheck, '最大尝试次数:', maxAttempts);

    for (let i = 0; i < maxAttempts; i++) {
        const ready = await checkServerReady(portToCheck);
        if (ready) {
            return true;
        }
        updateLoadingStatus(`等待服务就绪... (${i + 1}/${maxAttempts})`);
        await new Promise(resolve => setTimeout(resolve, 300));
    }
    return false;
}

function stopPythonServer() {
    if (serverCheckInterval) {
        clearInterval(serverCheckInterval);
        serverCheckInterval = null;
    }

    // 使用多种方式确保Python进程被终止
    if (process.platform === 'win32') {
        // 方法1：如果有pid，尝试终止该进程树
        if (pythonProcess && pythonProcess.pid) {
            spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
        }
        // 方法2：终止所有监听8080端口的进程
        spawn('cmd', ['/c', 'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8080 ^| findstr LISTENING\') do taskkill /f /pid %a']);
        // 方法3：终止所有python进程（最后手段）
        setTimeout(() => {
            spawn('taskkill', ['/f', '/im', 'python.exe']);
            spawn('taskkill', ['/f', '/im', 'pythonw.exe']);
        }, 500);
    } else {
        if (pythonProcess) {
            pythonProcess.kill('SIGTERM');
        }
    }
    pythonProcess = null;
}

app.on('ready', async () => {
    createLoadingWindow();

    // 若后端已在运行（开发时手动启动），跳过 Python 启动
    const alreadyRunning = await checkServerReady(PYTHON_SERVER_PORT);
    if (!alreadyRunning) {
        startPythonServer();
    } else {
        console.log('Python server already running on port', PYTHON_SERVER_PORT);
        updateLoadingStatus('检测到已运行的服务...');
    }

    const serverReady = await waitForServer(60);

    if (serverReady) {
        updateLoadingStatus('服务就绪，正在加载界面...');
        createWindow();
    } else {
        if (loadingWindow) {
            loadingWindow.close();
        }
        dialog.showErrorBox('启动超时',
            '服务器启动超时。\n\n' +
            '请检查：\n' +
            '1. Python是否正确安装\n' +
            '2. 端口8080是否被占用\n' +
            '3. 杀毒软件是否拦截'
        );
        app.quit();
    }
});

app.on('window-all-closed', () => {
    stopPythonServer();
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null) {
        createWindow();
    }
});

app.on('before-quit', () => {
    stopPythonServer();
});

app.on('will-quit', () => {
    stopPythonServer();
});

// IPC通信：打开文件夹选择对话框
ipcMain.handle('select-folder', async () => {
    if (!mainWindow) return { canceled: true };

    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory'],
        title: '选择文件夹'
    });

    return result;
});

// IPC通信：使用系统默认程序打开文件
ipcMain.handle('open-external', async (event, url) => {
    if (!url) return { success: false };

    // 如果是相对路径，转换为本地文件路径
    if (url.startsWith('/resources/')) {
        const resourcePath = url.replace('/resources/', '');
        // 资源文件存储在用户文档目录
        const userDocs = process.env.USERPROFILE || process.env.HOME;
        const persistentDir = path.join(userDocs, 'Documents', 'MediaArt_Workbench');
        const fullPath = path.join(persistentDir, 'resources', resourcePath);
        console.log('Opening file:', fullPath);
        shell.openPath(fullPath);
        return { success: true };
    }

    // 如果是HTTP URL，使用外部浏览器打开
    if (url.startsWith('http://') || url.startsWith('https://')) {
        shell.openExternal(url);
        return { success: true };
    }

    // 其他情况尝试作为本地路径打开
    shell.openPath(url);
    return { success: true };
});

// ========== IPC Handlers for preload.js ==========

ipcMain.handle('get-app-version', async () => {
    return app.getVersion();
});

ipcMain.handle('is-packaged', async () => {
    return app.isPackaged;
});

ipcMain.handle('resolve-path', async (event, relativePath) => {
    const basePath = getBasePath();
    return path.join(basePath, relativePath);
});
