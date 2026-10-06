"""Certificate preflight through real JWT/API/SQLite, plus pure rendering edges."""
import importlib
import re

import bcrypt
import pytest

from test_business_workflow import (  # noqa: F401
    workflow_api, create_project_and_player, create_certificate_template,
)


@pytest.fixture
def batch(workflow_api):
    api = workflow_api
    create_project_and_player(api)
    certificate, template = create_certificate_template(api)
    payload = {'templateId': template['id'], 'certNumbers': [
        {'certNumber': certificate['certNumber'], 'sessionId': certificate['sessionId']},
    ]}
    return api, certificate, template, payload


def field(column, **options):
    return {'column': column, 'x': 50, 'y': 40, **options}


def test_preflight_uses_only_selected_fields_and_rows_without_writes(batch):
    api, certificate, template, payload = batch
    selected = {**certificate, 'workName': '', 'award': '（待定）', 'instructor': '很长的指导老师姓名', 'language': 0}
    unrelated = {**certificate, 'certNumber': 'OTHER', 'playerName': '', 'award': ''}
    template['fields'] = [field('work_name'), field('award'),
                          field('instructor', x=99, align='left', fontSize=36), field('language')]
    api.save(certificates=[selected, unrelated], printTemplates=[template])
    before = api.snapshot()
    store = importlib.import_module('server.database.store').data_store
    writes = store.db.get_connection().total_changes
    files = {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()}

    result = api.json('/api/print/validate', 'POST', payload)
    assert result['itemCount'] == 1
    assert result['issueCount'] == 3
    assert result['canGenerate'] is True
    assert result['truncated'] is False
    assert {(issue['kind'], issue['column']) for issue in result['issues']} == {
        ('empty', 'workName'), ('placeholder', 'award'), ('overlong', 'instructor'),
    }
    assert all(issue['reference'] == payload['certNumbers'][0] for issue in result['issues'])
    assert all(issue['playerName'] == certificate['playerName'] for issue in result['issues'])
    assert all(issue['severity'] == 'warning' for issue in result['issues'])
    assert api.json('/api/print/validate', 'POST', payload) == result
    assert store.db.get_connection().total_changes == writes
    assert api.snapshot() == before
    assert api.json('/api/print/logs')['logs'] == []
    assert {p.relative_to(api.root) for p in api.root.rglob('*') if p.is_file()} == files


def test_supplement_recheck_and_generate_share_values_and_invalidate_old_check(batch):
    api, certificate, template, payload = batch
    template['fields'] = [field('work_name'), {**field('award'), 'column': '', 'dbColumn': 'award'}]
    api.save(certificates=[{**certificate, 'workName': '', 'award': '——'}], printTemplates=[template])
    original = api.json('/api/print/validate', 'POST', payload)
    assert original['issueCount'] == 2
    generated = api.json('/api/print/generate', 'POST', {**payload, 'validationToken': original['validationToken']})
    assert generated['warnings'] == [{'column': 'workName', 'label': '作品名称', 'count': 1}]
    api.save(certificates=[{**certificate, 'workName': '补录作品', 'award': '金奖'}])
    expired = api.response('/api/print/generate', 'POST', {**payload, 'validationToken': original['validationToken']})
    assert expired['status'] == 409
    assert '重新检查' in expired['body']['message']
    assert 'html' not in expired['body']
    checked = api.json('/api/print/validate', 'POST', payload)
    assert checked['issueCount'] == 0
    assert checked['validationToken'] != original['validationToken']
    printed = api.json('/api/print/generate', 'POST', {**payload, 'validationToken': checked['validationToken']})
    assert printed['warnings'] == []
    assert '补录作品' in printed['html'] and '金奖' in printed['html']
    assert 'font-size:12pt;' in printed['html']


@pytest.mark.parametrize('change', ['template', 'record', 'order'])
def test_validation_token_covers_template_records_and_print_order(batch, change):
    api, certificate, template, payload = batch
    other = {**certificate, 'certNumber': 'WORKFLOW-002', 'playerName': '第二位选手'}
    api.save(certificates=[certificate, other])
    payload['certNumbers'].append({'certNumber': other['certNumber'], 'sessionId': other['sessionId']})
    token = api.json('/api/print/validate', 'POST', payload)['validationToken']
    if change == 'template':
        template['fields'][0]['x'] = 60
        api.save(printTemplates=[template])
    elif change == 'record':
        api.save(certificates=[certificate, {**other, 'playerName': '修改姓名'}])
    else:
        payload['certNumbers'].reverse()
    response = api.response('/api/print/generate', 'POST', {**payload, 'validationToken': token})
    assert response['status'] == 409
    assert 'html' not in response['body']


