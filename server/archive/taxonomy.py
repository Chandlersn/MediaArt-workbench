"""归档分类的单一权威定义（single source of truth）。

凡是需要知道「归档有哪些一级分类 / 每个分类下有哪些二级目录」的地方，
都应从这里读取，而不是各自硬编码：

    - server/archive/routes.py     归档目录初始化、分类接口
    - server/resources/routes.py   ARCHIVE_TOP_DIRS（归档路径前缀判定）
    - server/materials/routes.py   项目/机构/选手资料扫描定位
    - 前端 ArchiveView.vue         分类描述、二级目录提示

这样避免多处定义漂移导致「同一份文档有多个家」。
"""

import re
from typing import Dict, Any, List

# 一级分类（归档根目录下的文件夹）
ARCHIVE_TOP_DIRS = (
    '01_项目资料', '02_选手档案', '03_合作机构',
    '04_财务管理', '05_知识资源', '06_系统备份',
)

# 一级分类描述（供前端展示）
TOP_DIR_DESCRIPTIONS = {
    '01_项目资料': '策划文档、宣传物料、现场记录、项目成果',
    '02_选手档案': '个人信息、参赛记录、作品、获奖证书、照片',
    '03_合作机构': '合作协议、往来函件、结算单据、合作记录',
    '04_财务管理': '收入凭证、支出凭证、财务报表、税务',
    '05_知识资源': '赛事规则、培训教材、经验总结',
    '06_系统备份': '自动备份、手动备份',
}

# 二级目录（规范化清单）。项目/选手/机构 的二级是「实体目录」（项目名/姓名/机构名），
# 实体目录之下再放 SUBDIRS[分类]；其余分类直接在根下放 SUBDIRS[分类]。
ENTITY_LEVEL_DIRS = ('01_项目资料', '02_选手档案', '03_合作机构')

SUBDIRS = {
    '01_项目资料': ('01_策划文档', '02_宣传物料', '03_现场记录', '04_项目成果'),
    '02_选手档案': ('01_个人信息', '02_参赛记录', '03_作品', '04_获奖证书', '05_照片'),
    '03_合作机构': ('01_合作协议', '02_往来函件', '03_结算单据', '04_合作记录'),
    '04_财务管理': ('01_收入', '02_支出', '03_报表', '04_税务'),
    '05_知识资源': ('01_赛事规则', '02_培训教材', '03_经验总结'),
    '06_系统备份': ('01_自动', '02_手动'),
}


def strip_seq(name: str) -> str:
    """去掉目录名的序号前缀（01_策划文档 -> 策划文档）。"""
    return re.sub(r'^\d+_', '', name or '')


def canonical_subdir(top_dir: str, name: str) -> str:
    """把某分类下的二级目录名归一到规范名（去序号）。找不到则原样去序号返回。"""
    for sub in SUBDIRS.get(top_dir, ()):
        if sub == name or strip_seq(sub) == strip_seq(name):
            return sub
    return strip_seq(name)


def describe(top_dir: str) -> str:
    return TOP_DIR_DESCRIPTIONS.get(top_dir, '归档分类')


def as_dict() -> dict:
    """给前端的序列化结构。"""
    return {
        'topDirs': list(ARCHIVE_TOP_DIRS),
        'descriptions': dict(TOP_DIR_DESCRIPTIONS),
        'subdirs': {k: list(v) for k, v in SUBDIRS.items()},
        'entityLevelDirs': list(ENTITY_LEVEL_DIRS),
    }


# 前端「资料类型」（materialTypes 配置里的名称）→ 归档三级目录（规范名）。
# 项目/机构/选手详情页上传时只有「资料类型」，需要它才能落到规范目录。
MATERIAL_TYPE_TO_SUBDIR = {
    '01_项目资料': {
        '策划文档': '01_策划文档', '策划方案': '01_策划文档', '方案': '01_策划文档',
        '宣传物料': '02_宣传物料', '海报': '02_宣传物料', '宣传': '02_宣传物料',
        '现场记录': '03_现场记录', '现场照片': '03_现场记录', '现场视频': '03_现场记录',
        '照片': '03_现场记录', '视频': '03_现场记录',
        '项目成果': '04_项目成果', '获奖证书': '04_项目成果', '成果': '04_项目成果',
    },
    '02_选手档案': {
        '个人信息': '01_个人信息', '报名表': '01_个人信息',
        '参赛记录': '02_参赛记录', '参赛历程': '02_参赛记录', '参赛视频': '02_参赛记录',
        '作品': '03_作品', '作品集': '03_作品', '作品介绍': '03_作品', '音频文件': '03_作品',
        '获奖证书': '04_获奖证书',
        '照片': '05_照片', '个人照片': '05_照片',
    },
    '03_合作机构': {
        '合作协议': '01_合作协议', '合同': '01_合作协议', '协议': '01_合作协议',
        '往来函件': '02_往来函件', '函件': '02_往来函件',
        '结算单据': '03_结算单据', '结算': '03_结算单据',
        '合作记录': '04_合作记录', '记录': '04_合作记录',
    },
}

