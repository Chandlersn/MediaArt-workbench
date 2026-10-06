"""Real temporary files/index and API checks for rename/recycle operations."""
import importlib
import os
from pathlib import Path
import subprocess

import pytest

from test_business_workflow import workflow_api  # noqa: F401


@pytest.fixture
def files(workflow_api):
    api = workflow_api
    metadata = importlib.import_module('server.materials.metadata')
    trash = importlib.import_module('server.utils.trash')
    archive = importlib.import_module('server.archive.routes')
    root = Path(archive.ARCHIVE_DIR)
    folder = root / 'player' / 'documents'
    name = metadata.store_material_file(str(folder), 'form.pdf', b'entry-form', '报名表', '初赛')
    return api, metadata, trash, root, folder / name


def fail_index(_entries):
    raise OSError('Index write unavailable')


@pytest.mark.parametrize('directory', [False, True])
@pytest.mark.parametrize('fail', [False, True])
def test_archive_rename_moves_classification_or_rolls_back(files, monkeypatch, directory, fail):
    api, metadata, _, root, source = files
    original = metadata.get_metadata(str(source))
    if fail:
        monkeypatch.setattr(metadata, '_write_index', fail_index)
    if directory:
        endpoint = '/api/rename-folder'
        payload = {'oldPath': source.parent.relative_to(root).as_posix(), 'newPath': 'renamed'}
        target = source.parent.with_name('renamed') / source.name
    else:
        endpoint = '/api/rename-file'
        payload = {'path': source.relative_to(root).as_posix(), 'newName': 'renamed.pdf'}
        target = source.with_name('renamed.pdf')
    response = api.response(endpoint, 'PUT', payload)
    assert response['status'] == (500 if fail else 200)
    assert response['body']['success'] is not fail
    retained = source if fail else target
    assert retained.read_bytes() == b'entry-form'
    assert metadata.get_metadata(str(retained)) == original
    assert not (target if fail else source).exists()


def test_recycle_restore_retains_exact_type_and_stage(files):
    _, metadata, trash, _, source = files
    original = metadata.get_metadata(str(source))
    rid = trash.send_to_trash(str(source.parent))
    recycled = Path(trash.TRASH_DIR) / rid / source.name
    assert not source.exists()
    assert metadata.get_metadata(str(recycled)) == original
    assert trash.restore_trash(rid)[0] is True
    assert source.read_bytes() == b'entry-form'
    assert metadata.get_metadata(str(source)) == original
    assert not recycled.exists()


@pytest.mark.parametrize('directory', [False, True])
def test_failed_recycle_keeps_original_and_reports_api_failure(files, monkeypatch, directory):
    api, metadata, trash, root, source = files
    original = metadata.load_metadata()
    monkeypatch.setattr(metadata, '_write_index', fail_index)
    path = source.parent if directory else source
    response = api.response('/api/delete-folder' if directory else '/api/delete-file', 'DELETE',
                            query={'path': path.relative_to(root).as_posix()})
    assert response['status'] == 500
    assert response['body']['success'] is False
    assert source.read_bytes() == b'entry-form'
    assert metadata.load_metadata() == original
    assert trash.list_trash() == []


def test_failed_restore_keeps_recycled_file_and_metadata(files, monkeypatch):
    _, metadata, trash, _, source = files
    rid = trash.send_to_trash(str(source))
    original = metadata.load_metadata()
    monkeypatch.setattr(metadata, '_write_index', fail_index)
    assert trash.restore_trash(rid)[0] is False
    assert not source.exists()
    assert (Path(trash.TRASH_DIR) / rid).read_bytes() == b'entry-form'
    assert metadata.load_metadata() == original
    assert len(trash.list_trash()) == 1


