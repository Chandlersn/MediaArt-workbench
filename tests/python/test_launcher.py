"""Offline launcher tests: no application database, browser, pip or fixed port."""

import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launcher(monkeypatch):
    spec = importlib.util.spec_from_file_location('_isolated_launcher', ROOT / 'scripts/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'log', lambda *_args: None)
    return module


def actual_status_body():
    # Execute only the production status method with in-memory models. Importing
    # its route module would initialize the application's database singleton.
    source = ast.parse((ROOT / 'server/system/routes.py').read_text(encoding='utf-8'))
    router = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'SystemRouter')
    method = next(node for node in router.body if isinstance(node, ast.FunctionDef) and node.name == 'status')
    model = SimpleNamespace(get_all=lambda: [])
    namespace = {
        'Dict': dict, 'Any': object, 'time': time, 'platform': platform, 'datetime': datetime,
        'SERVER_START_TIME': time.time(), '_ok': lambda body: body,
        'data_store': SimpleNamespace(**{name: model for name in (
            'projects', 'organizations', 'players', 'finances', 'knowledge', 'users')}),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<production-status>', 'exec'), namespace)
    return namespace['status'](SimpleNamespace(_format_uptime=lambda _: '0s', _data_files_size=lambda: 0))


def mock_http(monkeypatch, launcher, responses):
    def open_response(url, timeout):
        assert timeout == 1.5
        content_type, body, status = responses[url]
        stream = io.BytesIO(body.encode('utf-8') if isinstance(body, str) else body)
        stream.status = status
        stream.headers = Message()
        stream.headers['Content-Type'] = content_type
        return stream
    monkeypatch.setattr(launcher._http, 'open', open_response)


def test_identity_accepts_actual_status_and_homepage(launcher, monkeypatch):
    home = (ROOT / 'index.html').read_text(encoding='utf-8')
    mock_http(monkeypatch, launcher, {
        'http://127.0.0.1:1234/api/status': ('application/json', json.dumps(actual_status_body()), 200),
        'http://127.0.0.1:1234/': ('text/html', home, 200),
    })
    assert launcher.backend_matches('http://127.0.0.1:1234')
    assert launcher.homepage_matches('http://127.0.0.1:1234')
    assert not launcher.homepage_matches('http://127.0.0.1:1234', require_built=True)
    # The checked-in Vite config emits module entries under js/.
    built_home = home.replace('/src/main.js', './js/main-fixture.js')
    mock_http(monkeypatch, launcher, {'http://127.0.0.1:1234/': ('text/html', built_home, 200)})
    assert launcher.homepage_matches('http://127.0.0.1:1234', require_built=True)


@pytest.mark.parametrize('content_type,body,status', [
    ('text/html', '<html>Different service</html>', 200),
    ('application/json', '{"success":true,"status":"ok"}', 200),
    ('application/json', 'not valid JSON', 200),
    ('application/json', '[]', 200),
    ('application/json', '{}', 404),
    ('application/json', '{}', 302),
])
def test_unrelated_status_responses_do_not_claim_port(launcher, monkeypatch, content_type, body, status):
    mock_http(monkeypatch, launcher, {'http://127.0.0.1:1234/api/status': (content_type, body, status)})
    assert not launcher.backend_matches('http://127.0.0.1:1234')


@pytest.mark.parametrize('body', [
    '<title>Another application</title><div id="app"></div><script type="module" src="/js/main.js"></script>',
    '<title>媒体艺术项目管理工作台</title><div>404</div>',
    '<title>媒体艺术项目管理工作台</title><div id="app"></div>',
])
def test_wrong_or_incomplete_homepage_is_not_ready(launcher, monkeypatch, body):
    mock_http(monkeypatch, launcher, {'http://127.0.0.1:1234/': ('text/html', body, 200)})
    assert not launcher.homepage_matches('http://127.0.0.1:1234', require_built=True)


def occupied_port_fixture(launcher, monkeypatch):
    monkeypatch.setattr(launcher, 'check_python', lambda: True)
    monkeypatch.setattr(launcher, 'port_in_use', lambda _port: True)
    forbidden = Mock(side_effect=AssertionError('occupied-port reuse must not initialize or launch anything'))
    monkeypatch.setattr(launcher, 'ensure_deps', forbidden)
    monkeypatch.setattr(launcher, 'ensure_admin', forbidden)
    monkeypatch.setattr(launcher.subprocess, 'Popen', forbidden)
    browser = Mock()
    monkeypatch.setattr(launcher.webbrowser, 'open', browser)
    return browser


def test_occupied_foreign_port_stops_before_dependencies_accounts_or_browser(launcher, monkeypatch):
    browser = occupied_port_fixture(launcher, monkeypatch)
    monkeypatch.setattr(launcher, 'backend_matches', lambda _url: False)
    assert launcher.main() == 1
    browser.assert_not_called()


def test_existing_workbench_requires_matching_homepage(launcher, monkeypatch):
    browser = occupied_port_fixture(launcher, monkeypatch)
    monkeypatch.setattr(launcher, 'backend_matches', lambda _url: True)
    monkeypatch.setattr(launcher, 'homepage_matches', lambda *_args, **_kwargs: False)
    assert launcher.main() == 1
    browser.assert_not_called()


def test_existing_verified_workbench_honors_no_browser(launcher, monkeypatch):
    browser = occupied_port_fixture(launcher, monkeypatch)
    monkeypatch.setattr(launcher, 'backend_matches', lambda _url: True)
    monkeypatch.setattr(launcher, 'homepage_matches', lambda *_args, **_kwargs: True)
    monkeypatch.setenv('WORKBENCH_NO_BROWSER', '1')
    assert launcher.main() == 0
    browser.assert_not_called()
    monkeypatch.delenv('WORKBENCH_NO_BROWSER')
    assert launcher.main() == 0
    browser.assert_called_once_with(f'http://127.0.0.1:{launcher.BACKEND_PORT}')


def test_verified_vite_frontend_can_be_reused(launcher, monkeypatch):
    browser = occupied_port_fixture(launcher, monkeypatch)
    monkeypatch.delenv('WORKBENCH_NO_BROWSER', raising=False)
    monkeypatch.setattr(launcher, 'backend_matches', lambda _url: True)
    monkeypatch.setattr(launcher, 'homepage_matches', lambda url, **_kwargs: url.endswith(f':{launcher.DEV_PORT}'))
    assert launcher.main() == 0
    browser.assert_called_once_with(f'http://127.0.0.1:{launcher.DEV_PORT}')


def test_wait_ready_retries_identity_and_stops_if_owned_process_exits(launcher, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(launcher.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(launcher.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    probe = Mock(side_effect=[False, False, True])
    assert launcher.wait_ready(probe, timeout=2)
    assert probe.call_count == 3
    assert not launcher.wait_ready(lambda: False, timeout=1)
    probe.reset_mock()
    assert not launcher.wait_ready(probe, process=SimpleNamespace(poll=lambda: 1))
    probe.assert_not_called()


def test_started_backend_with_wrong_homepage_never_opens_browser(launcher, monkeypatch):
    monkeypatch.setattr(launcher, 'check_python', lambda: True)
    monkeypatch.setattr(launcher, 'port_in_use', lambda _port: False)
    monkeypatch.setattr(launcher, 'ensure_deps', lambda: True)
    monkeypatch.setattr(launcher, 'ensure_admin', lambda: None)
    monkeypatch.setattr(launcher, 'frontend_built', lambda: True)
    monkeypatch.setattr(launcher, 'backend_matches', lambda _url: True)
    monkeypatch.setattr(launcher, 'homepage_matches', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(launcher, 'wait_ready', lambda probe, **_kwargs: probe())
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(launcher.subprocess, 'Popen', Mock(return_value=process))
    browser = Mock()
    monkeypatch.setattr(launcher.webbrowser, 'open', browser)
    assert launcher.main() == 1
    process.terminate.assert_called_once()
    browser.assert_not_called()


@pytest.mark.skipif(os.name != 'nt', reason='Windows batch launcher')
def test_batch_detects_verified_python_in_space_containing_project(tmp_path):
    project = tmp_path / 'project with spaces'
    project.mkdir()
    bat = project / 'start.bat'
    shutil.copyfile(ROOT / '启动工作台.bat', bat)
    env = dict(os.environ, WORKBENCH_PYTHON=sys.executable)
    result = subprocess.run(
        [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'start.bat', '--check-python'],
        cwd=project, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sys.executable in result.stdout


@pytest.mark.skipif(os.name != 'nt', reason='Windows batch launcher')
def test_batch_falls_back_to_user_local_python_when_override_is_broken(tmp_path):
    project = tmp_path / 'launcher'
    project.mkdir()
    shutil.copyfile(ROOT / '启动工作台.bat', project / 'start.bat')
    profile = tmp_path / 'profile with spaces'
    local = profile / '.local'
    # An offline venv supplies a real Windows executable, including the required
    # pyvenv.cfg, without downloading or installing any dependencies.
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(local)], check=True, timeout=30)
    (local / 'bin').mkdir()
    executable = local / 'bin' / 'python3.12.exe'
    shutil.copyfile(local / 'Scripts' / 'python.exe', executable)
    env = dict(os.environ, USERPROFILE=str(profile), WORKBENCH_PYTHON=str(tmp_path / 'missing.exe'))
    result = subprocess.run(
        [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'start.bat', '--check-python'],
        cwd=project, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(executable) in result.stdout
