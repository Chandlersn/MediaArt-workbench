"""Persistence tests use isolated databases, never the workbench's data files."""

import copy
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from server.database.db import Database, DataStore, SnapshotConflictError, WRITABLE_SECTIONS


@pytest.fixture
def store(tmp_path):
    db = Database(str(tmp_path / 'workbench.db'))
    result = DataStore(db)
    yield result
    db.close_connection()


@pytest.mark.parametrize('bad_projects', [
    {'id': 'p1', 'name': 'Wrong container'},
    [{'id': 'p1'}],
    [{'id': 'p1', 'name': 'Updated'}, None],
    [{'name': 'Missing identity'}],
    [{'id': 'p1', 'name': 'First'}, {'id': 'p1', 'name': 'Duplicate'}],
])
def test_invalid_records_preserve_original_rows(store, bad_projects):
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    before = store.load_all_data()
    assert not store.save_all_data({'projects': bad_projects, '_snapshot': True})
    assert store.load_all_data() == before
    assert store.db.fetchval('PRAGMA foreign_keys') == 1


def test_failure_in_later_section_rolls_back_every_section(store):
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    before = store.load_all_data()
    # The first section writes successfully, then the organization violates NOT NULL.
    assert not store.save_all_data({
        'projects': [{'id': 'p1', 'name': 'Changed'}],
        'organizations': [{'id': 'o1'}],
    })
    assert store.load_all_data() == before
    assert store.db.fetchval('PRAGMA foreign_keys') == 1


def test_unique_constraint_failure_does_not_drop_accounts(store):
    assert store.save_all_data({'users': [{'id': 'u1', 'username': 'original', 'password': 'hashed'}]})
    before = store.users.get_all()
    assert not store.save_all_data({'users': [
        {'id': 'u2', 'username': 'duplicate', 'password': 'hashed'},
        {'id': 'u3', 'username': 'duplicate', 'password': 'hashed'},
    ]})
    assert store.users.get_all() == before


def test_revisions_reject_stale_section_but_allow_independent_edits(store):
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    initial = store.load_all_data()
    revisions = {}
    assert store.save_all_data({
        'projects': [{'id': 'p1', 'name': 'A edited'}],
        '_revisions': initial['_revisions'],
    }, revision_result=revisions)
    assert revisions == {'projects': store.load_all_data()['_revisions']['projects']}
    assert store.save_all_data({
        'organizations': [{'id': 'o1', 'name': 'B added'}],
        '_revisions': initial['_revisions'],
    })
    with pytest.raises(SnapshotConflictError) as raised:
        store.save_all_data({'projects': initial['projects'], '_revisions': initial['_revisions']})
    assert raised.value.sections == ['projects']
    assert store.projects.get_by_id('p1')['name'] == 'A edited'
    assert store.organizations.get_by_id('o1')['name'] == 'B added'
    assert store.db.fetchval('PRAGMA foreign_keys') == 1


def test_missing_section_revision_is_a_conflict(store):
    with pytest.raises(SnapshotConflictError):
        store.save_all_data({'projects': [], '_revisions': {}})


def test_single_section_save_never_loads_unrelated_large_tables(store, monkeypatch):
    def unexpected_read(*_args, **_kwargs):
        pytest.fail('Project changes must not load unrelated audit/certificate data')

    monkeypatch.setattr(store.audit_logs, 'get_all', unexpected_read)
    monkeypatch.setattr(store.certificates, 'get_all', unexpected_read)
    baseline = store.load_all_data(sections={'projects'})
    assert set(baseline) == {'projects', '_revisions'}
    assert set(baseline['_revisions']) == {'projects'}
    revisions = {}
    assert store.save_all_data({
        'projects': [{'id': 'p1', 'name': 'Only project data'}],
        '_revisions': baseline['_revisions'],
    }, revision_result=revisions)
    assert set(revisions) == {'projects'}


def test_competing_writers_cannot_both_accept_same_revision(store):
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Original'}]})
    revisions = store.load_all_data()['_revisions']
    barrier = threading.Barrier(2)

    def write(name):
        barrier.wait(timeout=5)
        try:
            return store.save_all_data({
                'projects': [{'id': 'p1', 'name': name}], '_revisions': revisions,
            })
        except SnapshotConflictError:
            return 'conflict'
        finally:
            store.db.close_connection()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ('A', 'B')))
    assert results.count(True) == 1
    assert results.count('conflict') == 1