def test_purge_removes_index_only_after_file_deletion_and_allows_retry(files, monkeypatch):
    _, metadata, trash, _, source = files
    rid = trash.send_to_trash(str(source.parent))
    original = metadata.load_metadata()
    with monkeypatch.context() as patch:
        def denied(*_args, **_kwargs):
            raise PermissionError('Cannot remove directory')
        patch.setattr(trash.shutil, 'rmtree', denied)
        assert trash.purge_trash(rid) is False
    assert metadata.load_metadata() == original
    assert (Path(trash.TRASH_DIR) / rid / source.name).exists()
    with monkeypatch.context() as patch:
        patch.setattr(metadata, '_write_index', fail_index)
        assert trash.purge_trash(rid) is False
    assert not (Path(trash.TRASH_DIR) / rid).exists()
    assert len(trash.list_trash()) == 1
    assert trash.purge_trash(rid) is True
    assert metadata.load_metadata() == {}
    assert trash.list_trash() == []


def test_purge_all_cleans_each_files_classification(files):
    _, metadata, trash, _, source = files
    other_name = metadata.store_material_file(str(source.parent), 'identity.pdf', b'id', '身份证')
    assert trash.send_to_trash(str(source))
    assert trash.send_to_trash(str(source.with_name(other_name)))
    assert trash.purge_all() == 2
    assert metadata.load_metadata() == {}
    assert trash.list_trash() == []


@pytest.mark.parametrize('name', ['../escape', '..\\escape', '/escape', 'C:\\escape', '.', '..', 'name.', 'name:stream'])
def test_folder_rename_rejects_paths_instead_of_names(files, name):
    api, _, _, root, source = files
    response = api.response('/api/rename-folder', 'PUT', {
        'oldPath': source.parent.relative_to(root).as_posix(), 'newPath': name,
    })
    assert response['status'] == 400
    assert source.read_bytes() == b'entry-form'


@pytest.mark.parametrize('rid', ['../../outside', '..\\..\\outside', '.', '..', 'C:\\outside', 'id:stream', 'id.'])
def test_trash_ids_cannot_target_paths(files, rid):
    api, _, trash, _, source = files
    outside = api.root / 'outside'
    outside.mkdir()
    (outside / 'keep.txt').write_bytes(b'keep')
    assert trash.purge_trash(rid) is False
    assert trash.restore_trash(rid)[0] is False
    assert (outside / 'keep.txt').read_bytes() == b'keep'
    assert source.exists()


def directory_link(link, target, test_root):
    assert link.absolute().is_relative_to(test_root.resolve())
    assert target.resolve().is_relative_to(test_root.resolve())
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('Directory links unavailable')
        # Junction creation needs no developer-mode symlink privilege. Both
        # sides are test-owned; teardown uses rmdir to unlink, never recurse.
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True, timeout=10)
        if result.returncode:
            pytest.skip('Directory junctions unavailable')


def test_archive_and_trash_reject_links_outside_their_roots(files):
    api, _, trash, root, _ = files
    outside = api.root / 'outside'
    outside.mkdir()
    sentinel = outside / 'keep.txt'
    sentinel.write_bytes(b'keep')
    archive_link = root / 'escape'
    trash_root = Path(trash.TRASH_DIR)
    trash_root.mkdir(parents=True, exist_ok=True)
    trash_link = trash_root / 'escape'
    try:
        directory_link(archive_link, outside, api.root)
        directory_link(trash_link, outside, api.root)
        response = api.response('/api/rename-file', 'PUT', {'path': 'escape/keep.txt', 'newName': 'moved.txt'})
        assert response['status'] >= 400
        assert trash.purge_trash('escape') is False
        assert trash.restore_trash('escape')[0] is False
        assert sentinel.read_bytes() == b'keep'
        assert not (outside / 'moved.txt').exists()
    finally:
        for link in (archive_link, trash_link):
            if link.exists():
                os.rmdir(link)


def test_restore_rejects_redirected_original_parent(files):
    api, _, trash, _, source = files
    rid = trash.send_to_trash(str(source))
    source.parent.rmdir()
    outside = api.root / 'outside'
    outside.mkdir()
    try:
        directory_link(source.parent, outside, api.root)
        assert trash.restore_trash(rid)[0] is False
        assert not (outside / source.name).exists()
        assert (Path(trash.TRASH_DIR) / rid).read_bytes() == b'entry-form'
    finally:
        if source.parent.exists():
            os.rmdir(source.parent)
