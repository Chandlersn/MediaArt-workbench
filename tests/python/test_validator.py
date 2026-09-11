# -*- coding: utf-8 -*-
"""
验证器模块测试
"""
import pytest
from server.utils.validator import Validator, FormSchemas


class TestValidatorRequired:
    """测试必填字段验证"""

    def test_valid_required_field(self):
        """有效的必填字段"""
        result = Validator.validate_required('test', '字段名')
        assert result['valid'] is True

    def test_empty_required_field(self):
        """空的必填字段"""
        result = Validator.validate_required('', '字段名')
        assert result['valid'] is False
        assert '字段名' in result['message']

    def test_whitespace_only_field(self):
        """只有空白的字段"""
        result = Validator.validate_required('   ', '字段名')
        assert result['valid'] is False

    def test_none_value(self):
        """None 值"""
        result = Validator.validate_required(None, '字段名')
        assert result['valid'] is False


class TestValidatorUsername:
    """测试用户名验证"""

    def test_valid_username(self):
        """有效的用户名 - 字母开头，3-20位"""
        result = Validator.validate('admin123', 'username')
        assert result['valid'] is True

    def test_username_too_short(self):
        """用户名太短"""
        result = Validator.validate('ab', 'username')
        assert result['valid'] is False

    def test_username_too_long(self):
        """用户名太长"""
        result = Validator.validate('a' * 25, 'username')
        assert result['valid'] is False

    def test_username_starts_with_number(self):
        """用户名以数字开头"""
        result = Validator.validate('1admin', 'username')
        assert result['valid'] is False


class TestValidatorPassword:
    """测试密码验证"""

    def test_valid_password(self):
        """有效的密码 - 至少6位，包含字母和数字"""
        result = Validator.validate('password123', 'password')
        assert result['valid'] is True

    def test_password_too_short(self):
        """密码太短"""
        result = Validator.validate('ab12', 'password')
        assert result['valid'] is False

    def test_password_no_number(self):
        """密码没有数字"""
        result = Validator.validate('password', 'password')
        assert result['valid'] is False


class TestValidatorRole:
    """测试角色验证"""

    def test_valid_admin_role(self):
        """有效的 admin 角色"""
        result = Validator.validate_enum('admin', ['admin', 'editor', 'viewer'])
        assert result['valid'] is True

    def test_valid_editor_role(self):
        """有效的 editor 角色"""
        result = Validator.validate_enum('editor', ['admin', 'editor', 'viewer'])
        assert result['valid'] is True

    def test_valid_viewer_role(self):
        """有效的 viewer 角色"""
        result = Validator.validate_enum('viewer', ['admin', 'editor', 'viewer'])
        assert result['valid'] is True

    def test_invalid_role(self):
        """无效的角色"""
        result = Validator.validate_enum('superadmin', ['admin', 'editor', 'viewer'])
        assert result['valid'] is False


class TestValidatorAll:
    """测试综合验证"""

    def test_validate_all_user_valid(self):
        """有效的用户数据"""
        data = {
            'username': 'testuser',
            'password': 'testpass123',  # 包含字母和数字
            'role': 'editor'
        }
        valid, errors = Validator.validate_all(data, FormSchemas.USER)
        assert valid is True
        assert len(errors) == 0

    def test_validate_all_user_invalid(self):
        """无效的用户数据"""
        data = {
            'username': '',  # 空
            'password': 'abc',  # 太短且无数字
            'role': 'invalid'  # 无效角色
        }
        valid, errors = Validator.validate_all(data, FormSchemas.USER)
        assert valid is False
        assert len(errors) > 0