def test_snapshot_reads_and_revisions_share_consistent_view(store, monkeypatch):
    assert store.save_all_data({
        'projects': [{'id': 'p1', 'name': 'Old project'}],
        'organizations': [{'id': 'o1', 'name': 'Old organization'}],
    })
    expected = store.load_all_data()
    original_get = store.projects.get_all

    def read_projects_then_other_writer_commits(*args, **kwargs):
        projects = original_get(*args, **kwargs)
        other = sqlite3.connect(store.db.db_path)
        try:
            with other:
                other.execute("UPDATE projects SET name='New project'")
                other.execute("UPDATE organizations SET name='New organization'")
        finally:
            other.close()
        return projects

    monkeypatch.setattr(store.projects, 'get_all', read_projects_then_other_writer_commits)
    observed = store.load_all_data()
    assert observed == expected
    assert store.organizations.get_by_id('o1')['name'] == 'New organization'


def test_revision_hash_ignores_sql_row_order_but_preserves_nested_order(store):
    one = {'projects': [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}],
           'projectChecklists': {'p1': {'items': ['first', 'second']}}}
    two = copy.deepcopy(one)
    two['projects'].reverse()
    assert store._snapshot_revisions(one) == store._snapshot_revisions(two)
    two['projectChecklists']['p1']['items'].reverse()
    assert store._snapshot_revisions(one)['projectChecklists'] != store._snapshot_revisions(two)['projectChecklists']


def test_parent_replacement_preserves_children_and_rejects_deleting_used_parent(store):
    assert store.save_all_data({
        'projects': [{'id': 'p1', 'name': 'Original'}],
        'players': [{'id': 'pl1', 'name': 'Player', 'projectId': 'p1', 'orgId': ''}],
    })
    assert store.players.get_by_id('pl1')['orgId'] is None
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Renamed'}]})
    assert store.players.get_by_id('pl1')['projectId'] == 'p1'
    assert not store.save_all_data({'projects': [], '_snapshot': True})
    assert store.projects.get_by_id('p1')['name'] == 'Renamed'
    assert store.db.fetchval('PRAGMA foreign_keys') == 1
    assert store.db.fetchall('PRAGMA foreign_key_check') == []


def test_preexisting_orphans_do_not_block_unrelated_edits(store):
    conn = store.db.get_connection()
    conn.execute('PRAGMA foreign_keys=OFF')
    with store.db.transaction():
        conn.execute("INSERT INTO players (id,name,project_id) VALUES ('pl1','Legacy','missing')")
    conn.execute('PRAGMA foreign_keys=ON')
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'New'}]})
    assert store.save_all_data({'players': [{'id': 'pl1', 'name': 'Renamed legacy', 'projectId': 'missing'}]})
    assert not store.save_all_data({'players': [{'id': 'pl1', 'name': 'Invalid new reference', 'projectId': 'different'}]})
    assert store.players.get_by_id('pl1')['name'] == 'Renamed legacy'
    assert store.db.fetchval('PRAGMA foreign_keys') == 1


def test_separate_database_paths_do_not_share_connections(store, tmp_path):
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'First DB'}]})
    second_db = Database(str(tmp_path / 'second.db'))
    try:
        second = DataStore(second_db)
        assert second.projects.count() == 0
        assert second.save_all_data({'projects': [{'id': 'p2', 'name': 'Second DB'}]})
        assert store.projects.get_by_id('p1')['name'] == 'First DB'
        assert store.projects.get_by_id('p2') is None
    finally:
        second_db.close_connection()


