"""Exercise exact upload classifications through real routes and isolated files."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest

from test_business_workflow import workflow_api, create_project_and_player  # noqa: F401


def test_upload_preserves_exact_type_stage_and_same_name_files(workflow_api):
    api = workflow_api
    _, _, player = create_project_and_player(api)
    first = api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '报名表', 'stage': '初赛',
        'title': '任意标题',
    }, '扫描件.pdf', b'first entry form')
    second = api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '身份证', 'stage': '初赛',
        'title': '任意标题',
    }, '扫描件.pdf', b'separate identity document')
    other_stage = api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '报名表', 'stage': '省赛',
    }, 'unrelated-name.pdf', b'province entry form')
    assert first['path'] != second['path']
    rows = api.json('/api/scan-player-files', query={'name': player['name']})['materials']
    assert {(row['type'], row['stage'], row['file_name']) for row in rows} == {
        ('报名表', '初赛', first['path']), ('身份证', '初赛', second['path']),
        ('报名表', '省赛', other_stage['path']),
    }
    for uploaded, expected in ((first, b'first entry form'), (second, b'separate identity document')):
        assert api.response('/api/download-player-material', query={
            'playerName': player['name'], 'fileName': uploaded['path'],
        })['body'] == expected
    metadata = importlib.import_module('server.materials.metadata')
    # A fresh reader sees the persisted labels; neither a browser flag nor a cache.
    index = json.loads(Path(metadata.INDEX_PATH).read_text(encoding='utf-8'))
    assert len(index) == 3
    assert all(key.startswith('archive/') and not Path(key).is_absolute() for key in index)
    assert str(api.root) not in json.dumps(index)


def test_public_submission_uses_the_same_exact_material_contract(workflow_api):
    api = workflow_api
    _, _, player = create_project_and_player(api)
    api.save(config={'stageMaterials': {'初赛': ['报名表']}},
             materialTypes=[{'id': 'entry-form', 'name': '报名表'}])
    link = api.json('/api/submit-links', 'POST', {
        'entityType': 'player', 'entityId': player['id'],
    })['link']
    uploaded = api.upload(f"/api/public/submit/{link['token']}", {
        'materialType': '报名表',
    }, 'document.pdf', b'entry form', authenticated=False)
    rows = api.json('/api/scan-player-files', query={'name': player['name']})['materials']
    assert [(row['type'], row['stage'], row['file_name']) for row in rows] == [
        ('报名表', '初赛', uploaded['fileName'])]


def test_metadata_failure_leaves_previous_file_and_index_intact(workflow_api, monkeypatch):
    api = workflow_api
    _, _, player = create_project_and_player(api)
    fields = {'playerName': player['name'], 'materialType': '报名表', 'stage': '初赛'}
    previous = api.upload('/api/upload', fields, 'form.pdf', b'original')
    metadata = importlib.import_module('server.materials.metadata')
    before = Path(metadata.INDEX_PATH).read_bytes()
    before_files = {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()}
    def cannot_write(_entries):
        raise OSError('disk full')
    monkeypatch.setattr(metadata, '_write_index', cannot_write)
    api.upload('/api/upload', fields, 'form.pdf', b'new file', status=500)
    assert Path(metadata.INDEX_PATH).read_bytes() == before
    assert {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()} == before_files
    assert api.response('/api/download-player-material', query={
        'playerName': player['name'], 'fileName': previous['path'],
    })['body'] == b'original'


def test_parallel_material_uploads_keep_all_names_and_labels(workflow_api):
    metadata = importlib.import_module('server.materials.metadata')
    resources = importlib.import_module('server.resources.routes')
    directory = Path(resources.get_archives_dir()) / '02_选手档案' / '并发选手' / '01_个人信息'
    def upload(index):
        return metadata.store_material_file(str(directory), 'same.pdf', str(index).encode(),
                                            f'Type {index}', '初赛')
    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(upload, range(12)))
    assert len(set(names)) == 12
    for index, filename in enumerate(names):
        path = directory / filename
        assert path.read_bytes() == str(index).encode()
        assert metadata.get_metadata(str(path))['type'] == f'Type {index}'


def test_delete_metadata_failure_reports_failure_and_preserves_the_file(workflow_api, monkeypatch):
    api = workflow_api
    _, _, player = create_project_and_player(api)
    uploaded = api.upload('/api/upload', {
        'playerName': player['name'], 'materialType': '报名表', 'stage': '初赛',
    }, 'form.pdf', b'original')
    metadata = importlib.import_module('server.materials.metadata')
    before = Path(metadata.INDEX_PATH).read_bytes()
    def cannot_write(_entries):
        raise OSError('disk full')
    monkeypatch.setattr(metadata, '_write_index', cannot_write)
    result = api.json('/api/delete-player-material', 'DELETE', {
        'playerName': player['name'], 'fileName': uploaded['path'],
    }, status=500)
    assert result['success'] is False
    assert Path(metadata.INDEX_PATH).read_bytes() == before
    assert api.response('/api/download-player-material', query={
        'playerName': player['name'], 'fileName': uploaded['path'],
    })['body'] == b'original'


def test_legacy_unclassified_files_keep_directory_fallback(workflow_api):
    api = workflow_api
    resources = importlib.import_module('server.resources.routes')
    directory = Path(resources.get_archives_dir()) / '02_选手档案' / '历史选手' / '01_个人信息'
    directory.mkdir(parents=True, exist_ok=True)
    # A title alone is not proof that a personal-info document satisfies a form.
    (directory / '历史选手_初赛__报名表.pdf').write_bytes(b'old unclassified bytes')
    rows = api.json('/api/scan-player-files', query={'name': '历史选手'})['materials']
    assert [(row['type'], row['stage']) for row in rows] == [('个人信息', '初赛')]


@pytest.mark.parametrize('kind,entity_field,download,first_type,second_type', [
    ('player', 'playerName', '/api/download-player-material', '报名表', '作品集'),
    ('project', 'projectName', '/api/download-project-material', '策划方案', '现场照片'),
    ('org', 'orgName', '/api/get-org-material', '合同', '结算'),
])
def test_exact_type_selects_the_right_same_named_file(workflow_api, kind, entity_field, download,
                                                      first_type, second_type):
    api = workflow_api
    fields = {entity_field: '同名资料主体', 'title': '相同文件名'}
    first = api.upload('/api/upload', {**fields, 'materialType': first_type}, 'scan.pdf', b'FIRST')
    second = api.upload('/api/upload', {**fields, 'materialType': second_type}, 'scan.pdf', b'SECOND')
    assert first['path'] == second['path']
    query = {entity_field: fields[entity_field], 'fileName': second['path'], 'materialType': second_type}
    for preview in (False, True):
        response = api.response(download, query={**query, 'preview': str(preview).lower()})
        assert response['status'] == 200
        assert response['body'] == b'SECOND'
    api.json(f'/api/delete-{kind}-material', 'DELETE', query)
    # Retrying an already deleted typed identity must not delete the other file.
    api.json(f'/api/delete-{kind}-material', 'DELETE', query, status=404)
    assert api.response(download, query={**query, 'materialType': first_type})['body'] == b'FIRST'
    assert api.response(download, query=query)['status'] == 404


def test_legacy_directory_alias_selects_the_correct_same_named_file(workflow_api):
    api = workflow_api
    resources = importlib.import_module('server.resources.routes')
    root = Path(resources.get_archives_dir()) / '02_选手档案' / '旧选手'
    for directory, content in [('01_个人信息', b'FORM'), ('03_作品', b'PORTFOLIO')]:
        target = root / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / 'same.pdf').write_bytes(content)
    for material_type in ('作品集', '作品'):
        response = api.response('/api/download-player-material', query={
            'playerName': '旧选手', 'fileName': 'same.pdf', 'materialType': material_type,
        })
        assert response['status'] == 200
        assert response['body'] == b'PORTFOLIO'
    assert api.response('/api/download-player-material', query={
        'playerName': '旧选手', 'fileName': 'same.pdf', 'materialType': '获奖证书',
    })['status'] == 404