def test_unselected_certificate_changes_do_not_invalidate_selected_batch(batch):
    api, certificate, _, payload = batch
    token = api.json('/api/print/validate', 'POST', payload)['validationToken']
    api.save(certificates=[certificate, {**certificate, 'certNumber': 'UNSELECTED', 'award': ''}])
    checked = api.json('/api/print/validate', 'POST', payload)
    assert checked['validationToken'] == token
    assert api.json('/api/print/generate', 'POST', {**payload, 'validationToken': token})['itemCount'] == 1


@pytest.mark.parametrize('invalid', [
    field('unknown_field'), field('playerName', x=0), field('playerName', x=0, align='right'),
    field('playerName', y=100), field('playerName', x='bad'), field('playerName', fontSize=0),
    field('playerName', fontSize='Infinity'), field('playerName', align='invalid'), None,
])
def test_invalid_fields_and_layout_block_generation(batch, invalid):
    api, _, template, payload = batch
    template['fields'] = [invalid]
    api.save(printTemplates=[template])
    result = api.json('/api/print/validate', 'POST', payload)
    assert result['canGenerate'] is False
    assert result['issueCount'] == 1
    issue = result['issues'][0]
    assert issue['severity'] == 'error'
    assert issue['reference'] is None
    assert issue['kind'] in ('missing-field', 'layout')
    if isinstance(invalid, dict) and invalid['column'] == 'unknown_field':
        assert issue['column'] == 'unknownField'
    response = api.response('/api/print/generate', 'POST', payload)
    assert response['status'] == 400
    assert 'html' not in response['body']


@pytest.mark.parametrize('key,value', [('background', ''), ('fields', []), ('pageSize', 'missing-size')])
def test_invalid_template_reports_actionable_error(batch, key, value):
    api, _, template, payload = batch
    api.save(printTemplates=[{**template, key: value}])
    checked = api.json('/api/print/validate', 'POST', payload)
    assert checked['canGenerate'] is False
    assert checked['issues'][0]['kind'] == 'layout'
    assert checked['issues'][0]['reference'] is None


@pytest.mark.parametrize('endpoint', ['/api/print/validate', '/api/print/generate'])
@pytest.mark.parametrize('missing', ['certificate', 'session', 'template'])
def test_missing_selection_never_silently_prints_remaining_records(batch, endpoint, missing):
    api, certificate, _, payload = batch
    if missing == 'template':
        payload['templateId'] = 'missing-template'
    else:
        payload['certNumbers'].append({
            'certNumber': 'missing-certificate' if missing == 'certificate' else certificate['certNumber'],
            'sessionId': certificate['sessionId'] if missing == 'certificate' else 'missing-session',
        })
    response = api.response(endpoint, 'POST', payload)
    assert response['status'] == 404
    assert response['body']['success'] is False
    assert 'html' not in response['body']


def test_explicit_session_selects_only_that_certificate_and_legacy_strings_must_be_unique(batch):
    api, certificate, _, payload = batch
    assert api.json('/api/print/validate', 'POST', {**payload, 'certNumbers': [certificate['certNumber']]})['itemCount'] == 1
    other = {**certificate, 'sessionId': 'another-session', 'award': ''}
    api.save(certificates=[certificate, other])
    assert api.json('/api/print/validate', 'POST', payload)['issueCount'] == 0
    ambiguous = api.response('/api/print/validate', 'POST', {**payload, 'certNumbers': [certificate['certNumber']]})
    assert ambiguous['status'] == 400
    assert '多个批次' in ambiguous['body']['message']


@pytest.mark.parametrize('stored,requested', [('', 'legacy-import'), ('legacy-import', '')])
def test_empty_historical_session_has_unique_legacy_alias(batch, stored, requested):
    api, certificate, _, payload = batch
    store = importlib.import_module('server.database.store').data_store
    # The normal save API migrates old empty sessions; seed the historical row
    # directly in this test-owned database to model an untouched older install.
    store.db.execute('UPDATE certificates SET session_id = ? WHERE cert_number = ?', (stored, certificate['certNumber']))
    payload['certNumbers'][0]['sessionId'] = requested
    assert api.json('/api/print/validate', 'POST', payload)['itemCount'] == 1
    other = {**certificate, 'sessionId': 'another-session'}
    store.certificates.create(other)
    assert api.json('/api/print/generate', 'POST', payload)['itemCount'] == 1
    with store.db.transaction() as conn:
        conn.execute('INSERT INTO certificates (cert_number, session_id, player_name) VALUES (?, ?, ?)',
                     (certificate['certNumber'], '' if stored else 'legacy-import', 'Ambiguous'))
    assert api.response('/api/print/validate', 'POST', payload)['status'] == 400


