#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地一键启动器（个人单机使用）。

做的事：
  1. 检查 Python 版本与运行依赖（bcrypt / PyJWT），缺失则自动安装；
  2. 检查前端是否已构建 —— 已构建就**只起一个后端进程**（后端直接托管页面）；
     未构建且本机有 Node 则自动 `npm run build`，构建失败则尝试 Vite 开发模式；
  3. 端口被占用时先核对工作台状态和首页；只有匹配才复用已有服务；
  4. 就绪后自动打开浏览器；Ctrl+C 可停止。

设计取舍：优先「单进程」而不是「两个终端」，因为本项目定位是个人本地使用——
少一个进程、少一个端口、少一处会挂的地方。后端托管前端的能力见
server/main.py 的 translate_path 与 server/config.py 的 STATIC_DIR。
"""

import os
import re
import json
import html
import http.client
import sys
import time
import socket
import signal
import subprocess
import webbrowser
import urllib.request

# 让中文在 Windows 控制台正常输出
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_PORT = int(os.environ.get('WORKBENCH_PORT', os.environ.get('PORT', 8080)))
DEV_PORT = int(os.environ.get('VITE_DEV_SERVER_PORT', 3004))

REQUIRED_MODULES = [('bcrypt', 'bcrypt'), ('jwt', 'PyJWT')]
MIN_PYTHON = (3, 8)
HOME_TITLE = '媒体艺术项目管理工作台'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# localhost probes must not follow redirects or use a configured HTTP proxy.
_http = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def log(msg: str = '') -> None:
    print(msg, flush=True)


def hr() -> None:
    log('=' * 52)


# ---------- 环境检查 ----------

def check_python() -> bool:
    if sys.version_info < MIN_PYTHON:
        log(f"[×] Python 版本过低：当前 {sys.version.split()[0]}，需要 "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}+")
        return False
    log(f"[√] Python {sys.version.split()[0]}")
    return True


def missing_deps() -> list:
    import importlib
    missing = []
    for mod, pkg in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    return missing


def ensure_deps() -> bool:
    """依赖缺失时自动安装（用户已双击启动，装依赖是预期行为）。"""
    missing = missing_deps()
    if not missing:
        log('[√] 运行依赖已就绪')
        return True

    log(f'[!] 缺少依赖：{" ".join(missing)}，正在自动安装…')
    cmd = [sys.executable, '-m', 'pip', 'install', *missing]
    try:
        rc = subprocess.call(cmd, cwd=BASE_DIR)
    except Exception as e:
        log(f'[×] 安装失败：{e}')
        rc = 1

    if rc != 0 or missing_deps():
        log()
        log('[×] 依赖安装未成功，请手动执行：')
        log(f'    "{sys.executable}" -m pip install -r requirements.txt')
        return False

    log('[√] 依赖安装完成')
    return True


def node_available() -> bool:
    try:
        subprocess.check_output(['node', '--version'], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def frontend_built() -> bool:
    return os.path.isfile(os.path.join(BASE_DIR, 'dist', 'index.html'))


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(('127.0.0.1', port)) == 0


def _read_response(url: str, content_type: str, limit: int):
    """Read a bounded local response; unrelated pages and redirects fail closed."""
    with _http.open(url, timeout=1.5) as response:
        if response.status != 200 or response.headers.get_content_type() != content_type:
            return None
        body = response.read(limit + 1)
        if len(body) > limit:
            return None
        return body.decode('utf-8')


def backend_matches(base_url: str) -> bool:
    """Match this application's status schema, rather than any HTTP response."""
    try:
        body = _read_response(base_url.rstrip('/') + '/api/status', 'application/json', 65536)
        status = json.loads(body) if body else None
        if not isinstance(status, dict):
            return False
        counts = status.get('counts')
        expected = {'projects', 'organizations', 'players', 'finances', 'knowledge', 'users'}
        return (
            status.get('success') is True
            and status.get('status') == 'ok'
            and status.get('database') == 'sqlite'
            and isinstance(status.get('version'), str)
            and bool(status['version'])
            and isinstance(counts, dict)
            and expected.issubset(counts)
            and all(type(counts[key]) is int and counts[key] >= 0 for key in expected)
        )
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return False


