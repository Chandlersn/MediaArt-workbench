# Server utilities module
from .jwt_handler import JWTHandler, require_auth, get_current_user, create_token_response, jwt_handler
from .permissions import (
    has_permission,
    has_higher_role,
    get_role_permissions,
    get_user_effective_permissions,
    is_admin,
    is_editor_or_above,
    ROLE_HIERARCHY,
    ROLE_DISPLAY_NAMES,
    MODULES,
    ACTIONS,
    MODULE_LABELS,
    ACTION_LABELS,
    DEFAULT_ROLE_MATRIX,
    get_role_matrix,
    load_role_matrix,
    save_role_matrix,
)

__all__ = [
    # JWT 相关
    'JWTHandler',
    'require_auth',
    'get_current_user',
    'create_token_response',
    'jwt_handler',
    # 权限相关
    'has_permission',
    'has_higher_role',
    'get_role_permissions',
    'get_user_effective_permissions',
    'is_admin',
    'is_editor_or_above',
    'ROLE_HIERARCHY',
    'ROLE_DISPLAY_NAMES',
    'MODULES',
    'ACTIONS',
    'MODULE_LABELS',
    'ACTION_LABELS',
    'DEFAULT_ROLE_MATRIX',
    'get_role_matrix',
    'load_role_matrix',
    'save_role_matrix',
]
