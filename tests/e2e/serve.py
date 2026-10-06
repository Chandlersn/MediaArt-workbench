"""Run the real app in a disposable workspace, never against business data."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import secrets
import threading
from http.server import ThreadingHTTPServer


def main():
    project = Path(__file__).resolve().parents[2]
    if not (project / 'dist' / 'index.html').is_file():
        raise SystemExit('Run npm run build before browser acceptance tests.')
    with tempfile.TemporaryDirectory(prefix='mediaart-e2e-') as directory:
        fixture = Path(directory).resolve()
        assert fixture.parent == Path(tempfile.gettempdir()).resolve()
        shutil.copytree(project / 'server', fixture / 'server',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(project / 'dist', fixture / 'dist')
        # Import code from the disposable copy so every __file__-derived data,
        # credential, archive, trash and configuration path is isolated too.
        sys.path.insert(0, str(fixture))
        os.chdir(fixture)
        os.environ['WORKBENCH_HOST'] = '127.0.0.1'
        os.environ['WORKBENCH_PORT'] = os.environ.get('WORKBENCH_E2E_PORT', '18080')
        os.environ['WORKBENCH_JWT_SECRET'] = 'mediaart-browser-tests-only-never-a-business-secret'
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

        import bcrypt
        from server.config import BASE_DIR
        from server.database.store import data_store
        assert Path(BASE_DIR).resolve() == fixture
        assert Path(data_store.db.db_path).resolve().is_relative_to(fixture)
        data_store.users.create({
            'id': 'browser-admin', 'username': 'browser-admin', 'role': 'admin',
            'real_name': 'Browser acceptance account',
            'password': bcrypt.hashpw(b'Browser-test-only-2026!', bcrypt.gensalt()).decode(),
        })
        assert data_store.save_all_data({
            'config': {'stageMaterials': {'初赛': ['报名表'], '省赛': ['报名表']}},
            'materialTypes': [{'id': 'entry-form', 'name': '报名表'},
                              {'id': 'portfolio', 'name': '作品集'}],
        })
        print(f'E2E fixture: {fixture}', flush=True)
        from server import main as application
        from server.database import db as database_module
        shutdown_token = os.environ.get('WORKBENCH_E2E_SHUTDOWN_TOKEN', '')
        cleanup_errors = []
        cleanup_lock = threading.Lock()

        def close_fixture_connections():
            # Database caches connections per thread, so main-thread cleanup
            # cannot close handles opened by HTTP worker threads. Close every
            # fixture connection in its owning thread, including extra stores.
            connections = getattr(database_module._local, 'connections', {})
            for path, connection in list(connections.items()):
                try:
                    if not Path(path).resolve().is_relative_to(fixture):
                        raise RuntimeError(f'Unexpected database outside E2E fixture: {path}')
                    connection.close()
                    del connections[path]
                except Exception as error:
                    # Finish closing other handles, then fail the harness after
                    # all workers have joined. Do not hide cleanup failures.
                    with cleanup_lock:
                        cleanup_errors.append(error)

        class FixtureHandler(application.WorkbenchHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.path == '/__acceptance__/shutdown':
                    supplied = self.headers.get('X-Acceptance-Token', '')
                    if not shutdown_token or not secrets.compare_digest(supplied, shutdown_token):
                        self.send_error(403)
                        return
                    self.send_response(200)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                super().do_POST()

        class FixtureServer(ThreadingHTTPServer):
            # Production workers are daemon threads. Acceptance cleanup must
            # wait for in-flight requests before deleting their database files.
            daemon_threads = False
            block_on_close = True

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    # This also covers failures during handler construction or
                    # setup, before BaseRequestHandler would call finish().
                    close_fixture_connections()

        # This server and shutdown hook exist only in the acceptance harness.
        try:
            application.run_startup_checks()
            with FixtureServer((application.HOST, application.PORT), FixtureHandler) as httpd:
                print(f'E2E server: http://127.0.0.1:{httpd.server_address[1]}', flush=True)
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    pass
        finally:
            try:
                close_fixture_connections()
                if cleanup_errors:
                    raise RuntimeError(
                        f'Failed to close {len(cleanup_errors)} E2E database connection(s)'
                    ) from cleanup_errors[0]
            finally:
                os.chdir(project)


if __name__ == '__main__':
    main()