def homepage_matches(base_url: str, require_built: bool = False) -> bool:
    """Verify the workbench title, Vue mount and a module entry on the home page."""
    try:
        body = _read_response(base_url.rstrip('/') + '/', 'text/html', 524288)
        if not body:
            return False
        title = re.search(r'<title\b[^>]*>(.*?)</title>', body, re.I | re.S)
        if not title or html.unescape(title.group(1)).strip() != HOME_TITLE:
            return False
        if not re.search(r'<div\b[^>]*\bid\s*=\s*[\"\']app[\"\']', body, re.I):
            return False
        scripts = re.findall(r'<script\b[^>]*>', body, re.I)
        entries = [tag for tag in scripts
                   if re.search(r'\btype\s*=\s*[\"\']module[\"\']', tag, re.I)
                   and re.search(r'\bsrc\s*=', tag, re.I)]
        if require_built:
            entries = [tag for tag in entries if re.search(
                r'\bsrc\s*=\s*[\"\'](?:\./|/)?(?:js|assets)/[^\"\']+\.js(?:\?[^\"\']*)?[\"\']', tag, re.I)]
        return bool(entries)
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return False


def wait_ready(probe, timeout: float = 40.0, process=None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if probe():
            return True
        time.sleep(0.4)
    return False


def open_browser(url: str) -> None:
    if os.environ.get('WORKBENCH_NO_BROWSER') == '1':
        log('[·] 已跳过自动打开浏览器（WORKBENCH_NO_BROWSER=1）')
        return
    try:
        webbrowser.open(url)
    except Exception as e:
        log(f'[!] 无法自动打开浏览器，请手动访问 {url}（{e}）')


def build_frontend() -> bool:
    log('[·] 正在构建前端（首次启动需要，约 1-2 分钟）…')
    try:
        rc = subprocess.call(['npm', 'run', 'build'], cwd=BASE_DIR, shell=True)
    except Exception as e:
        log(f'[×] 构建失败：{e}')
        return False
    if rc != 0 or not frontend_built():
        log('[×] 前端构建失败')
        return False
    log('[√] 前端构建完成')
    return True


# ---------- 首次部署：自动创建管理员 ----------

def user_count():
    """返回 users 表记录数；表不存在或读取失败返回 None（视为需要初始化）。"""
    db_file = os.path.join(BASE_DIR, 'data', 'workbench.db')
    if not os.path.isfile(db_file):
        return None
    import sqlite3
    try:
        conn = sqlite3.connect(db_file)
        try:
            return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return None


def ensure_admin() -> None:
    """全新部署时数据库是空的，而注册接口需要管理员权限 —— 会形成「谁都登不进去」的死锁。

    所以这里自动跑一次 scripts/init_admin.py 打破死锁，并把账号密码明确打印出来。
    密码用随机值（不硬编码弱口令），同时落在 data/initial_password.txt 里可随时查阅。
    """
    if user_count():
        return

    log('[·] 检测到还没有任何账号，正在创建管理员…')
    script = os.path.join(BASE_DIR, 'scripts', 'init_admin.py')
    if not os.path.isfile(script):
        log('[!] 未找到 scripts/init_admin.py，跳过。若无法登录请手动创建管理员。')
        return

    try:
        subprocess.call([sys.executable, script], cwd=BASE_DIR)
    except Exception as e:
        log(f'[!] 创建管理员失败：{e}')
        return

    # 把刚生成的账号密码读出来，明确告诉用户（否则用户不知道该用什么登录）
    pwd_file = os.path.join(BASE_DIR, 'data', 'initial_password.txt')
    creds = {}
    try:
        with open(pwd_file, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    k, v = line.split(':', 1)
                    creds[k.strip()] = v.strip()
    except Exception:
        pass

    if creds.get('username') and creds.get('password'):
        _INITIAL_CREDS.append((creds['username'], creds['password']))
        log('[√] 管理员已创建')
    else:
        log('[!] 管理员已创建，但未能读取到密码，请查看 data/initial_password.txt')


_INITIAL_CREDS = []


# ---------- 进程管理 ----------

_procs = []


def stop_all() -> None:
    for p in _procs:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    for p in _procs:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def _on_signal(signum, frame):
    raise KeyboardInterrupt


def main() -> int:
    hr()
    log('   媒体艺术智能工作台 · 本地启动')
    hr()
    log()

    if not check_python():
        return 1

    backend_url = f'http://127.0.0.1:{BACKEND_PORT}'
    dev_url = f'http://127.0.0.1:{DEV_PORT}'
    # Reuse only a verified workbench. Do this before dependency installation or
    # account initialization: an occupied port must not trigger unrelated work.
    if port_in_use(BACKEND_PORT):
        log()
        if not backend_matches(backend_url):
            log(f'[×] 端口 {BACKEND_PORT} 已被其他服务占用，未检测到工作台后端。')
            log('    请先关闭占用此端口的程序，或用 WORKBENCH_PORT 指定其他端口。')
            return 1
        if homepage_matches(backend_url, require_built=True):
            open_url = backend_url
        elif backend_matches(dev_url) and homepage_matches(dev_url):
            open_url = dev_url
        else:
            log('[×] 已找到工作台后端，但未找到可用的工作台首页。')
            log('    请构建前端后重启后端，或启动 Vite 开发服务器。')
            return 1
        log(f'[√] 已确认工作台正在运行：{open_url}')
        open_browser(open_url)
        return 0

    if not ensure_deps():
        return 1

    # 决定运行模式：优先单进程（后端托管已构建的前端）
    use_single_process = frontend_built()
    if not use_single_process:
        if not node_available():
            log('[×] 前端尚未构建，且本机未检测到 Node.js，无法构建。')
            log('    请安装 Node.js 18+ 后重试；或在一台有 Node 的机器上执行')
            log('    `npm run build`，再把生成的 dist/ 目录整个拷到本目录下。')
            return 1
        use_single_process = build_frontend()
        if not use_single_process:
            log('[!] 前端构建失败，改用「后端 + Vite 开发服务器」双进程模式。')

    # 全新部署自动建管理员，避免卡在登录界面
    ensure_admin()

    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'

    log()
    log(f'[·] 启动后端服务（端口 {BACKEND_PORT}）…')
    backend = subprocess.Popen(
        [sys.executable, '-m', 'server.main'],
        cwd=BASE_DIR, env=env,
    )
    _procs.append(backend)

    def backend_ready():
        return backend_matches(backend_url) and (
            not use_single_process or homepage_matches(backend_url, require_built=True))

    if not wait_ready(backend_ready, timeout=40, process=backend):
        log('[×] 后端或工作台首页未就绪。请检查上方输出中的错误信息。')
        stop_all()
        return 1
    log('[√] 后端已就绪')

    open_url = backend_url

    if not use_single_process:
        log(f'[·] 启动前端开发服务器（端口 {DEV_PORT}）…')
        frontend = subprocess.Popen(
            ['npm', 'run', 'dev', '--', '--host', '127.0.0.1',
             '--port', str(DEV_PORT), '--strictPort'],
            cwd=BASE_DIR, env=env, shell=True,
        )
        _procs.append(frontend)
        if wait_ready(lambda: backend_matches(dev_url) and homepage_matches(dev_url),
                      timeout=40, process=frontend):
            log('[√] 前端已就绪')
            open_url = dev_url
        else:
            log('[×] 前端启动失败，未找到可用的工作台首页。')
            stop_all()
            return 1

    log()
    hr()
    log(f'  已启动，正在打开浏览器：{open_url}')
    if _INITIAL_CREDS:
        user, pwd = _INITIAL_CREDS[0]
        log()
        log('  ┌─ 首次使用，已自动创建管理员账号 ─────────────')
        log(f'  │  用户名：{user}')
        log(f'  │  密  码：{pwd}')
        log('  │  请立即登录并修改密码；密码也保存在')
        log('  │  data/initial_password.txt')
        log('  └──────────────────────────────────────────────')
    else:
        log('  登录账号：admin（密码见 data/initial_password.txt，或你自行设置的值）')
    log()
    log('  按 Ctrl+C 停止服务')
    hr()

    open_browser(open_url)

    # 等待：任一子进程退出即认为服务结束
    try:
        while True:
            for p in _procs:
                if p.poll() is not None:
                    log()
                    log(f'[!] 有服务进程退出（退出码 {p.returncode}），正在停止全部服务…')
                    raise KeyboardInterrupt
            time.sleep(1)
    except KeyboardInterrupt:
        log()
        log('[·] 正在停止服务…')
        stop_all()
        log('[√] 已停止。')
        return 0


if __name__ == '__main__':
    try:
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        stop_all()
        sys.exit(0)
