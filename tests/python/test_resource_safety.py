"""Exercise real resource routes and SQLite using only temporary business data."""
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def resource_api(tmp_path, monkeypatch):
    from server.database.db import Database, DataStore
    db = Database(str(tmp_path / 'workbench.db'))
    store = DataStore(db)
    singleton = types.ModuleType('server.database.store')
    singleton.data_store = store
    monkeypatch.setitem(sys.modules, 'server.database.store', singleton)
    from server import config
    monkeypatch.setattr(config, 'BASE_DIR', str(tmp_path))
    path = Path(__file__).resolve().parents[2] / 'server/resources/routes.py'
    spec = importlib.util.spec_from_file_location('_isolated_resource_regressions', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'extract_user_from_request', lambda rc: rc.get('fixture_user'))

    def request(route, payload=None, role='admin', method='POST', headers=None, body=None):
        return module.ResourcesRouter().handle_request({
            'path': route, 'method': method, 'headers': headers or {},
            'body': body if body is not None else json.dumps(payload or {}).encode(),
            'fixture_user': {'user_id': 'fixture', 'role': role},
        })
    yield request, store, module, tmp_path
    db.close_connection()


def test_editor_cannot_submit_users_or_settings(resource_api):
    request, store, _, _ = resource_api
    revisions = store.load_all_data()['_revisions']
    for key, value in [('users', []), ('config', {})]:
        response = request('/api/data/save', {key: value, '_snapshot': True, '_revisions': revisions}, role='editor')
        assert response['status'] == 403


def test_save_requires_revision_and_rejects_stale_data(resource_api):
    request, store, _, _ = resource_api
    original = {'id': 'p1', 'name': 'Original'}
    assert store.save_all_data({'projects': [original]})
    base = store.load_all_data()['_revisions']
    assert request('/api/data/save', {'projects': [original]})['status'] == 409
    payload = {'projects': [{'id': 'p1', 'name': 'New'}], '_snapshot': True, '_revisions': base}
    success = request('/api/data/save', payload)
    assert success['status'] == 200
    assert success['body']['_revisions']['projects'] != base['projects']
    assert request('/api/data/save', payload)['status'] == 409
    assert store.projects.get_by_id('p1')['name'] == 'New'


def test_invalid_save_returns_error_and_keeps_original(resource_api):
    request, store, _, _ = resource_api
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    response = request('/api/data/save', {'projects': [{'id': 'p1'}],
                       '_revisions': store.load_all_data()['_revisions'], '_snapshot': True})
    assert response['status'] == 400
    assert store.projects.get_by_id('p1')['name'] == 'Original'


def test_editor_can_edit_but_cannot_delete_existing_entities(resource_api):
    request, store, _, _ = resource_api
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    base = store.load_all_data()['_revisions']
    assert request('/api/data/save', {'projects': [], '_snapshot': True, '_revisions': base}, role='editor')['status'] == 403
    response = request('/api/data/save', {'projects': [{'id': 'p1', 'name': 'Edited'}],
                       '_snapshot': True, '_revisions': base}, role='editor')
    assert response['status'] == 200


def test_normal_load_never_exposes_passwords(resource_api):
    request, store, _, _ = resource_api
    assert store.save_all_data({'users': [{'id': 'u1', 'username': 'test', 'password': 'fixture-hash', 'role': 'admin'}]})
    response = request('/api/data/load', method='GET', role='viewer')
    assert response['status'] == 200
    assert 'password' not in response['body']['data']['users'][0]
    assert store.users.get_by_id('u1')['password'] == 'fixture-hash'


def test_normal_load_does_not_scan_complete_log_history(resource_api, monkeypatch):
    request, store, _, _ = resource_api

    def unexpected_scan(**_kwargs):
        pytest.fail('Normal page load must not read all logs or notifications')

    monkeypatch.setattr(store.audit_logs, 'get_all', unexpected_scan)
    monkeypatch.setattr(store.notifications, 'get_all', unexpected_scan)
    response = request('/api/data/load', method='GET')
    assert response['status'] == 200
    assert 'auditLogs' not in response['body']['data']
    assert 'notifications' not in response['body']['data']


