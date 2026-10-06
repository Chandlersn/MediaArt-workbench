"""Exercise icon HTTP responses without opening the application's database."""
import http.client
import importlib.util
from pathlib import Path
import sys
import threading
import types
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer

import pytest


@pytest.fixture
def icon_api(tmp_path, monkeypatch):
    resources = types.ModuleType('server.resources.routes')
    resources.get_archives_dir = lambda: str(tmp_path / 'archives')
    monkeypatch.setitem(sys.modules, 'server.resources.routes', resources)
    spec = importlib.util.spec_from_file_location(
        '_isolated_icon_routes', Path(__file__).resolve().parents[2] / 'server/archive/routes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from server import main
    from server.api.router import APIRouter
    router = APIRouter.__new__(APIRouter)
    router.routes = {}
    router._archive_router = module.ArchiveRouter()
    router._resources_router = None
    monkeypatch.setattr(main, 'APIRouter', lambda: router)
    monkeypatch.setattr(module, 'get_folder_icon', lambda size: None)
    monkeypatch.setattr(module, 'get_file_icon', lambda ext, size: None)

    class QuietHandler(main.WorkbenchHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()

    def fetch(query):
        connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
        try:
            connection.request('GET', '/api/file-icon' + query)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    yield fetch, module
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize('query', ['?type=folder', '?ext=pdf', '?ext=docx', '?ext=unknown', ''])
def test_missing_native_icons_return_renderable_svg(icon_api, query):
    fetch, _ = icon_api
    status, headers, body = fetch(query)
    assert status == 200
    assert headers['Content-Type'].startswith('image/svg+xml')
    svg = ET.fromstring(body)
    assert svg.tag == '{http://www.w3.org/2000/svg}svg'
    assert svg.findall('{http://www.w3.org/2000/svg}path')
    assert int(headers['Content-Length']) == len(body)
    assert 'max-age=300' in headers['Cache-Control']


@pytest.mark.parametrize('query, extractor', [
    ('?type=folder', 'get_folder_icon'), ('?ext=pdf', 'get_file_icon'),
])
def test_native_errors_use_fallback_instead_of_failed_http(icon_api, monkeypatch, query, extractor):
    fetch, module = icon_api

    def unavailable(*_args):
        raise OSError('Native icon conversion failed')

    monkeypatch.setattr(module, extractor, unavailable)
    status, headers, body = fetch(query)
    assert status == 200
    assert headers['Content-Type'].startswith('image/svg+xml')
    assert ET.fromstring(body).tag.endswith('svg')


@pytest.mark.parametrize('query, extractor', [
    ('?type=folder', 'get_folder_icon'), ('?ext=pdf', 'get_file_icon'),
])
def test_native_png_response_is_preserved(icon_api, monkeypatch, query, extractor):
    fetch, module = icon_api
    native_png = b'\x89PNG\r\n\x1a\nnative-icon-fixture'
    monkeypatch.setattr(module, extractor, lambda *_args: native_png)
    status, headers, body = fetch(query)
    assert status == 200
    assert headers['Content-Type'] == 'image/png'
    assert body == native_png
    assert 'max-age=86400' in headers['Cache-Control']


@pytest.mark.parametrize('requested,expected', [('0', '16'), ('99999', '256'), ('bad', '48')])
def test_fallback_sizes_are_bounded(icon_api, requested, expected):
    fetch, _ = icon_api
    status, _, body = fetch('?type=folder&size=' + requested)
    assert status == 200
    assert ET.fromstring(body).attrib['width'] == expected
    assert ET.fromstring(body).attrib['height'] == expected


def test_unknown_extension_is_not_embedded_in_svg(icon_api):
    fetch, _ = icon_api
    status, _, body = fetch('?ext=%3Cscript%3Ealert%281%29%3C%2Fscript%3E')
    assert status == 200
    assert b'script' not in body
    assert b'alert' not in body
    ET.fromstring(body)
