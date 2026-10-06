"""Business acceptance through the real API router, JWT and temporary SQLite.

No system print/open endpoint is invoked. Every module that can access business
files is imported only after its database and filesystem roots are redirected.
"""

import datetime
import importlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit
import zlib

import bcrypt
import pytest


def png_fixture():
    """A complete 2 x 2 RGBA PNG; Pillow is not required for acceptance tests."""
    def chunk(kind, content):
        return (struct.pack('>I', len(content)) + kind + content
                + struct.pack('>I', zlib.crc32(kind + content) & 0xffffffff))

    pixels = b'\x00' + b'\xff\xff\xff\xff' * 2
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels * 2)) + chunk(b'IEND', b''))


class WorkflowAPI:
    def __init__(self, router, root):
        self.router = router
        self.root = root
        self.token = ''

    def response(self, url, method='GET', payload=None, *, query=None,
                 headers=None, body=None, authenticated=True):
        if query:
            url += '?' + urlencode(query)
        parsed = urlsplit(url)
        request_headers = dict(headers or {})
        if authenticated and self.token:
            request_headers['Authorization'] = f'Bearer {self.token}'
        if payload is not None:
            request_headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        return self.router.route_request({
            'path': parsed.path, 'method': method, 'headers': request_headers,
            'body': body or b'', 'query_params': parse_qs(parsed.query),
            'client_address': ('127.0.0.1', 49152),
        })

    def json(self, url, method='GET', payload=None, *, status=200, **kwargs):
        response = self.response(url, method, payload, **kwargs)
        assert response['status'] == status, response.get('body')
        if status < 400:
            assert response['body'].get('success') is True, response['body']
        return response['body']

    def snapshot(self):
        return self.json('/api/data/load')['data']

    def save(self, **sections):
        versions = self.snapshot()['_revisions']
        return self.json('/api/data/save', 'POST', {
            **sections, '_snapshot': True,
            '_revisions': {key: versions[key] for key in sections},
        })

    def upload(self, url, fields, filename, content, content_type='application/octet-stream', **kwargs):
        boundary = 'mediaart-workflow-fixture-boundary'
        parts = []
        for key, value in fields.items():
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                          f'\r\n\r\n{value}\r\n').encode('utf-8'))
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                      f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n').encode('utf-8'))
        parts.extend([content, f'\r\n--{boundary}--\r\n'.encode()])
        return self.json(url, 'POST', headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        }, body=b''.join(parts), **kwargs)


@pytest.fixture
def workflow_api(tmp_path, monkeypatch):
    # Route modules keep imported store/root references. Import a fresh server
    # namespace per case instead of accidentally reusing another test's singleton.
    previous = {name: module for name, module in sys.modules.items()
                if name == 'server' or name.startswith('server.')}
    for name in previous:
        sys.modules.pop(name, None)
    store = None
    try:
        monkeypatch.setenv('WORKBENCH_JWT_SECRET', 'workflow-test-only-jwt-key-at-least-32-bytes')
        config = importlib.import_module('server.config')
        config.BASE_DIR = str(tmp_path)
        database = importlib.import_module('server.database.db')
        database.BASE_DIR = str(tmp_path)
        database.DATA_DIR = str(tmp_path / 'data')
        database.DB_FILE = str(tmp_path / 'data' / 'workbench.db')

        # This is the real application singleton, now constructed against temp DB.
        store = importlib.import_module('server.database.store').data_store
        assert Path(store.db.db_path).resolve() == (tmp_path / 'data' / 'workbench.db').resolve()
        password = 'workflow-password'
        store.users.create({
            'id': 'workflow-admin', 'username': 'workflow-admin', 'role': 'admin',
            'password': bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode(),
        })
        api = WorkflowAPI(importlib.import_module('server.api.router').APIRouter(), tmp_path)
        resources = importlib.import_module('server.resources.routes')
        printing = importlib.import_module('server.print.routes')
        assert Path(resources.BACKUP_DIR).resolve().is_relative_to(tmp_path.resolve())
        assert Path(printing.ARCHIVES_DIR).resolve().is_relative_to(tmp_path.resolve())
        assert Path(printing.BASE_DIR).resolve() == tmp_path.resolve()
        login = api.json('/api/auth/login', 'POST', {
            'username': 'workflow-admin', 'password': password,
        }, authenticated=False)
        api.token = login['access_token']
        assert api.json('/api/auth/me')['user']['id'] == 'workflow-admin'
        yield api
    finally:
        if store is not None:
            store.db.close_connection()
        for name in list(sys.modules):
            if name == 'server' or name.startswith('server.'):
                sys.modules.pop(name, None)
        sys.modules.update(previous)


def create_project_and_player(api):
    project = {'id': 'workflow-project', 'name': '流程验收项目', 'status': 'planning'}
    organization = {'id': 'workflow-org', 'name': '验收合作机构'}
    player = {
        'id': 'workflow-player', 'name': '验收选手', 'projectId': project['id'],
        'orgId': organization['id'], 'stage': '初赛',
    }
    api.save(projects=[project], organizations=[organization])
    api.save(players=[player], config={'stageMaterials': {'初赛': ['照片'], '复赛': ['照片']}},
             materialTypes=[{'id': 'workflow-photo', 'name': '照片'}])
    loaded = api.json('/api/players/workflow-player')['data']
    assert loaded['name'] == player['name']
    assert loaded['projectId'] == project['id']
    assert loaded['orgId'] == organization['id']
    return project, organization, player


