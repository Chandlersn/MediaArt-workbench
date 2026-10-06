"""Optional icon extraction must not prevent the archive module from loading."""

import ctypes
import importlib.util
from pathlib import Path
import platform
import sys
from types import SimpleNamespace

import pytest


def load_extractor():
    source = Path(__file__).resolve().parents[2] / 'server' / 'archive' / 'icon_extractor.py'
    spec = importlib.util.spec_from_file_location('_isolated_icon_extractor', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('system', ['Linux', 'Darwin'])
def test_non_windows_import_without_pillow_or_windows_loader(monkeypatch, system):
    monkeypatch.setattr(platform, 'system', lambda: system)
    monkeypatch.delattr(ctypes, 'windll', raising=False)
    monkeypatch.setitem(sys.modules, 'PIL', None)

    module = load_extractor()

    assert module._PIL_AVAILABLE is False
    assert module._WINDOWS_API_AVAILABLE is False
    assert module.get_file_icon('.pdf') is None
    assert module.get_folder_icon() is None


def test_windows_without_pillow_does_not_call_native_extractor(monkeypatch):
    class UnusedDLL:
        def __getattr__(self, name):
            raise AssertionError(f'Unexpected native API call: {name}')

    monkeypatch.setattr(platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(
        shell32=UnusedDLL(), user32=UnusedDLL(), gdi32=UnusedDLL()), raising=False)
    monkeypatch.setitem(sys.modules, 'PIL', None)

    module = load_extractor()

    assert module._WINDOWS_API_AVAILABLE is True
    assert module._PIL_AVAILABLE is False
    assert module.get_file_icon('.docx') is None
    assert module.get_folder_icon() is None


def test_windows_dll_failure_leaves_optional_api_unavailable(monkeypatch):
    class MissingDLLs:
        def __getattr__(self, name):
            raise OSError(f'DLL unavailable: {name}')

    monkeypatch.setattr(platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(ctypes, 'windll', MissingDLLs(), raising=False)
    monkeypatch.setitem(sys.modules, 'PIL', None)

    module = load_extractor()
    # The DLL guard must work independently of Pillow availability.
    monkeypatch.setattr(module, '_PIL_AVAILABLE', True)

    assert module._WINDOWS_API_AVAILABLE is False
    assert module.get_file_icon('.xlsx') is None
    assert module.get_folder_icon() is None
