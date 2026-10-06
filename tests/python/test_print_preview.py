"""The embedded preview must render the checked batch without print side effects."""
import importlib

import pytest

from test_print_preflight import batch, workflow_api  # noqa: F401


def test_preview_is_single_page_read_only_and_uses_print_layout(batch):
    api, certificate, template, payload = batch
    other = {**certificate, 'certNumber': 'PREVIEW-SECOND', 'playerName': '第二位预览选手'}
    api.save(certificates=[certificate, other])
    payload['certNumbers'].append({'certNumber': other['certNumber'], 'sessionId': other['sessionId']})
    token = api.json('/api/print/validate', 'POST', payload)['validationToken']
    before = api.snapshot()
    store = importlib.import_module('server.database.store').data_store
    writes = store.db.get_connection().total_changes
    first = api.json('/api/print/preview', 'POST', {**payload, 'validationToken': token})
    second = api.json('/api/print/preview', 'POST', {**payload, 'validationToken': token, 'pageIndex': 1})
    assert first['reference'] == payload['certNumbers'][0]
    assert second['reference'] == payload['certNumbers'][1]
    assert second['itemCount'] == 2 and second['pageIndex'] == 1
    assert second['validationToken'] == token
    assert second['page']['width_mm'] == 297
    assert second['page']['height_mm'] == 210
    assert first['html'].count('<div class="page">') == 1
    assert '第二位预览选手' not in first['html']
    assert '第二位预览选手' in second['html']
    assert 'onclick=' not in second['html']
    assert '<div class="no-print"' not in second['html']
    generated = api.json('/api/print/generate', 'POST', {**payload, 'validationToken': token})
    # The actual positioned field markup is identical to the final print output.
    page_markup = second['html'].split('<body>\n')[1].split('\n</body>')[0]
    assert page_markup in generated['html']
    assert api.json('/api/print/logs')['logs'] == []
    assert store.db.get_connection().total_changes == writes
    assert api.snapshot() == before


@pytest.mark.parametrize('index', [-1, 1, True, '0', None])
def test_preview_rejects_out_of_range_or_noninteger_page(batch, index):
    api, _, _, payload = batch
    token = api.json('/api/print/validate', 'POST', payload)['validationToken']
    response = api.response('/api/print/preview', 'POST', {**payload, 'validationToken': token, 'pageIndex': index})
    assert response['status'] == 400
    assert 'html' not in response['body']


def test_preview_requires_current_batch_token(batch):
    api, certificate, _, payload = batch
    assert api.response('/api/print/preview', 'POST', payload)['status'] == 409
    token = api.json('/api/print/validate', 'POST', payload)['validationToken']
    api.save(certificates=[{**certificate, 'playerName': '改过的姓名'}])
    response = api.response('/api/print/preview', 'POST', {**payload, 'validationToken': token})
    assert response['status'] == 409
    assert 'html' not in response['body']
