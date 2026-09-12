"""
权限管理模块（统一角色-权限矩阵）

模型：role -> module -> [actions]
  - module：业务域（projects / organizations / players / finances / users /
           knowledge / resources / settings）
  - action：view(查看) / edit(编辑·新增·修改) / delete(删除)

矩阵持久化在 config/role_permissions.json，启动时加载；文件不存在则使用
DEFAULT_ROLE_MATRIX。管理员(admin)恒拥有全部权限，未知模块按"拒绝"处理(fail-safe)。
"""

import json
import logging
import os
import copy
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# ========== 模块 / 动作定义 ==========

# 业务模块（顺序即前端展示顺序）
MODULES: List[str] = [
    'projects',        # 项目
    'organizations',   # 机构
    'players',         # 选手（人员）
    'finances',        # 财务
    'users',           # 用户与权限
    'knowledge',       # 知识库
    'resources',       # 资源 / 归档
    'settings',        # 系统设置
]

# 可执行动作
ACTIONS: List[str] = ['view', 'edit', 'delete']

# 模块中文名（前端展示）
MODULE_LABELS: Dict[str, str] = {
    'projects': '项目',
    'organizations': '机构',
    'players': '选手',
    'finances': '财务',
    'users': '用户与权限',
    'knowledge': '知识库',
    'resources': '资源与归档',
    'settings': '系统设置',
}

# 动作中文名（前端展示）
ACTION_LABELS: Dict[str, str] = {
    'view': '查看',
    'edit': '编辑',
    'delete': '删除',
}

# 角色显示名
ROLE_DISPLAY_NAMES: Dict[str, str] = {
    'admin': '管理员',
    'editor': '编辑者',
    'viewer': '查看者',
}

# 角色权限等级（数值越大权限越高），用于层级判断
ROLE_HIERARCHY: Dict[str, int] = {
    'admin': 100,
    'editor': 50,
    'viewer': 10,
}


# ========== 默认角色矩阵 ==========

def _full() -> List[str]:
    return list(ACTIONS)


def _view_edit() -> List[str]:
    return ['view', 'edit']


def _view_only() -> List[str]:
    return ['view']


DEFAULT_ROLE_MATRIX: Dict[str, Dict[str, List[str]]] = {
    'admin': {m: _full() for m in MODULES},
    'editor': {
        'projects': _view_edit(),
        'organizations': _view_edit(),
        'players': _view_edit(),
        'finances': _view_edit(),
        'knowledge': _view_edit(),
        'resources': _view_edit(),
        'users': _view_only(),
        'settings': _view_only(),
    },
    'viewer': {m: _view_only() for m in MODULES},
}


# ========== 持久化 ==========

def _config_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'config', 'role_permissions.json')


def _validate_matrix(matrix: Any) -> bool:
    """校验外部传入的矩阵结构是否合法。"""
    if not isinstance(matrix, dict):
        return False
    for role, mods in matrix.items():
        if role not in DEFAULT_ROLE_MATRIX:
            return False
        if not isinstance(mods, dict):
            return False
        for mod, acts in mods.items():
            if mod not in MODULES:
                return False
            if not isinstance(acts, list):
                return False
            for a in acts:
                if a not in ACTIONS:
                    return False
    return True


def load_role_matrix() -> Dict[str, Dict[str, List[str]]]:
    """加载角色矩阵；文件缺失或解析失败则回退默认矩阵。"""
    path = _config_path()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if _validate_matrix(data):
                return data
            logger.warning('角色权限矩阵格式非法，回退默认配置')
    except Exception as e:
        logger.warning(f'加载角色权限矩阵失败: {e}，回退默认配置')
    return _default_copy()


def save_role_matrix(matrix: Dict[str, Dict[str, List[str]]]) -> bool:
    """保存角色矩阵到配置文件。"""
    if not _validate_matrix(matrix):
        return False
    path = _config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(matrix, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f'保存角色权限矩阵失败: {e}')
        return False


def _default_copy() -> Dict[str, Dict[str, List[str]]]:
    return copy.deepcopy(DEFAULT_ROLE_MATRIX)


# 模块级缓存，避免每次请求重复读盘
_ROLE_MATRIX_CACHE: Dict[str, Dict[str, List[str]]] = load_role_matrix()


def get_role_matrix() -> Dict[str, Dict[str, List[str]]]:
    """返回当前生效的矩阵（深拷贝，防止外部篡改缓存）。"""
    return copy.deepcopy(_ROLE_MATRIX_CACHE)


def reload_role_matrix() -> None:
    """重新从磁盘加载矩阵（保存后调用以刷新缓存）。"""
    global _ROLE_MATRIX_CACHE
    _ROLE_MATRIX_CACHE = load_role_matrix()


# ========== 权限判断 ==========

def has_permission(role: str, module: str, action: str = None) -> bool:
    """判断角色是否拥有某模块的某动作权限。

    签名兼容两种写法：
      - has_permission(role, module, action)
      - has_permission(role, 'module:action')   # 单字符串形式
    admin 恒为 True；未知模块 / 缺失动作返回 False（fail-safe）。
    """
    if action is None and isinstance(module, str) and ':' in module:
        module, action = module.split(':', 1)

    if role == 'admin':
        return True
    if module not in MODULES or action not in ACTIONS:
        return False
    perms = _ROLE_MATRIX_CACHE.get(role, {})
    return action in perms.get(module, [])


def get_role_permissions(role: str) -> List[str]:
    """返回角色的全部权限，扁平化为 'module:action' 列表（兼容旧调用）。"""
    perms = _ROLE_MATRIX_CACHE.get(role, {})
    out = []
    for mod, acts in perms.items():
        for a in acts:
            out.append(f'{mod}:{a}')
    return out


def get_user_effective_permissions(role: str) -> Dict[str, List[str]]:
    """返回某角色在各模块上的可用动作（前端用于 UI 门控）。"""
    return _ROLE_MATRIX_CACHE.get(role, {m: [] for m in MODULES})


def has_higher_role(user_role: str, required_role: str) -> bool:
    """判断用户角色等级是否不低于要求角色。"""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


def is_admin(role: str) -> bool:
    return role == 'admin'


def is_editor_or_above(role: str) -> bool:
    return has_higher_role(role, 'editor')