def test_complete_business_snapshot_round_trip(store, tmp_path):
    snapshot = {
        'projects': [{'id': 'p1', 'name': 'Project'}],
        'organizations': [{'id': 'o1', 'name': 'Organization'}],
        'players': [{'id': 'pl1', 'name': 'Player', 'projectId': 'p1', 'orgId': 'o1'}],
        'finances': [{'id': 'f1', 'amount': 10, 'projectId': 'p1', 'orgId': 'o1'}],
        'users': [{'id': 'u1', 'username': 'admin', 'password': 'hash', 'role': 'admin'}],
        'config': {'stages': [], 'resourceCategories': ['Pictures']},
        'materialTypes': [{'id': 'm1', 'name': 'Photo'}],
        'knowledge': {'guide': [{'id': 'k1', 'title': 'Guide', 'fields': {'body': 'Text'}}]},
        'notifications': [{'id': f'n{i}', 'title': f'Notification {i}'} for i in range(55)],
        'auditLogs': [{'id': f'a{i}', 'action': 'create'} for i in range(105)],
        'templates': {'categories': ['Documents'], 'items': [{'id': 't1', 'name': 'Contract'}]},
        'checklistState': {'p1:check': True},
        'checklists': [{'id': 'c1', 'title': 'Checklist', 'items': ['First']}],
        'certificates': [{'certNumber': 'C1', 'sessionId': 's1', 'playerName': 'Player'}],
        'certSettings': {'prefix': 'C'},
        'printTemplates': [{'id': 'pt1', 'name': 'Print', 'background': 'template.png', 'fields': []}],
        'projectChecklists': {'p1': {'cards': [{'id': 'card1', 'items': []}]}},
        'archiveConfig': {'players': {'materialTypes': []}},
        'archiveMappings': {'p1': 'Project folder'},
        '_snapshot': True,
    }
    assert store.save_all_data(snapshot)
    exported = store.load_all_data()
    assert len(exported['auditLogs']) == 105
    assert len(exported['notifications']) == 55
    assert exported['archiveMappings'] == snapshot['archiveMappings']
    assert exported['checklistState'] == snapshot['checklistState']
    assert exported['config']['stages'] == []
    target_db = Database(str(tmp_path / 'restored.db'))
    try:
        target = DataStore(target_db)
        exported.pop('_revisions')
        exported['_snapshot'] = True
        assert target.save_all_data(exported)
        restored = target.load_all_data()
        for section in WRITABLE_SECTIONS:
            if isinstance(restored[section], list):
                def row_key(row):
                    return (row.get('id', row.get('certNumber')), row.get('sessionId', ''))
                assert sorted(restored[section], key=row_key) == sorted(exported[section], key=row_key), section
            else:
                assert restored[section] == exported[section], section
    finally:
        target_db.close_connection()


def test_wal_backup_contains_committed_rows_and_restores_through_sqlite(store, tmp_path, monkeypatch):
    import server.database.migrate as migration
    monkeypatch.setattr(migration, 'get_data_store', lambda: store)
    monkeypatch.setattr(migration, 'DB_FILE', store.db.db_path)
    monkeypatch.setattr(migration, 'JSON_FILE', str(tmp_path / 'nonexistent.json'))
    monkeypatch.setattr(migration, 'BACKUP_DIR', str(tmp_path / 'backup'))
    migrator = migration.DataMigrator()
    store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
    store.projects.create({'id': 'p1', 'name': 'Committed WAL record'})
    backup = migrator.create_backup()
    assert backup
    copied = sqlite3.connect(str(Path(backup) / 'workbench.db'))
    try:
        assert copied.execute("SELECT name FROM projects WHERE id='p1'").fetchone()[0] == 'Committed WAL record'
    finally:
        copied.close()
    store.projects.update('p1', {'name': 'Changed later'})
    assert migrator.rollback_from_backup(Path(backup).name)
    assert store.projects.get_by_id('p1')['name'] == 'Committed WAL record'


def test_import_discards_source_revisions_and_restores_empty_sections(store, tmp_path):
    backup = store.load_all_data()
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'After backup'}]})
    path = tmp_path / 'snapshot.json'
    path.write_text(json.dumps(backup), encoding='utf-8')
    assert store.import_from_json(str(path))
    assert store.projects.count() == 0


@pytest.mark.parametrize('automatic', [False, True])
def test_legacy_migration_discards_source_revisions(store, tmp_path, monkeypatch, automatic):
    import server.database.auto_migrate as automatic_migration
    import server.database.migrate as migration

    original = store.load_all_data()
    assert store.save_all_data({'projects': [{'id': 'p1', 'name': 'Later edit'}]})
    source = tmp_path / 'migration.json'
    source.write_text(json.dumps(original), encoding='utf-8')
    module = automatic_migration if automatic else migration
    monkeypatch.setattr(module, 'get_data_store', lambda: store)
    monkeypatch.setattr(module, 'JSON_FILE', str(source))
    if automatic:
        assert module.auto_migrate()
    else:
        assert module.DataMigrator().migrate_json_to_sqlite(create_backup=False)
    assert store.projects.count() == 0


