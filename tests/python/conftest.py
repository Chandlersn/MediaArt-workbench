# -*- coding: utf-8 -*-
"""
pytest 配置文件
提供测试 fixtures 和公共配置
"""
import os
import sys
import json
import pytest
import tempfile
import shutil

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_data_dir():
    """临时数据目录 fixture"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        'id': 'u123456',
        'username': 'testuser',
        'role': 'editor',
        'createdAt': '2024-01-01 10:00:00'
    }


@pytest.fixture
def sample_project_data():
    """示例项目数据"""
    return {
        'id': 'p001',
        'name': '测试项目',
        'status': 'planning',
        'startDate': '2024-01-01',
        'endDate': '2024-12-31'
    }


@pytest.fixture
def mock_data_file(temp_data_dir):
    """模拟数据文件"""
    data_file = os.path.join(temp_data_dir, 'workbench_data.json')
    sample_data = {
        'projects': [],
        'organizations': [],
        'players': [],
        'finances': [],
        'users': [{
            'id': 'u001',
            'username': 'admin',
            'password': '$2b$12$test_hashed_password',
            'passwordHashed': True,
            'role': 'admin'
        }],
        'auditLogs': []
    }
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f)
    return data_file


@pytest.fixture
def mock_env(monkeypatch, temp_data_dir):
    """模拟环境变量"""
    monkeypatch.setenv('DATA_DIR', temp_data_dir)
    return temp_data_dir