# -*- coding: utf-8 -*-
"""
权限模块测试
"""
import pytest
from server.utils.permissions import (
    has_permission,
    get_role_permissions,
    get_role_level,
    is_admin,
    is_editor_or_above,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS
)


class TestRoleHierarchy:
    """测试角色层级"""

    def test_admin_has_highest_level(self):
        """admin 应该有最高层级"""
        assert get_role_level('admin') >= get_role_level('editor')
        assert get_role_level('admin') >= get_role_level('viewer')

    def test_editor_above_viewer(self):
        """editor 应该高于 viewer"""
        assert get_role_level('editor') > get_role_level('viewer')

    def test_hierarchy_consistency(self):
        """层级应该一致"""
        assert ROLE_HIERARCHY['admin'] > ROLE_HIERARCHY['editor']
        assert ROLE_HIERARCHY['editor'] > ROLE_HIERARCHY['viewer']


class TestPermissionCheck:
    """测试权限检查"""

    def test_admin_has_all_permissions(self):
        """admin 应该拥有所有权限"""
        admin_perms = get_role_permissions('admin')
        assert 'manage_users' in admin_perms
        assert 'manage_config' in admin_perms
        assert 'create' in admin_perms
        assert 'read' in admin_perms
        assert 'update' in admin_perms
        assert 'delete' in admin_perms

    def test_viewer_has_read_permission(self):
        """viewer 应该只有查看权限"""
        viewer_perms = get_role_permissions('viewer')
        assert 'read' in viewer_perms
        assert 'create' not in viewer_perms

    def test_has_permission_function(self):
        """has_permission 函数应该正确判断"""
        assert has_permission('admin', 'manage_users') is True
        assert has_permission('editor', 'create') is True
        assert has_permission('viewer', 'create') is False

    def test_is_admin_function(self):
        """is_admin 函数应该正确判断"""
        assert is_admin('admin') is True
        assert is_admin('editor') is False
        assert is_admin('viewer') is False

    def test_is_editor_or_above(self):
        """is_editor_or_above 应该包含 editor 和 admin"""
        assert is_editor_or_above('admin') is True
        assert is_editor_or_above('editor') is True
        assert is_editor_or_above('viewer') is False


class TestInvalidRole:
    """测试无效角色"""

    def test_invalid_role_returns_viewer_permissions(self):
        """无效角色应该返回 viewer 权限"""
        perms = get_role_permissions('invalid_role')
        assert perms == get_role_permissions('viewer')

    def test_invalid_role_returns_zero_level(self):
        """无效角色应该返回 0 层级"""
        assert get_role_level('invalid_role') == 0