def test_business_views_keep_needed_dictionaries_without_settings_permission(resource_api, monkeypatch):
    request, store, module, _ = resource_api
    assert store.save_all_data({
        'config': {'stageMaterials': {'review': ['photo']},
                   'resourceCategories': [{'id': 'custom'}], 'financeTypes': ['private']},
        'materialTypes': [{'id': 'photo', 'name': 'Photo'}],
        'printTemplates': [{'id': 't1', 'name': 'Certificate', 'docType': 'certificate'}],
    })
    monkeypatch.setattr(module, 'has_permission', lambda role, business, action:
                        action == 'view' and business in {'projects', 'players', 'resources'})
    response = request('/api/data/load', method='GET', role='viewer')
    data = response['body']['data']
    assert data['config']['stageMaterials'] == {'review': ['photo']}
    assert data['config']['resourceCategories'] == [{'id': 'custom'}]
    assert 'financeTypes' not in data['config']
    assert data['materialTypes'][0]['id'] == 'photo'
    assert data['printTemplates'][0]['id'] == 't1'
    assert 'finances' not in data
    assert 'users' not in data
    assert not {'config', 'materialTypes', 'printTemplates'} & data['_revisions'].keys()
    payload = {'config': data['config'], '_revisions': store.load_all_data()['_revisions']}
    assert request('/api/data/save', payload, role='viewer')['status'] == 403


def test_backup_restore_includes_certificates_templates_and_config(resource_api):
    request, store, _, _ = resource_api
    original = {
        'projects': [{'id': 'p1', 'name': 'Original'}],
        'certificates': [{'certNumber': 'C1', 'sessionId': 's1', 'playerName': 'Original'}],
        'certSettings': {'numberTemplates': {'round': '{seq}'}},
        'printTemplates': [{'id': 't1', 'name': 'Original', 'docType': 'certificate', 'background': 'data/print-bg/a.png'}],
        'config': {'resourceCategories': [{'id': 'original'}]},
        'projectChecklists': {'p1': {'custom': {'label': 'Original', 'cards': []}}},
    }
    assert store.save_all_data(original)
    backup = request('/api/data/backup', {'projects': []})
    assert backup['status'] == 200
    assert store.save_all_data({'certificates': [], 'printTemplates': [], 'config': {},
                                'projectChecklists': {}, 'certSettings': {}, '_snapshot': True})
    restored = request('/api/data/restore', {'backup_name': backup['body']['backup_name']})
    assert restored['status'] == 200
    result = store.load_all_data()
    assert result['certificates'][0]['certNumber'] == 'C1'
    assert result['printTemplates'][0]['name'] == 'Original'
    assert result['certSettings'] == original['certSettings']
    assert result['config'] == original['config']
    assert result['projectChecklists'] == original['projectChecklists']


@pytest.mark.parametrize('path,method', [('/api/data/import', 'POST'), ('/api/data/export', 'GET'),
    ('/api/data/restore', 'POST'), ('/api/data/backup', 'POST')])
def test_sensitive_backup_operations_require_admin(resource_api, path, method):
    request, _, _, _ = resource_api
    assert request(path, role='editor', method=method)['status'] == 403


def test_nested_upload_preserves_all_directory_levels(resource_api):
    request, _, module, _ = resource_api
    top = next(iter(module.ARCHIVE_TOP_DIRS))
    target = f'{top}/ProjectFixture/StageFixture'
    body = (f'--proof\r\nContent-Disposition: form-data; name="targetPath"\r\n\r\n{target}\r\n'
            '--proof\r\nContent-Disposition: form-data; name="file"; filename="proof.txt"\r\n'
            'Content-Type: text/plain\r\n\r\nproof-content\r\n--proof--\r\n').encode()
    response = request('/api/upload', headers={'Content-Type': 'multipart/form-data; boundary=proof'}, body=body)
    assert response['status'] == 200
    dest = Path(module.get_archives_dir()) / top / 'ProjectFixture' / 'StageFixture' / 'proof.txt'
    assert dest.read_bytes() == b'proof-content'


@pytest.mark.parametrize('path', ['C:/private.txt', 'D:\\private.txt', '../private.txt', 'folder/secret.txt:stream'])
def test_windows_file_paths_cannot_escape_resource_root(resource_api, path):
    _, _, module, _ = resource_api
    assert module._safe_rel(path) is None


def test_multiple_backups_have_unique_names_and_parseable_dates(resource_api):
    request, _, module, _ = resource_api
    first = request('/api/data/backup')['body']['backup_name']
    second = request('/api/data/backup')['body']['backup_name']
    assert first != second
    assert module._split_backup_name(first)[1] != ''
    from server.database.maintenance import rotate_backups
    assert rotate_backups(module.BACKUP_DIR, keep=1) == 1