def test_numeric_legacy_identities_and_references_survive_import(store):
    assert store.save_all_data({
        'projects': [{'id': 10, 'name': 'Legacy project'}],
        'organizations': [{'id': 20, 'name': 'Legacy organization'}],
        'players': [{'id': 30, 'name': 'Legacy player', 'projectId': 10, 'orgId': 20}],
        'certificates': [{'certNumber': 1001, 'sessionId': 1}],
        'printTemplates': [{'id': 40, 'name': 'Legacy print', 'fields': []}],
    })
    snapshot = store.load_all_data()
    assert snapshot['projects'][0]['id'] == '10'
    assert snapshot['players'][0]['projectId'] == '10'
    assert snapshot['certificates'][0]['certNumber'] == '1001'
    assert snapshot['certificates'][0]['sessionId'] == '1'
    assert snapshot['printTemplates'][0]['id'] == '40'
    assert not store.save_all_data({'projects': [
        {'id': 10, 'name': 'Numeric'}, {'id': '10', 'name': 'Same ID as string'},
    ]})
    assert store.projects.get_by_id('10')['name'] == 'Legacy project'


def test_template_backup_preserves_additional_structure(store):
    templates = {
        'categories': [], 'items': [],
        'customMetadata': {'schemaVersion': 5, 'settings': ['keep', 'order']},
    }
    assert store.save_all_data({'templates': templates})
    assert store.load_all_data()['templates'] == templates


def test_schema_initialization_never_commits_outer_transaction(store):
    with pytest.raises(RuntimeError, match='abort fixture'):
        with store.db.transaction() as conn:
            conn.execute("INSERT INTO projects (id,name) VALUES ('p1','Uncommitted')")
            # Both initialization paths used executescript(), which commits any
            # pending transaction before executing its first statement.
            store.db._create_tables()
            store._ensure_certificates_table()
            raise RuntimeError('abort fixture')
    assert store.projects.count() == 0


def test_script_failure_rolls_back_earlier_statements(store):
    with pytest.raises(sqlite3.OperationalError):
        store.db.execute_script(
            "INSERT INTO projects (id,name) VALUES ('p1','Name; with delimiter');"
            "INSERT INTO missing_table VALUES (1);"
        )
    assert store.projects.count() == 0


def test_admin_export_restore_preserves_password_hashes(store, tmp_path, monkeypatch):
    import importlib.util
    import sys
    import types
    import bcrypt
    from server import config

    # Load the real router with an isolated singleton, before any route import
    # could initialize the application's default database.
    singleton = types.ModuleType('server.database.store')
    singleton.data_store = store
    monkeypatch.setitem(sys.modules, 'server.database.store', singleton)
    monkeypatch.setattr(config, 'BASE_DIR', str(tmp_path))
    monkeypatch.setenv('WORKBENCH_JWT_SECRET', 'isolated-persistence-regression-secret')
    path = Path(__file__).resolve().parents[2] / 'server/resources/routes.py'
    spec = importlib.util.spec_from_file_location('_password_restore_regression', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'extract_user_from_request', lambda rc: {'user_id': 'u1', 'role': 'admin'})
    router = module.ResourcesRouter()
    password = b'Fixture-password-2026'
    hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=4)).decode()
    assert store.save_all_data({'users': [{
        'id': 'u1', 'username': 'fixture-admin', 'password': hashed,
        'passwordHashed': True, 'role': 'admin', 'isActive': True,
    }]})
    exported = router.handle_request({'path': '/api/data/export', 'method': 'GET', 'headers': {}})
    assert exported['status'] == 200
    saved_user = exported['body']['data']['users'][0]
    assert saved_user['password'] == hashed
    assert saved_user['passwordHashed'] == 1
    store.users.update('u1', {'password': 'changed later'})
    restored = router._restore_payload(exported['body']['data'])
    assert restored['status'] == 200
    assert bcrypt.checkpw(password, store.users.get_by_id('u1')['password'].encode())
    # A historical redacted export must fail atomically, not erase accounts.
    del saved_user['password']
    assert router._restore_payload(exported['body']['data'])['status'] == 400
    assert store.users.get_by_id('u1')['password'] == hashed
