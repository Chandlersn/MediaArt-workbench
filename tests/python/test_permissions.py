# -*- coding: utf-8 -*-
"""
权限模块测试

对应 server.utils.permissions 的「角色-权限矩阵」模型：

    role -> module -> [actions]

- MODULES：业务域（projects / organizations / players / finances /
           users / knowledge / resources / settings）
- ACTIONS：view（查看）/ edit（编辑·新增·修改）/ delete（删除）

注意：模型中没有独立的 create 动作，新增与修改统一归入 edit。
管理员 admin 恒拥有全部权限；未知模块或未知动作按「拒绝」处理（fail-safe）。
"""
import pytest
from server.utils.permissions import (
    MODULES,
    ACTIONS,
    ROLE_HIERARCHY,
    DEFAULT_ROLE_MATRIX,
    get_role_matrix,
    get_role_permissions,
    get_user_effective_permissions,
    has_permission,
    has_higher_role,
    is_admin,
    is_editor_or_above,
)


class TestRoleHierarchy:
    """测试角色层级"""

    def test_admin_has_highest_level(self):
        """admin 应该有最高层级"""
        assert ROLE_HIERARCHY['admin'] >= ROLE_HIERARCHY['editor']
        assert ROLE_HIERARCHY['admin'] >= ROLE_HIERARCHY['viewer']

    def test_editor_above_viewer(self):
        """editor 应该高于 viewer"""
        assert ROLE_HIERARCHY['editor'] > ROLE_HIERARCHY['viewer']

    def test_hierarchy_consistency(self):
        """层级应该一致"""
        assert ROLE_HIERARCHY['admin'] > ROLE_HIERARCHY['editor']
        assert ROLE_HIERARCHY['editor'] > ROLE_HIERARCHY['viewer']

    def test_unknown_role_level_is_zero(self):
        """未知角色等级视为 0（最低），不高于任何已知角色"""
        assert ROLE_HIERARCHY.get('invalid_role', 0) == 0
        assert has_higher_role('invalid_role', 'viewer') is False


class TestPermissionMatrix:
    """测试角色权限矩阵结构"""

    def test_matrix_covers_all_modules(self):
        """每个角色矩阵都应覆盖全部业务模块"""
        matrix = get_role_matrix()
        for role in DEFAULT_ROLE_MATRIX:
            assert set(matrix[role].keys()) == set(MODULES)

    def test_matrix_actions_are_valid(self):
        """矩阵中的动作必须属于 ACTIONS"""
        matrix = get_role_matrix()
        for _role, mods in matrix.items():
            for _mod, acts in mods.items():
                for act in acts:
                    assert act in ACTIONS

    def test_admin_full_actions(self):
        """admin 在所有模块拥有全部动作"""
        matrix = get_role_matrix()
        assert set(matrix['admin'].keys()) == set(MODULES)
        for mod in MODULES:
            assert set(matrix['admin'][mod]) == set(ACTIONS)

    def test_viewer_view_only(self):
        """viewer 在所有模块仅有查看权"""
        matrix = get_role_matrix()
        for mod in MODULES:
            assert matrix['viewer'][mod] == ['view']

    def test_editor_readonly_on_sensitive_modules(self):
        """editor 对用户管理与系统设置模块仅可查看"""
        matrix = get_role_matrix()
        assert matrix['editor']['users'] == ['view']
        assert matrix['editor']['settings'] == ['view']

    def test_get_role_permissions_is_flattened(self):
        """get_role_permissions 应返回 'module:action' 扁平列表"""
        perms = get_role_permissions('admin')
        assert 'users:delete' in perms
        assert 'projects:edit' in perms
        assert len(perms) == len(MODULES) * len(ACTIONS)

    def test_get_user_effective_permissions_shape(self):
        """get_user_effective_permissions 应返回 module -> actions 字典"""
        effective = get_user_effective_permissions('editor')
        assert set(effective.keys()) == set(MODULES)
        assert effective['projects'] == ['view', 'edit']

    def test_unknown_role_has_no_permissions(self):
        """未知角色不应获得任何权限（fail-safe）"""
        assert get_role_permissions('invalid_role') == []
        assert get_user_effective_permissions('invalid_role') == {m: [] for m in MODULES}


class TestPermissionCheck:
    """测试权限检查"""

    def test_admin_has_all_permissions(self):
        """admin 应该拥有所有模块的全部权限"""
        for mod in MODULES:
            for act in ACTIONS:
                assert has_permission('admin', mod, act) is True

    def test_viewer_has_view_only(self):
        """viewer 应该只能查看，不能编辑或删除"""
        assert has_permission('viewer', 'projects', 'view') is True
        assert has_permission('viewer', 'projects', 'edit') is False
        assert has_permission('viewer', 'projects', 'delete') is False

    def test_editor_can_edit_business_modules(self):
        """editor 应能编辑业务模块（edit 涵盖新增与修改），但不能删除"""
        assert has_permission('editor', 'projects', 'view') is True
        assert has_permission('editor', 'projects', 'edit') is True
        assert has_permission('editor', 'projects', 'delete') is False

    def test_editor_cannot_edit_users(self):
        """editor 不应能编辑用户模块"""
        assert has_permission('editor', 'users', 'view') is True
        assert has_permission('editor', 'users', 'edit') is False

    def test_has_permission_colon_form(self):
        """has_permission 支持 'module:action' 单字符串写法"""
        assert has_permission('admin', 'projects:delete') is True
        assert has_permission('viewer', 'projects:delete') is False

    def test_unknown_module_denied_for_non_admin(self):
        """未知模块对非管理员按 fail-safe 拒绝"""
        assert has_permission('editor', 'unknown_module', 'view') is False
        assert has_permission('viewer', 'unknown_module', 'view') is False

    def test_unknown_action_denied(self):
        """未知动作按 fail-safe 拒绝"""
        assert has_permission('editor', 'projects', 'unknown_action') is False

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