def create_certificate_template(api, certificates=None):
    background = api.upload('/api/print/background', {}, '验收底图.png', png_fixture(), 'image/png')
    assert (background['pageWidth'], background['pageHeight']) == (2, 2)
    certificate = {
        'certNumber': 'WORKFLOW-001', 'sessionId': 'workflow-session',
        'projectId': 'workflow-project', 'orgId': 'workflow-org',
        'orgName': '验收合作机构', 'playerId': 'workflow-player', 'playerName': '验收选手',
        'workName': '验收作品', 'award': '一等奖', 'certRound': '初赛',
    }
    template = {
        'id': 'workflow-template', 'name': '验收证书模板', 'docType': 'certificate',
        'background': background['background'], 'pageWidth': 2, 'pageHeight': 2,
        'pageSize': 'A4_L', 'projectId': 'workflow-project',
        'fields': [
            {'column': 'playerName', 'label': '选手', 'x': 50, 'y': 30},
            {'column': 'cert_number', 'label': '编号', 'x': 50, 'y': 50},
            {'column': 'award', 'label': '奖项', 'x': 50, 'y': 70},
        ],
    }
    api.save(certificates=certificates or [certificate], printTemplates=[template],
             certSettings={'activeSessionId': certificate['sessionId']})
    return certificate, template


def test_project_player_material_certificate_print_and_backup_restore(workflow_api):
    api = workflow_api
    project, organization, player = create_project_and_player(api)
    project_file = api.upload('/api/upload', {
        'projectName': project['name'], 'materialType': '策划文档', 'title': '执行方案',
    }, '执行方案.txt', '验收项目执行方案'.encode('utf-8'), 'text/plain')
    project_scan = api.json('/api/scan-project-files', query={'name': project['name']})
    assert [(item['type'], item['file_name']) for item in project_scan['materials']] == [
        ('策划文档', project_file['path'])]
    downloaded = api.response('/api/download-project-material', query={
        'projectName': project['name'], 'fileName': project_file['path'], 'materialType': '策划文档',
    })
    assert downloaded['status'] == 200
    assert downloaded['body'].decode('utf-8') == '验收项目执行方案'

    photo = png_fixture()
    initial_photo = api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '照片', 'stage': '初赛', 'title': '初赛照片',
    }, '照片.png', photo, 'image/png')
    api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '照片', 'stage': '复赛', 'title': '复赛照片',
    }, '照片.png', photo, 'image/png')
    scan = api.json('/api/scan-player-files', query={'name': player['name']})
    assert {(item['type'], item['stage']) for item in scan['materials']} == {('照片', '初赛'), ('照片', '复赛')}
    assert api.response('/api/download-player-material', query={
        'playerName': player['name'], 'fileName': initial_photo['path'], 'materialType': '照片',
    })['body'] == photo

    certificate, template = create_certificate_template(api)
    catalog = api.json('/api/print/fields')['fields']
    assert {'certNumber', 'playerName', 'award'} <= {field['column'] for field in catalog}
    generated = api.json('/api/print/generate', 'POST', {
        'templateId': template['id'],
        'certNumbers': [{'certNumber': certificate['certNumber'], 'sessionId': certificate['sessionId']}],
    })
    assert generated['itemCount'] == 1
    assert generated['warnings'] == []
    for value in (certificate['playerName'], certificate['certNumber'], certificate['award']):
        assert value in generated['html']
    assert template['background'] in generated['html']

    archive = api.json('/api/print/archive', 'POST', {
        'templateId': template['id'], 'title': '验收打印批次', 'html': generated['html'],
        'entityType': 'project', 'entityId': project['id'], 'entityName': project['name'],
        'itemCount': generated['itemCount'], 'refIds': [certificate['certNumber']],
    })
    assert archive['archived'] is True
    logs = api.json('/api/print/logs', query={'docType': 'certificate'})['logs']
    assert len(logs) == 1
    assert logs[0]['id'] == archive['logId']
    assert logs[0]['entity_id'] == project['id']
    assert logs[0]['printed_by'] == 'workflow-admin'
    assert logs[0]['item_count'] == 1
    assert json.loads(logs[0]['ref_ids']) == [certificate['certNumber']]
    assert api.json(f"/api/print/doc/{archive['logId']}")['html'] == generated['html']

    backup = api.json('/api/data/backup', 'POST', {})
    backups = api.json('/api/data/list-backups')['backups']
    assert any(item['name'] == backup['backup_name'] and item['has_data'] for item in backups)
    api.save(players=[{**api.snapshot()['players'][0], 'name': '恢复前已修改'}],
             certificates=[], printTemplates=[], certSettings={})
    assert api.snapshot()['certificates'] == []
    restored = api.json('/api/data/restore', 'POST', {'backup_name': backup['backup_name']})
    assert {'projects', 'players', 'certificates', 'printTemplates', 'certSettings'} <= set(restored['restoredSections'])
    after = api.snapshot()
    assert after['projects'][0]['name'] == project['name']
    assert after['organizations'][0]['name'] == organization['name']
    assert after['players'][0]['name'] == player['name']
    assert after['players'][0]['projectId'] == project['id']
    assert after['certificates'][0]['certNumber'] == certificate['certNumber']
    assert after['certificates'][0]['playerId'] == player['id']
    assert after['certSettings']['activeSessionId'] == certificate['sessionId']
    assert after['printTemplates'][0]['fields'] == template['fields']
    # Business-data restoration must not break the material and print files that
    # remain in this deployment's archive. It does not claim to back up file bytes.
    assert api.json('/api/scan-player-files', query={'name': player['name']})['materials'] == scan['materials']
    assert api.json(f"/api/print/doc/{archive['logId']}")['html'] == generated['html']
    assert api.json('/api/print/generate', 'POST', {
        'templateId': template['id'], 'certNumbers': [certificate['certNumber']],
        'sessionId': certificate['sessionId'],
    })['html'] == generated['html']