# 未命中映射时的兜底三级目录
DEFAULT_SUBDIR = {
    '01_项目资料': '01_策划文档',
    '02_选手档案': '01_个人信息',
    '03_合作机构': '01_合作协议',
}


# ========== 默认「资料类型」（初始状态用） ==========

# 实体 → 对应的一级归档分类
ENTITY_TOP_DIR = {
    'projects': '01_项目资料',
    'players': '02_选手档案',
    'organizations': '03_合作机构',
}

# 默认资料类型的图标（仅用于初始展示，用户可自行改）
_DEFAULT_TYPE_ICONS = {
    '策划文档': '📋', '宣传物料': '🎨', '现场记录': '📸', '项目成果': '🏆',
    '个人信息': '🪪', '参赛记录': '🎽', '作品': '🎭', '获奖证书': '🏅', '照片': '🖼️',
    '合作协议': '📄', '往来函件': '✉️', '结算单据': '🧾', '合作记录': '📝',
}


def default_material_types(entity: str) -> List[Dict[str, Any]]:
    """返回某实体（projects / players / organizations）的默认资料类型列表。

    结构对齐前端配置项：``{ id, name, icon }``。用途是「初始状态」——尚未做过
    资料类型配置时，配置页与详情页上传下拉即可直接选用，而不是一片空白。

    名称直接取自该分类的规范三级目录（去序号），因此**与 SUBDIRS 永远一致**：
    改三级目录即同步改默认资料类型。
    """
    top = ENTITY_TOP_DIR.get(entity)
    if not top:
        return []
    out: List[Dict[str, Any]] = []
    for idx, sub in enumerate(SUBDIRS.get(top, ()), 1):
        name = strip_seq(sub)
        out.append({
            'id': f'{entity}-mt-{idx}',
            'name': name,
            'icon': _DEFAULT_TYPE_ICONS.get(name, '📄'),
        })
    return out


def resolve_subdir_for_type(top_dir: str, material_type: str) -> str:
    """把「资料类型」解析成归档三级目录（规范名，含序号）。

    顺序：显式映射 → 类型名本身就是规范目录名（含去序号比对）→ 兜底目录。
    """
    subs = SUBDIRS.get(top_dir, ())
    if not subs:
        return ''
    mt = (material_type or '').strip()
    mapped = MATERIAL_TYPE_TO_SUBDIR.get(top_dir, {}).get(mt)
    if mapped and mapped in subs:
        return mapped
    for s in subs:
        if s == mt or strip_seq(s) == mt:
            return s
    return DEFAULT_SUBDIR.get(top_dir, subs[0])


def authoritative_material_types() -> Dict[str, Any]:
    """资料类型的单一权威来源（供后端解析与前端下拉共用）。

    返回每个一级分类下的：
      - types: 合法「资料类型」名称集合（同义别名 ∪ 规范子目录名去序号）
      - map:   资料类型 → 规范三级目录（含序号）的解析映射
      - default_subdir: 未命中时的兜底目录
    注意：资料类型「名称」只有这一处定义；`materialTypes` 用户配置应以此为基准。
    """
    out = {}
    for top in ARCHIVE_TOP_DIRS:
        mapping = MATERIAL_TYPE_TO_SUBDIR.get(top, {})
        type_names = set(mapping.keys()) | {strip_seq(s) for s in SUBDIRS.get(top, ())}
        out[top] = {
            'types': sorted(type_names),
            'map': mapping,
            'default_subdir': DEFAULT_SUBDIR.get(top),
        }
    return out
