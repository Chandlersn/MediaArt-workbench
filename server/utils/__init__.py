# Server utilities module
from .jwt_handler import JWTHandler, require_auth, get_current_user, create_token_response, jwt_handler
from .permissions import (
    require_permission,
    require_role,
    has_permission,
    has_higher_role,
    get_role_permissions,
    get_role_level,
    is_admin,
    is_editor_or_above,
    get_user_permissions_from_payload,
    check_permission_for_action,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    ROLE_DISPLAY_NAMES
)

__all__ = [
    # JWT 相关
    'JWTHandler',
    'require_auth',
    'get_current_user',
    'create_token_response',
    'jwt_handler',
    # 权限相关
    'require_permission',
    'require_role',
    'has_permission',
    'has_higher_role',
    'get_role_permissions',
    'get_role_level',
    'is_admin',
    'is_editor_or_above',
    'get_user_permissions_from_payload',
    'check_permission_for_action',
    'ROLE_HIERARCHY',
    'ROLE_PERMISSIONS',
    'ROLE_DISPLAY_NAMES'
]
