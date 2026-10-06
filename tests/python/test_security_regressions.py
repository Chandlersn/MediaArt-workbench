"""Security regressions using temporary files and an isolated user store."""

import http.client
import importlib.util
import json
from pathlib import Path
import runpy
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

import bcrypt
import pytest


@pytest.fixture
def static_server(tmp_path, monkeypatch, request):
    from server import main

    built = getattr(request, 'param', True)
    files = {
        'data/.jwt_secret': b'private-key-fixture',
        'data/workbench.db': b'private-database-fixture',
        'data/backup/probe.json': b'private-backup-fixture',
        'data/print-bg/proof.png': b'public-print-background',
        'data/print-fonts/proof.woff2': b'public-print-font',
        'resources/proof.txt': b'public-resource',
        'resources/.hidden': b'private-hidden-file',
        'private/proof.txt': b'private-outside-root',
        'server/config.py': b'private-source',
        '.env': b'private-environment',
        # Even an accidentally copied data file in dist must remain inaccessible.
        'dist/data/workbench.db': b'private-copied-database',
    }
    if built:
        files.update({'dist/index.html': b'public-index', 'dist/assets/app.js': b'public-script'})
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    monkeypatch.setattr(main, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(main, 'STATIC_DIR', str(tmp_path / 'dist'))
    monkeypatch.setattr(main, 'FRONTEND_BUILT', built)
    # Static requests must never initialize the application's database singleton.
    monkeypatch.setattr(main, 'APIRouter', lambda: None)

    class QuietHandler(main.WorkbenchHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()

    def fetch(path, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    yield fetch, tmp_path
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize('path', [
    '/data/.jwt_secret', '/data/workbench.db', '/DATA/workbench.db',
    '/data/backup/probe.json', '/data/', '/resources/', '/resources/.hidden',
    '/resources/../private/proof.txt', '/resources/..%5cprivate%5cproof.txt',
    '/resources/%2e%2e/private/proof.txt', '/data/print-bg/../workbench.db',
    '/resources/C:%5cprivate%5cproof.txt', '/.env', '/server/config.py',
    '/resources/..%20/private/proof.txt', '/data/print-bg-extra/proof.png',
])
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_private_and_traversal_requests_are_rejected(static_server, path, method):
    fetch, _ = static_server
    status, body = fetch(path, method)
    assert status == 404
    assert b'private-' not in body


@pytest.mark.parametrize('static_server', [True, False], indirect=True)
@pytest.mark.parametrize('path,expected', [
    ('/data/print-bg/proof.png', b'public-print-background'),
    ('/data/print-fonts/proof.woff2', b'public-print-font'),
    ('/resources/proof.txt', b'public-resource'),
])
def test_public_business_files_remain_available(static_server, path, expected):
    fetch, _ = static_server
    assert fetch(path) == (200, expected)


def test_built_frontend_remains_available(static_server):
    fetch, _ = static_server
    assert fetch('/') == (200, b'public-index')
    assert fetch('/assets/app.js') == (200, b'public-script')


@pytest.mark.parametrize('static_server', [False], indirect=True)
def test_unbuilt_frontend_never_serves_repository_source(static_server):
    fetch, root = static_server
    (root / 'index.html').write_bytes(b'private-development-page')
    for path in ('/', '/index.html', '/server/config.py', '/data/workbench.db'):
        assert fetch(path)[0] == 404


def test_symbolic_link_cannot_escape_public_directory(static_server):
    fetch, root = static_server
    try:
        (root / 'resources' / 'outside').symlink_to(root / 'private', target_is_directory=True)
    except OSError:
        pytest.skip('Creating symbolic links is not permitted on this host')
    assert fetch('/resources/outside/proof.txt')[0] == 404


def test_directory_index_resolution_cannot_escape_public_root(static_server, monkeypatch):
    from server import main

    fetch, root = static_server
    realpath = main.os.path.realpath
    index = main.os.path.normcase(str(root / 'dist' / 'index.html'))

    def redirected_index(path, *args, **kwargs):
        if main.os.path.normcase(str(path)) == index:
            return str(root / 'private' / 'proof.txt')
        return realpath(path, *args, **kwargs)

    # Model a linked index without requiring Windows symbolic-link privileges.
    monkeypatch.setattr(main.os.path, 'realpath', redirected_index)
    assert fetch('/')[0] == 404


def test_host_defaults_to_loopback_and_can_be_configured(monkeypatch):
    config_file = Path(__file__).resolve().parents[2] / 'server' / 'config.py'
    monkeypatch.delenv('WORKBENCH_HOST', raising=False)
    assert runpy.run_path(str(config_file))['HOST'] == '127.0.0.1'
    monkeypatch.setenv('WORKBENCH_HOST', '0.0.0.0')
    assert runpy.run_path(str(config_file))['HOST'] == '0.0.0.0'


@pytest.fixture
def user_router(monkeypatch):
    monkeypatch.setenv('WORKBENCH_JWT_SECRET', 'isolated-security-test-key-at-least-32-bytes')
    from server.utils import auth_middleware
    from server.utils.jwt_handler import JWTHandler

    handler = JWTHandler(secret_key='isolated-security-test-key-at-least-32-bytes')
    monkeypatch.setattr(auth_middleware, 'jwt_handler', handler)
    store = Mock()
    store.users.get_by_id.return_value = {'id': 'viewer-fixture', 'role': 'viewer'}
    store_module = types.ModuleType('server.database.store')
    store_module.data_store = store
    monkeypatch.setitem(sys.modules, 'server.database.store', store_module)

    # Load this router under a separate name, leaving other tests' module caches intact.
    route_file = Path(__file__).resolve().parents[2] / 'server' / 'users' / 'routes.py'
    spec = importlib.util.spec_from_file_location('_isolated_security_users_routes', route_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token = handler.generate_token('viewer-fixture', 'viewer', 'viewer')

    def change_password(payload):
        return module.UsersRouter().handle_request({
            'path': '/api/users/change-password', 'method': 'POST',
            'headers': {'Authorization': f'Bearer {token}'},
            'body': json.dumps(payload).encode(),
        })

    return change_password, store


def test_viewer_cannot_change_another_users_password(user_router):
    change_password, store = user_router
    response = change_password({'userId': 'admin-fixture', 'newPassword': 'new-password'})
    assert response['status'] == 403
    store.users.get_by_id.assert_not_called()
    store.users.update.assert_not_called()


@pytest.mark.parametrize('include_user_id', [True, False])
def test_current_user_can_complete_first_login_password_change(user_router, include_user_id):
    change_password, store = user_router
    payload = {'newPassword': 'first-login-password'}
    if include_user_id:
        payload['userId'] = 'viewer-fixture'
    response = change_password(payload)
    assert response['status'] == 200
    target, update = store.users.update.call_args.args
    assert target == 'viewer-fixture'
    assert bcrypt.checkpw(payload['newPassword'].encode(), update['password'].encode())
