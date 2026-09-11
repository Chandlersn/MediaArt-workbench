// electron/preload.js
// 安全暴露 Electron IPC API 到渲染进程

const { contextBridge, ipcRenderer } = require('electron');

// 只暴露必要的 API，不暴露整个 Node.js
contextBridge.exposeInMainWorld('electronAPI', {
  // 文件系统操作（受限）
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // 安全的路径解析（不暴露 path 模块）
  resolvePath: (relativePath) => ipcRenderer.invoke('resolve-path', relativePath),

  // 应用信息
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  isPackaged: () => ipcRenderer.invoke('is-packaged'),

  // 平台信息
  platform: process.platform,

  // 安全的事件监听（不暴露完整 ipcRenderer）
  onServerReady: (callback) => {
    ipcRenderer.on('server-ready', (event, data) => callback(data));
  }
});