def test_issue_limit_reports_total_and_does_not_hide_template_blocker(batch):
    api, certificate, template, payload = batch
    records = [{**certificate, 'certNumber': f'BATCH-{i}', 'workName': '很' * 1000} for i in range(205)]
    template['fields'] = [field('workName', x=99, align='left'), field('unknown')]
    api.save(certificates=records, printTemplates=[template])
    payload['certNumbers'] = [{'certNumber': r['certNumber'], 'sessionId': r['sessionId']} for r in records]
    result = api.json('/api/print/validate', 'POST', payload)
    assert result['itemCount'] == 205
    assert result['issueCount'] == 206
    assert result['truncated'] is True
    assert len(result['issues']) == 200
    assert result['canGenerate'] is False
    assert result['issues'][0]['kind'] == 'missing-field'
    assert len(result['issues'][1]['value']) == 500


def test_zero_and_false_are_not_empty_in_check_or_render(batch):
    api, certificate, template, payload = batch
    template['fields'] = [field('award'), field('language')]
    api.save(certificates=[{**certificate, 'award': 0, 'language': 0}], printTemplates=[template])
    assert api.json('/api/print/validate', 'POST', payload)['issueCount'] == 0
    html = api.json('/api/print/generate', 'POST', payload)['html']
    assert html.count('>0</div>') == 2
    preflight = importlib.import_module('server.print.preflight')
    printing = importlib.import_module('server.print.routes')
    record = {**certificate, 'award': 0, 'language': False}
    checked = preflight.inspect_batch(template, [record], {'award', 'language'}, printing.PAGE_SIZES)
    assert checked['issueCount'] == 0
    assert '>False</div>' in printing.build_html(template, [record])


def test_numeric_layout_strings_are_rendered_as_the_values_that_were_checked(batch):
    api, _, template, payload = batch
    template['fields'] = [field('playerName', x='50 ', y=' 4e1 ', fontSize=' 18 ')]
    api.save(printTemplates=[template])
    checked = api.json('/api/print/validate', 'POST', payload)
    assert checked['canGenerate'] is True and checked['issueCount'] == 0
    html = api.json('/api/print/generate', 'POST', {**payload, 'validationToken': checked['validationToken']})['html']
    assert re.search(r'left:50(?:\.0)?%;', html)
    assert re.search(r'top:40(?:\.0)?%;', html)
    assert re.search(r'font-size:18(?:\.0)?pt;', html)
    assert '50 %' not in html and '18 pt' not in html


@pytest.mark.parametrize('payload', [None, [], {}, {'templateId': 3, 'certNumbers': ['A']},
                                   {'templateId': 'workflow-template', 'certNumbers': [{}]},
                                   {'templateId': 'workflow-template', 'certNumbers': ['A'], 'sessionId': []}])
def test_invalid_requests_return_400(batch, payload):
    api, _, _, _ = batch
    assert api.response('/api/print/validate', 'POST', payload)['status'] == 400


def test_validate_has_same_auth_and_permission_boundary_as_generate(batch):
    api, _, _, payload = batch
    for endpoint in ('/api/print/validate', '/api/print/generate', '/api/print/preview'):
        assert api.response(endpoint, 'POST', payload, authenticated=False)['status'] == 401
    store = importlib.import_module('server.database.store').data_store
    store.users.create({'id': 'no-print-user', 'username': 'no-print-user', 'role': 'no-print-role',
                        'password': bcrypt.hashpw(b'No-print-password', bcrypt.gensalt(rounds=4)).decode()})
    api.token = api.json('/api/auth/login', 'POST', {'username': 'no-print-user', 'password': 'No-print-password'},
                         authenticated=False)['access_token']
    for endpoint in ('/api/print/validate', '/api/print/generate', '/api/print/preview'):
        assert api.response(endpoint, 'POST', payload)['status'] == 403
