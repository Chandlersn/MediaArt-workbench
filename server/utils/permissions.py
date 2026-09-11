"""
权限管理模块
定义角色权限配置和权限验证装饰器
"""
from functools import wraps
import json


# ========== 角色定义 ==========

# 角色权限等级（数字越大权限越高）
ROLE_HIERARCHY = {
    'admin': 100,    # 管理员：所有权限
    'editor': 50,    # 编辑者：创建、读取、更新
    'viewer': 10     # 查看者：只读
}

# 角色对应的权限列表
ROLE_PERMISSIONS = {
    'admin': ['create', 'read', 'update', 'delete', 'manage_users', 'manage_config'],
    'editor': ['create', 'read', 'update'],
    'viewer': ['read']
}

# 角色显示名称
ROLE_DISPLAY_NAMES = {
    'admin': '管理员',
    'editor': '编辑者',
    'viewer': '查看者'
}


# ========== 权限验证函数 ==========

def get_role_permissions(role):
    """
    获取指定角色的权限列表

    Args:
        role: 角色名称

    Returns:
        list: 权限列表
    """
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS['viewer'])


def has_permission(role, permission):
    """
    检查角色是否拥有指定权限

    Args:
        role: 角色名称
        permission: 权限名称

    Returns:
        bool: 是否拥有权限
    """
    permissions = get_role_permissions(role)
    return permission in permissions


def has_higher_role(user_role, required_role):
    """
    检查用户角色是否高于或等于要求角色

    Args:
        user_role: 用户角色
        required_role: 要求的角色

    Returns:
        bool: 是否满足角色要求
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def get_role_level(role):
    """
    获取角色的权限等级

    Args:
        role: 角色名称

    Returns:
        int: 权限等级
    """
    return ROLE_HIERARCHY.get(role, 0)


def is_admin(role):
    """
    检查是否为管理员

    Args:
        role: 角色名称

    Returns:
        bool: 是否为管理员
    """
    return role == 'admin'


def is_editor_or_above(role):
    """
    检查是否为编辑者或更高权限

    Args:
        role: 角色名称

    Returns:
        bool: 是否为编辑者或更高权限
    """
    return get_role_level(role) >= ROLE_HIERARCHY['editor']


# ========== 权限装饰器 ==========

def require_permission(permission):
    """
    权限验证装饰器

    用法:
        @require_permission('delete')
        def delete_item(self):
            # 只有 admin 角色可以执行
            pass

    Args:
        permission: 所需权限名称
    """
    def decorator(handler_method):
        @wraps(handler_method)
        def wrapper(self, *args, **kwargs):
            # 检查是否已通过认证（需要先使用 @require_auth 装饰器）
            user_payload = getattr(self, 'user_payload', None)

            if not user_payload:
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '未认证，请先登录',
                    'error': 'UNAUTHORIZED'
                }, ensure_ascii=False).encode())
                return

            # 获取用户角色
            user_role = user_payload.get('role', 'viewer')

            # 检查权限
            if not has_permission(user_role, permission):
                self.send_response(403)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': f'权限不足，需要 {permission} 权限',
                    'error': 'FORBIDDEN',
                    'required_permission': permission,
                    'user_role': user_role
                }, ensure_ascii=False).encode())
                return

            # 权限验证通过，调用原始方法
            return handler_method(self, *args, **kwargs)

        return wrapper
    return decorator


def require_role(required_role):
    """
    角色验证装饰器（验证用户角色等级）

    用法:
        @require_role('editor')
        def edit_item(self):
            # editor 或 admin 角色可以执行
            pass

    Args:
        required_role: 所需的最低角色等级
    """
    def decorator(handler_method):
        @wraps(handler_method)
        def wrapper(self, *args, **kwargs):
            # 检查是否已通过认证
            user_payload = getattr(self, 'user_payload', None)

            if not user_payload:
                self.send_response(401)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': '未认证，请先登录',
                    'error': 'UNAUTHORIZED'
                }, ensure_ascii=False).encode())
                return

            # 获取用户角色
            user_role = user_payload.get('role', 'viewer')

            # 检查角色等级
            if not has_higher_role(user_role, required_role):
                self.send_response(403)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'message': f'权限不足，需要 {ROLE_DISPLAY_NAMES.get(required_role, required_role)} 或更高权限',
                    'error': 'FORBIDDEN',
                    'required_role': required_role,
                    'user_role': user_role
                }, ensure_ascii=False).encode())
                return

            # 角色验证通过，调用原始方法
            return handler_method(self, *args, **kwargs)

        return wrapper
    return decorator


# ========== 权限检查辅助函数 ==========

def check_permission_for_action(action_type):
    """
    根据操作类型返回所需权限

    Args:
        action_type: 操作类型 ('create', 'read', 'update', 'delete')

    Returns:
        str: 所需权限名称
    """
    permission_map = {
        'create': 'create',
        'read': 'read',
        'update': 'update',
        'delete': 'delete',
        'manage_users': 'manage_users',
        'manage_config': 'manage_config'
    }
    return permission_map.get(action_type, 'read')


def get_user_permissions_from_payload(payload):
    """
    从 JWT payload 中获取用户的所有权限

    Args:
        payload: JWT payload

    Returns:
        list: 权限列表
    """
    if not payload:
        return []

    role = payload.get('role', 'viewer')
    return get_role_permissions(role)