@pytest.mark.parametrize('per_item_session', [False, True])
def test_print_never_substitutes_a_certificate_from_another_session(workflow_api, per_item_session):
    api = workflow_api
    create_project_and_player(api)
    certificate, template = create_certificate_template(api)
    selection = ({'certNumber': certificate['certNumber'], 'sessionId': 'missing-session'}
                 if per_item_session else certificate['certNumber'])
    response = api.response('/api/print/generate', 'POST', {
        'templateId': template['id'], 'certNumbers': [selection],
        'sessionId': certificate['sessionId'] if per_item_session else 'missing-session',
    })
    assert response['status'] == 404, response['body']
    assert response['body']['success'] is False
    assert 'html' not in response['body']


def test_print_still_resolves_unique_certificate_without_session(workflow_api):
    api = workflow_api
    create_project_and_player(api)
    certificate, template = create_certificate_template(api)
    generated = api.json('/api/print/generate', 'POST', {
        'templateId': template['id'], 'certNumbers': [certificate['certNumber']],
    })
    assert generated['itemCount'] == 1
    assert certificate['playerName'] in generated['html']
    assert certificate['certNumber'] in generated['html']


def test_print_archive_references_reprint_the_original_session(workflow_api):
    api = workflow_api
    create_project_and_player(api)
    certificate, template = create_certificate_template(api)
    second = {**certificate, 'sessionId': 'second-session', 'playerName': '另一批次选手'}
    api.save(certificates=[certificate, second])
    references = [{'certNumber': second['certNumber'], 'sessionId': second['sessionId']}]
    original = api.json('/api/print/generate', 'POST', {
        'templateId': template['id'], 'certNumbers': references,
    })
    archived = api.json('/api/print/archive', 'POST', {
        'templateId': template['id'], 'html': original['html'],
        'itemCount': 1, 'refIds': references,
    })
    log = next(row for row in api.json('/api/print/logs')['logs'] if row['id'] == archived['logId'])
    assert json.loads(log['ref_ids']) == references
    reprinted = api.json('/api/print/generate', 'POST', {
        'templateId': log['template_id'], 'certNumbers': json.loads(log['ref_ids']),
    })
    assert reprinted['itemCount'] == 1
    assert second['playerName'] in reprinted['html']
    assert certificate['playerName'] not in reprinted['html']
    assert reprinted['html'] == original['html']


def test_repeated_print_archives_keep_each_document(workflow_api, monkeypatch):
    api = workflow_api
    printing = importlib.import_module('server.print.routes')

    class SameSecond(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 5, 12, 34, 56, tzinfo=tz)

    monkeypatch.setattr(printing, 'datetime', SimpleNamespace(datetime=SameSecond))
    first = api.json('/api/print/archive', 'POST', {
        'title': '同名打印批次', 'html': '<html><body>FIRST_CERTIFICATE</body></html>', 'itemCount': 1,
    })
    second = api.json('/api/print/archive', 'POST', {
        'title': '同名打印批次', 'html': '<html><body>SECOND_CERTIFICATE</body></html>', 'itemCount': 1,
    })
    assert first['archived'] and second['archived']
    assert first['snapshotPath'] != second['snapshotPath']
    assert 'FIRST_CERTIFICATE' in api.json(f"/api/print/doc/{first['logId']}")['html']
    assert 'SECOND_CERTIFICATE' in api.json(f"/api/print/doc/{second['logId']}")['html']
    assert len(api.json('/api/print/logs')['logs']) == 2


def test_unauthenticated_upload_and_print_do_not_change_business_files(workflow_api):
    api = workflow_api
    before = {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()}
    api.upload('/api/upload', {'playerName': '禁止写入'}, 'unauthorized.txt', b'forbidden',
               authenticated=False, status=401)
    api.json('/api/print/archive', 'POST', {'title': 'Forbidden', 'html': 'forbidden'},
             authenticated=False, status=401)
    after = {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()}
    assert after == before
    assert api.json('/api/print/logs')['logs'] == []
