# -*- coding: utf-8 -*-
"""打印体系路由（底图 + 勾选字段 → 批量生成 HTML → 打印 / 归档 / 留痕）。

设计要点（与 docs/方案-打印体系.md v9 一致）：

- **底图承载版式**：用户在专业软件里设计好证书，导出成图片上传；工作台不排版。
- **字段承载变化**：字段集合来自数据库表的列，用户**勾选**后拖到图上定位。
- **坐标存百分比**：底图换分辨率不会错位（重导底图不用重新定位）。
- **生成用 HTML**：纯字符串替换 + 循环复制块，绕开 docx 的 run 分割坑，零新增依赖。
- **不越权**：系统只提供能力（有哪些列、定位、生成、打印），勾哪些字段、怎么排布由用户决定。

接口：
    GET    /api/print/fields          字段目录（来自数据库表列 + 中文标签）
    POST   /api/print/background      上传底图 → 返回像素尺寸 + 建议纸张
    POST   /api/print/validate        本次证书与模板的只读打印检查
    POST   /api/print/preview         检查后的单份排版预览（不归档）
    POST   /api/print/generate        批量生成可打印 HTML（含 N 页）
    POST   /api/print/archive         归档生成的 HTML + 写留痕
    GET    /api/print/logs            打印记录
    GET    /api/print/doc/<log_id>    取回归档文档
    POST   /api/print/open            （可选）一键打开设计稿源文件
"""

import os
import json
import uuid
import struct
import shutil
import logging
import platform
import subprocess
import datetime
from typing import Any, Dict, List, Optional, Tuple

from server.config import BASE_DIR
from server.database.store import data_store
from server.resources.routes import (
    _ok, _qp, _json_body, _auth, _perm, _parse_multipart, _sanitize_filename,
    get_archives_dir,
)
from server.archive.taxonomy import PRINT_ARCHIVE_DIR
from server.print.preflight import DEFAULT_FONT_PT, inspect_batch, empty_warnings, number as layout_number

logger = logging.getLogger(__name__)
MAX_PRINT_RECORDS = 10000


class PrintRequestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

# 底图存放目录。放在 data/ 下而不是 resources/：resources/ 是素材库（资源中心）
# 的领域，打印资产混进去会被素材扫描当成杂乱文件；data/ 是运行时用户数据目录
# （不入素材扫描、随 .gitignore 不入库），且同在静态业务前缀内可直接免鉴权引用。
BG_REL_DIR = 'data/print-bg'

# 上传字体存放目录（同上；静态路由免鉴权，生成页与画布预览都能直接引用）。
# 字体 family 名 = 去扩展名的文件名，@font-face 与字段 fontFamily 用同一名字对齐。
FONT_REL_DIR = 'data/print-fonts'
FONT_EXTS = ('ttf', 'otf', 'woff', 'woff2')
_FONT_FORMAT = {'ttf': 'truetype', 'otf': 'opentype', 'woff': 'woff', 'woff2': 'woff2'}

# 常用中文字体候选（Windows 自带为主）：启动时检测系统字体目录，
# 只把实际存在的暴露到界面——候选可维护，暴露结果来自运行环境而非写死。
_FONT_CANDIDATES = [
    # (显示名, CSS font-family, 字体目录中的文件名)
    ('宋体', 'SimSun', ('simsun.ttc',)),
    ('黑体', 'SimHei', ('simhei.ttf',)),
    ('微软雅黑', 'Microsoft YaHei', ('msyh.ttc', 'msyh.ttf')),
    ('楷体', 'KaiTi', ('simkai.ttf',)),
    ('仿宋', 'FangSong', ('simfang.ttf',)),
    ('等线', 'DengXian', ('Deng.ttf',)),
    ('隶书', 'LiSu', ('SIMLI.TTF',)),
    ('幼圆', 'YouYuan', ('SIMYOU.TTF',)),
    ('华文行楷', 'STXingkai', ('STXINGKA.TTF',)),
    ('华文楷体', 'STKaiti', ('STKAITI.TTF',)),
    ('华文仿宋', 'STFangsong', ('STFANGSO.TTF',)),
    ('华文中宋', 'STZhongsong', ('STZHONGS.TTF',)),
    ('华文琥珀', 'STHupo', ('STHUPO.TTF',)),
    ('方正舒体', 'FZShuTi', ('FZSTK.TTF',)),
    ('方正姚体', 'FZYaoTi', ('FZYTK.TTF',)),
]


def _detect_system_fonts() -> List[Dict[str, str]]:
    """检测系统实际安装的候选字体。

    Windows 以注册表字体表为权威来源（覆盖装在任意目录的字体，
    含 Office 附带的华文系列、用户级安装），目录扫描作非 Windows 兜底。
    """
    found: List[Dict[str, str]] = []
    seen = set()

    reg_names: set = set()
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                        hive, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as k:
                    i = 0
                    while True:
                        try:
                            name, _, _ = winreg.EnumValue(k, i)
                            i += 1
                            reg_names.add(str(name).lower())
                        except OSError:
                            break
            except OSError:
                continue
    except ImportError:
        pass

    dir_names: set = set()
    windir = os.environ.get('WINDIR') or r'C:\Windows'
    for d in (os.path.join(windir, 'Fonts'),
              os.path.expanduser(r'~\AppData\Local\Microsoft\Windows\Fonts')):
        if os.path.isdir(d):
            try:
                dir_names.update(n.lower() for n in os.listdir(d))
            except OSError:
                pass

    for label, family, files in _FONT_CANDIDATES:
        keys = {label.lower(), family.lower()} | {f.lower() for f in files}
        hit = any(any(k in n for k in keys) for n in reg_names) \
            or any(k in dir_names for k in keys)
        if hit and family not in seen:
            seen.add(family)
            found.append({'label': label, 'value': family})
    return found


SYSTEM_FONTS = _detect_system_fonts()

# 打印件归档目录：跟随 config.json 的 archivePath 配置 + taxonomy 单一定义源，
# 不再写死 'MediaArt_Archives/07_打印归档'（配置漂移/改名会导致归档落错地方）。
ARCHIVES_DIR = get_archives_dir()
ARCHIVE_ROOT = PRINT_ARCHIVE_DIR
ARCHIVE_TYPE_DIR = {
    'certificate': '证书',
    'roster': '名单',
    'report': '报表',
}

# 纸张规格：物理尺寸（mm），用于按底图比例自动建议
PAGE_SIZES = {
    'A4_L': {'label': 'A4 横向', 'width_mm': 297, 'height_mm': 210},
    'A4_P': {'label': 'A4 纵向', 'width_mm': 210, 'height_mm': 297},
    'A3_L': {'label': 'A3 横向', 'width_mm': 420, 'height_mm': 297},
    'A3_P': {'label': 'A3 纵向', 'width_mm': 297, 'height_mm': 420},
}

# 证书字段的中文标签（DB 列名 → 显示名；仅影响界面展示，取值仍按列名）。
# 这是唯一的字段命名元数据源：字段目录的 label 一律由此查表（按 DB 列名），
# 缺失时回退为列名本身；新增列只需在 schema 与此处各加一行，其余全部自动派生。
CERT_FIELD_LABELS = {
    'cert_number': '证书编号',
    'player_name': '选手姓名',
    'org_name': '选送机构',
    'receiving_org': '收件机构',
    'group_name': '组别',
    'award': '奖项',
    'cert_round': '赛段',
    'work_name': '作品名称',
    'instructor': '指导老师',
    'language': '语种',
    'promotion': '晋级情况',
    'player_id': '选手 ID',
    'org_id': '机构 ID',
    'project_id': '项目 ID',
}

# 证书表中不适合直接打印的内部字段（DB 列名；与 schema.sql 的内部列保持一致）
CERT_FIELD_SKIP = {
    'session_id', 'import_id', 'source_sheet', 'missing_work_name',
    'is_withdrawn', 'packed', 'created_at', 'updated_at',
}

# 证书记录（get_all() 的驼峰键）中不适合直接打印的内部字段
# 已知内部字段显式黑名单（第一层，语义明确的最快路径；
# 更通用的命名 / 值形态规则见 _printable_key，两层叠加）
CERT_INTERNAL_KEYS = {
    'sessionId', 'importId', 'sourceSheet', 'missingWorkName',
    'isWithdrawn', 'packed', 'createdAt', 'updatedAt',
}


def _key_stats(records: List[Dict[str, Any]], key: str) -> tuple:
    """统计某记录键的填充情况 → (填充数, 总数, 非空值列表)。"""
    vals = [r.get(key) for r in records]
    nonempty = [str(v).strip() for v in vals if v is not None and str(v).strip() != '']
    return len(nonempty), len(vals), nonempty


def _printable_key(key: str, primary_rec_key: str,
                   filled: int, nonempty: List[str]) -> bool:
    """通用可打印性判定（分层规则，任何文档类型 / 表都成立）。

    - 显式黑名单：CERT_INTERNAL_KEYS（已知内部字段，语义优先）；
    - 命名语义：`At` / `_at` 结尾 = 时间戳；`Id` 结尾 = 系统引用
      （主键豁免，如 certNumber 证书编号要打印）；
    - 值形态：全表非空值都是 0/1/true/false = 布尔状态标记，打印无意义
      （只认纯布尔字面量，不认「是/否」——避免误杀晋级情况这类业务字段）；
    - 值长度：平均长度超 60 字符 = 段落长文本，不适合做证书字段。
    """
    if key in CERT_INTERNAL_KEYS:
        return False
    if key.endswith('At') or key.endswith('_at'):
        return False
    if key.endswith('Id') and key != primary_rec_key:
        return False
    if filled and all(v in ('0', '1', 'true', 'false', 'True', 'False') for v in nonempty):
        return False
    if nonempty and sum(len(v) for v in nonempty) / len(nonempty) > 60:
        return False
    return True


# ---------- 通用小工具 ----------

def _abs(rel_path: str) -> str:
    """仓库根相对路径 → 绝对路径。"""
    return os.path.join(BASE_DIR, str(rel_path).replace('\\', '/').lstrip('/'))


def _record_key(db_column: str) -> str:
    """DB 列名 → 记录键名。

    数据层 `Model.get_all()` 返回的记录键是经 `_convert_from_db`（下划线 → 驼峰）
    转换过的。这里**复用同一个算法**派生键名，而不是在打印模块再写一份命名约定
    —— 此前两处各自硬编码（PRAGMA 给下划线、记录是驼峰），模板里存的列名
    去 `rec.get(col)` 恒取空，打印页全部字段空白。
    """
    return data_store.certificates._from_db_field(db_column)


def _record_value(rec: Dict[str, Any], column: str) -> Any:
    """按模板字段里的 column 名从证书记录取值。

    兼容两种存量格式：字段目录输出的记录键（驼峰）与历史模板保存的
    DB 列名（下划线），无论模板何时保存都能取到值。
    """
    if column in rec:
        return rec.get(column)
    return rec.get(_record_key(column))


def _resolve_snapshot(rel_path: str) -> str:
    """把留痕里的 snapshot_path 解析成绝对路径。

    兼容两种存量格式：归档根相对路径（新，跟随 archivePath 配置）与
    仓库根相对路径（旧，'MediaArt_Archives/...' 开头）。
    """
    candidate = os.path.join(ARCHIVES_DIR, rel_path)
    if os.path.isfile(candidate):
        return candidate
    return _abs(rel_path)


def _client_ip(request_context: Dict[str, Any]) -> str:
    addr = request_context.get('client_address')
    if isinstance(addr, (tuple, list)) and addr:
        return str(addr[0])
    return ''


def _username(request_context: Dict[str, Any]) -> str:
    user = request_context.get('user', {}) or {}
    return user.get('username') or ''


# ---------- 读图片像素尺寸（纯标准库，已实测） ----------

def image_size(path: str) -> Optional[Tuple[int, int]]:
    """读取 PNG / JPEG 的像素尺寸。纯标准库实现，不依赖 Pillow。

    PNG：8 字节签名 + IHDR，宽高是 big-endian uint32。
    JPEG：扫描段找 SOF0–SOF15（排除 DHT=C4 / JPG=C8 / DAC=CC）。
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
            if head[:8] == b'\x89PNG\r\n\x1a\n':
                w, h = struct.unpack('>II', head[16:24])
                return int(w), int(h)
            if head[:2] == b'\xff\xd8':
                return _jpeg_size(f)
    except Exception as e:
        logger.warning(f"读取图片尺寸失败 {path}: {e}")
    return None


def _jpeg_size(f) -> Optional[Tuple[int, int]]:
    f.seek(2)
    while True:
        b = f.read(1)
        if not b:
            return None
        if b != b'\xff':
            continue
        marker = f.read(1)
        while marker == b'\xff':
            marker = f.read(1)
        if not marker:
            return None
        m = marker[0]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            continue
        seg = f.read(2)
        if len(seg) < 2:
            return None
        length = struct.unpack('>H', seg)[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            data = f.read(5)
            if len(data) < 5:
                return None
            h, w = struct.unpack('>HH', data[1:5])
            return int(w), int(h)
        f.seek(max(length - 2, 0), 1)


def _migrate_print_assets() -> None:
    """一次性迁移：打印底图 / 字体从 resources/（素材库领域）挪到 data/ 独立目录。

    幂等：旧目录不存在时什么都不做。挪完顺手改写模板里存的底图路径，
    保证已有模板的底图不断链（字体文件按名引用，目录挪移不影响）。
    """
    migrated = False
    for old_rel, new_rel in (('resources/print-bg', BG_REL_DIR),
                             ('resources/print-fonts', FONT_REL_DIR)):
        old_dir, new_dir = _abs(old_rel), _abs(new_rel)
        if not os.path.isdir(old_dir):
            continue
        os.makedirs(new_dir, exist_ok=True)
        for fn in os.listdir(old_dir):
            src, dst = os.path.join(old_dir, fn), os.path.join(new_dir, fn)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.move(src, dst)
                migrated = True
        try:
            os.rmdir(old_dir)  # 空了才删得掉，删不掉说明有并存文件，留着不碍事
        except OSError:
            pass
    if not migrated:
        return
    try:
        rows = data_store.db.fetchall(
            "SELECT id, background FROM print_templates WHERE background LIKE 'resources/print-bg/%'")
        for r in rows:
            new_bg = BG_REL_DIR + str(r.get('background') or '')[len('resources/print-bg'):]
            with data_store.db.transaction() as conn:
                conn.execute('UPDATE print_templates SET background = ? WHERE id = ?',
                             (new_bg, r.get('id')))
        if rows:
            logger.info(f"打印资产已迁移至 data/，改写 {len(rows)} 个模板的底图路径")
    except Exception as e:
        logger.warning(f"改写模板底图路径失败（可忽略）: {e}")


_migrate_print_assets()  # 模块导入即执行，幂等


def list_uploaded_fonts() -> List[Dict[str, str]]:
    """扫描字体目录 → [{name, file, url}]（name 即 @font-face 的 family 名）。"""
    d = _abs(FONT_REL_DIR)
    out: List[Dict[str, str]] = []
    try:
        for fn in sorted(os.listdir(d)):
            ext = os.path.splitext(fn)[1].lower().lstrip('.')
            if ext in FONT_EXTS:
                out.append({
                    'name': os.path.splitext(fn)[0],
                    'file': fn,
                    'url': f'/{FONT_REL_DIR}/{fn}',
                })
    except OSError:
        pass
    return out


def _font_face_css() -> str:
    """为所有已上传字体生成 @font-face 声明。

    生成页与编辑器画布共用同一 family 名（去扩展名的文件名），
    因此字段里存的 fontFamily 在两边渲染一致。
    """
    rules = []
    for f in list_uploaded_fonts():
        ext = f['file'].rsplit('.', 1)[-1].lower()
        fmt = _FONT_FORMAT.get(ext)
        if not fmt:
            continue
        rules.append(
            f"@font-face {{ font-family:'{f['name']}'; "
            f"src:url('{f['url']}') format('{fmt}'); }}")
    return '\n'.join(rules)


def suggest_page_size(width: int, height: int) -> Dict[str, Any]:
    """按底图宽高比判断**方向**，尺寸默认 A4（最常用）。

    ⚠️ **不能靠比例猜纸张尺寸**：A4 与 A3 的宽高比都是 √2
    （A4 横 297/210 = 1.4143；A3 横 420/297 = 1.4141，差 0.0002），
    比例上**无法区分**。所以这里只判断横竖，尺寸交给用户确认。

    同时计算与建议纸张的比例偏差，偏差过大时前端应提示"会变形"。
    """
    if not width or not height:
        return {'key': 'A4_L', 'label': PAGE_SIZES['A4_L']['label'],
                'landscape': True, 'ratioDiff': 0.0, 'ratioMismatch': False}

    landscape = width >= height
    key = 'A4_L' if landscape else 'A4_P'
    spec = PAGE_SIZES[key]
    target_ratio = spec['width_mm'] / spec['height_mm']
    ratio = width / height
    diff = abs(ratio - target_ratio) / target_ratio

    return {
        'key': key,
        'label': spec['label'],
        'landscape': landscape,
        'ratio': round(ratio, 4),
        'ratioDiff': round(diff, 4),
        # 偏差超过 2% 视为"比例不符"，直接铺满会拉伸变形
        'ratioMismatch': diff > 0.02,
        'note': '按底图比例判断方向；A4 与 A3 比例相同，尺寸请自行确认（默认 A4）',
    }


# ---------- 字段目录（来自数据库表列） ----------

def cert_field_catalog() -> List[Dict[str, Any]]:
    """从证书管理的实际数据派生可用字段清单（数据驱动 + 通用过滤）。

    - 字段集合：遍历 `certificates.get_all()` 真实记录键的并集——台账里
      实际有什么字段，打印模板就能勾选什么，与证书管理页面同源；
    - 过滤：`_printable_key` 分层通用规则（显式黑名单 → 命名语义 →
      值形态 → 值长度），不依赖每张表手工维护排除清单；
    - fill：填充率（如 '2/3'）随清单返回，前端据此标注空缺字段；
    - 空库时回退 PRAGMA 表结构派生（没有数据也能先建模板）；
    - label：按 DB 列名查 CERT_FIELD_LABELS，缺失回退键名。
    """
    try:
        records = data_store.certificates.get_all()
    except Exception as e:
        logger.warning(f"读取证书记录失败: {e}")
        records = []

    # 主键的记录键（如 cert_number → certNumber），在 Id 规则中豁免
    primary_rec_key = data_store.certificates._from_db_field(
        data_store.certificates.primary_key)

    keys: List[str] = []
    seen = set()
    stats: Dict[str, tuple] = {}
    for rec in records:
        for k in rec.keys():
            if k in seen:
                continue
            seen.add(k)
            filled, total, nonempty = _key_stats(records, k)
            if _printable_key(k, primary_rec_key, filled, nonempty):
                keys.append(k)
                stats[k] = (filled, total)

    if not keys:
        try:
            cols = data_store.db.fetchall("PRAGMA table_info(certificates)")
        except Exception as e:
            logger.warning(f"读取 certificates 表结构失败: {e}")
            return []
        for c in cols:
            name = (c.get('name') or '')
            if name and name not in CERT_FIELD_SKIP:
                k = _record_key(name)
                if _printable_key(k, primary_rec_key, 0, []):
                    keys.append(k)

    out: List[Dict[str, Any]] = []
    for k in keys:
        db_col = data_store.certificates._to_db_field(k)
        filled, total = stats.get(k, (0, 0))
        out.append({
            'column': k,
            'dbColumn': db_col,
            'label': CERT_FIELD_LABELS.get(db_col, k),
            'type': 'TEXT',
            'fill': f'{filled}/{total}' if records else '',
        })
    return out


def _find_template(template_id: str) -> Optional[Dict[str, Any]]:
    rows = data_store._load_print_templates()
    return next((r for r in rows if r.get('id') == template_id), None)


# ---------- HTML 生成 ----------

def _escape(text: Any) -> str:
    s = '' if text is None else str(text)
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


def _field_style(f: Dict[str, Any]) -> str:
    """字段定位样式。

    百分比坐标；居中 / 右对齐用 translate 修正，因此**不需要指定宽度**也能居中准确。
    """
    x = f.get('x', 0)
    y = f.get('y', 0)
    align = f.get('align') or 'center'
    parts = [f'left:{x}%;', f'top:{y}%;']
    if align == 'center':
        parts.append('transform:translateX(-50%);')
    elif align == 'right':
        parts.append('transform:translateX(-100%);')
    parts.append(f"font-size:{f.get('fontSize', DEFAULT_FONT_PT)}pt;")
    if f.get('bold'):
        parts.append('font-weight:bold;')
    if f.get('color'):
        parts.append(f"color:{f['color']};")
    if f.get('fontFamily'):
        # family 名里的引号直接剥掉（上传字体名来自文件名，不该带引号）
        fam = str(f['fontFamily']).replace("'", '').replace('"', '')
        parts.append(f"font-family:'{fam}';")
    parts.append(f'text-align:{align};')
    return ''.join(parts)


def build_html(template: Dict[str, Any], records: List[Dict[str, Any]], preview: bool = False) -> str:
    """底图 + 字段叠加 → 一份含 N 页的可打印 HTML。"""
    spec = PAGE_SIZES.get(template.get('pageSize') or 'A4_L', PAGE_SIZES['A4_L'])
    width_mm, height_mm = spec['width_mm'], spec['height_mm']
    bg = (template.get('background') or '').replace('\\', '/').lstrip('/')
    fields = template.get('fields') or []

    pages: List[str] = []
    for rec in records:
        inner: List[str] = []
        for f in fields:
            col = f.get('column') or ''
            if not col:
                continue
            inner.append(
                f'<div class="pf" style="{_field_style(f)}">'
                f'{_escape(_record_value(rec, col))}</div>')
        pages.append(f'<div class="page">{"".join(inner)}</div>')

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f'<title>{_escape(template.get("name") or "打印预览")}</title>\n<style>\n'
        # 已上传字体统一在此声明，字段 font-family 按名引用即可
        + (_font_face_css() + '\n' if _font_face_css() else '')
        + f'@page {{ size: {width_mm}mm {height_mm}mm; margin: 0; }}\n'
        '* { box-sizing: border-box; }\n'
        'body { margin: 0; background: #f0f0f0; }\n'
        '.page { position: relative; '
        f'width: {width_mm}mm; height: {height_mm}mm; '
        f"background-image: url('/{bg}'); background-size: 100% 100%; "
        'background-repeat: no-repeat; page-break-after: always; overflow: hidden; }\n'
        '.page:last-child { page-break-after: auto; }\n'
        '.pf { position: absolute; white-space: nowrap; }\n'
        '@media print { body { background: #fff; } .no-print { display: none !important; } }\n'
        '</style>\n</head>\n<body>\n'
        + ('' if preview else '<div class="no-print" style="padding:12px;font:13px/1.6 system-ui;'
        'background:#fff8e1;color:#8a6d00;border-bottom:1px solid #ffe082;">'
        '<button onclick="window.print()" style="margin-right:12px;padding:4px 14px;'
        'cursor:pointer;border:1px solid #8a6d00;border-radius:6px;background:#fff;'
        'color:#8a6d00;">打印</button>'
        '请在打印对话框中选择「缩放 = 100%」（或「实际大小」），'
        '并关闭页眉页脚，否则位置会偏移。'
        '</div>\n')
        + ''.join(pages)
        + '\n</body>\n</html>'
    )


def _open_with_os(abs_path: str) -> None:
    """用系统默认程序打开文件。"""
    if platform.system() == 'Windows':
        os.startfile(abs_path)  # noqa: S606 仅 Windows 存在
    elif platform.system() == 'Darwin':
        subprocess.Popen(['open', abs_path])
    else:
        subprocess.Popen(['xdg-open', abs_path])


# ---------- 路由 ----------

class PrintRouter:
    """Router for print template generation / archive / logs."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            if norm == '/api/print/fields' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.fields()

            if norm == '/api/print/fonts' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.fonts()

            if norm == '/api/print/font' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.upload_font(request_context)

            if norm == '/api/print/font/delete' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.delete_font(request_context)

            if norm == '/api/print/background' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'settings', 'edit')):
                    return p
                return self.upload_background(request_context)

            if norm == '/api/print/generate' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'projects', 'view')):
                    return p
                return self.generate(request_context)

            if norm == '/api/print/validate' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'projects', 'view')):
                    return p
                return self.validate(request_context)

            if norm == '/api/print/preview' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'projects', 'view')):
                    return p
                return self.preview(request_context)

            if norm == '/api/print/archive' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                if (p := _perm(request_context, 'projects', 'view')):
                    return p
                return self.archive(request_context)

            if norm == '/api/print/logs' and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.logs(request_context)

            if norm.startswith('/api/print/doc/') and method == 'GET':
                if (a := _auth(request_context)):
                    return a
                return self.get_doc(norm[len('/api/print/doc/'):])

            if norm == '/api/print/open' and method == 'POST':
                if (a := _auth(request_context)):
                    return a
                return self.open_source(request_context)

            return _ok({'success': False,
                        'message': f'未处理的打印接口: {method} {norm}'}, 404)

        except PrintRequestError as e:
            return _ok({'success': False, 'message': str(e)}, e.status)
        except Exception as e:
            logger.error(f"处理打印请求失败 {method} {norm}: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'服务器内部错误: {e}'}, 500)

    # ---------- 字段目录 ----------

    def fields(self) -> Dict[str, Any]:
        return _ok({'success': True, 'docType': 'certificate',
                    'fields': cert_field_catalog(),
                    'pageSizes': PAGE_SIZES})

    # ---------- 字体 ----------

    def fonts(self) -> Dict[str, Any]:
        return _ok({'success': True,
                    'system': SYSTEM_FONTS,
                    'uploaded': list_uploaded_fonts()})

    def upload_font(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        headers = request_context.get('headers', {}) or {}
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if 'multipart/form-data' not in (content_type or ''):
            return _ok({'success': False,
                        'message': 'Content-Type 必须是 multipart/form-data'}, 400)

        body = request_context.get('body', b'') or b''
        _fields, raw_name, file_data = _parse_multipart(body, content_type)
        if not file_data or not raw_name:
            return _ok({'success': False, 'message': '未收到文件'}, 400)

        ext = os.path.splitext(raw_name)[1].lower().lstrip('.')
        if ext not in FONT_EXTS:
            return _ok({'success': False,
                        'message': '字体仅支持 TTF / OTF / WOFF / WOFF2'}, 400)

        safe = _sanitize_filename(raw_name)
        if not safe or os.path.splitext(safe)[1].lower().lstrip('.') not in FONT_EXTS:
            return _ok({'success': False, 'message': '文件名无效'}, 400)
        try:
            os.makedirs(_abs(FONT_REL_DIR), exist_ok=True)
            with open(_abs(f'{FONT_REL_DIR}/{safe}'), 'wb') as f:
                f.write(file_data)
        except Exception as e:
            logger.error(f"保存字体失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'保存字体失败: {e}'}, 500)

        name = os.path.splitext(safe)[0]
        return _ok({
            'success': True,
            'message': '字体已上传',
            'font': {'name': name, 'file': safe,
                     'url': f'/{FONT_REL_DIR}/{safe}'},
        })

    def delete_font(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        payload = _json_body(request_context)
        name = (payload.get('name') or '').strip() if isinstance(payload, dict) else ''
        if not name:
            return _ok({'success': False, 'message': '缺少字体名'}, 400)
        font = next((f for f in list_uploaded_fonts() if f['name'] == name), None)
        if not font:
            return _ok({'success': False, 'message': '字体不存在'}, 404)
        try:
            os.remove(_abs(f"{FONT_REL_DIR}/{font['file']}"))
        except Exception as e:
            logger.error(f"删除字体失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'删除失败: {e}'}, 500)
        return _ok({'success': True, 'message': '字体已删除（正在使用它的字段将回退默认字体）'})

    # ---------- 底图上传 ----------

    def upload_background(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        headers = request_context.get('headers', {}) or {}
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if 'multipart/form-data' not in (content_type or ''):
            return _ok({'success': False,
                        'message': 'Content-Type 必须是 multipart/form-data'}, 400)

        body = request_context.get('body', b'') or b''
        _fields, raw_name, file_data = _parse_multipart(body, content_type)
        if not file_data or not raw_name:
            return _ok({'success': False, 'message': '未收到文件'}, 400)

        ext = os.path.splitext(raw_name)[1].lower().lstrip('.')
        if ext not in ('png', 'jpg', 'jpeg'):
            return _ok({'success': False, 'message': '底图仅支持 PNG / JPG'}, 400)

        safe = (_sanitize_filename(raw_name)
                or f"bg_{int(datetime.datetime.now().timestamp())}.{ext}")
        rel_path = f'{BG_REL_DIR}/{safe}'
        try:
            os.makedirs(_abs(BG_REL_DIR), exist_ok=True)
            with open(_abs(rel_path), 'wb') as f:
                f.write(file_data)
        except Exception as e:
            logger.error(f"保存底图失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'保存底图失败: {e}'}, 500)

        size = image_size(_abs(rel_path))
        if not size:
            return _ok({'success': False,
                        'message': '无法读取图片尺寸，请确认文件未损坏'}, 400)
        w, h = size
        return _ok({
            'success': True,
            'message': '底图已上传',
            'background': rel_path,
            'pageWidth': w,
            'pageHeight': h,
            'suggestPageSize': suggest_page_size(w, h),
        })

    # ---------- 生成 ----------

    def _read_batch(self, request_context: Dict[str, Any]):
        """Read one consistent snapshot, shared by preflight, warnings and HTML."""
        payload = _json_body(request_context)
        if not isinstance(payload, dict):
            raise PrintRequestError('请求体必须是 JSON 对象')
        template_id = payload.get('templateId')
        cert_numbers = payload.get('certNumbers')
        session_id = payload.get('sessionId', '')
        if not isinstance(template_id, str) or not template_id.strip():
            raise PrintRequestError('缺少有效的 templateId')
        if not isinstance(cert_numbers, list) or not cert_numbers:
            raise PrintRequestError('请选择要打印的证书')
        if len(cert_numbers) > MAX_PRINT_RECORDS:
            raise PrintRequestError(f'单次最多检查或生成 {MAX_PRINT_RECORDS} 张证书')
        if not isinstance(session_id, str):
            raise PrintRequestError('sessionId 必须是字符串')
        with data_store.db.transaction():
            template = _find_template(template_id.strip())
            if not template:
                raise PrintRequestError(f'打印模板不存在: {template_id}', 404)
            records = self._load_certificates(cert_numbers, session_id)
            columns = {_record_key(row['name']) for row in
                       data_store.db.fetchall('PRAGMA table_info(certificates)')}

        # Normalize once. The historical snake-case column and dbColumn-only
        # format must resolve identically in preflight and the generated page.
        template = dict(template)
        if isinstance(template.get('fields'), list):
            fields = []
            for raw in template['fields']:
                if not isinstance(raw, dict):
                    fields.append(raw)
                    continue
                field = dict(raw)
                column = field.get('column') or field.get('dbColumn') or ''
                field['column'] = _record_key(column) if isinstance(column, str) else ''
                for attribute in ('x', 'y', 'fontSize'):
                    if attribute in field:
                        numeric = layout_number(field[attribute])
                        if numeric is not None:
                            field[attribute] = numeric
                if not field.get('label'):
                    field['label'] = CERT_FIELD_LABELS.get(
                        data_store.certificates._to_db_field(field['column']), field['column'])
                fields.append(field)
            template['fields'] = fields
        return payload, template, records, columns

    def validate(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        _payload, template, records, columns = self._read_batch(request_context)
        return _ok(inspect_batch(template, records, columns, PAGE_SIZES))

    def preview(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """One checked certificate, using the print renderer without printing or archiving."""
        payload, template, records, columns = self._read_batch(request_context)
        index = payload.get('pageIndex', 0)
        if type(index) is not int or not 0 <= index < len(records):
            raise PrintRequestError('预览页码超出本次证书范围')
        checked = inspect_batch(template, records, columns, PAGE_SIZES)
        if payload.get('validationToken') != checked['validationToken']:
            return _ok({'success': False, 'message': '证书或模板已变更，请重新检查后查看预览'}, 409)
        if not checked['canGenerate']:
            return _ok({'success': False, 'message': '请修正模板问题后再预览'}, 400)
        record = records[index]
        return _ok({
            'success': True, 'html': build_html(template, [record], preview=True),
            'page': PAGE_SIZES[template.get('pageSize') or 'A4_L'],
            'pageIndex': index, 'itemCount': len(records),
            'reference': {'certNumber': record.get('certNumber'), 'sessionId': record.get('sessionId') or ''},
            'playerName': record.get('playerName') or '',
            'validationToken': checked['validationToken'],
        })

    def generate(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        payload, template, records, columns = self._read_batch(request_context)
        checked = inspect_batch(template, records, columns, PAGE_SIZES)
        if 'validationToken' in payload and payload['validationToken'] != checked['validationToken']:
            return _ok({'success': False, 'message': '证书或模板已变更，请重新检查后再生成'}, 409)
        if not checked['canGenerate']:
            return _ok({**checked, 'success': False, 'message': '打印模板存在错误，请修改模板后重新检查'}, 400)

        return _ok({
            'success': True,
            'html': build_html(template, records),
            'itemCount': len(records),
            'warnings': empty_warnings(template, records),
        })

    @staticmethod
    def _load_certificates(cert_numbers: List[Any], session_id: str) -> List[Dict[str, Any]]:
        rows = data_store.certificates.get_all()
        index: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in rows:
            index[(r.get('certNumber') or '', r.get('sessionId') or '')] = r

        out: List[Dict[str, Any]] = []
        for item in cert_numbers:
            if isinstance(item, dict):
                num = item.get('certNumber')
                sid = item.get('sessionId', session_id)
                explicit = 'sessionId' in item or bool(session_id)
            else:
                num, sid, explicit = item, session_id, bool(session_id)
            if not isinstance(num, str) or not num.strip() or not isinstance(sid, str):
                raise PrintRequestError('证书引用必须包含有效的 certNumber 和字符串 sessionId')
            if not explicit:
                candidates = [value for (number, _), value in index.items() if number == num]
            elif sid in ('', 'legacy-import'):
                # The certificate UI labels old empty sessions as legacy-import.
                # Accept that alias only when it identifies exactly one record.
                candidates = [index[key] for key in ((num, ''), (num, 'legacy-import')) if key in index]
            else:
                candidates = [index[(num, sid)]] if (num, sid) in index else []
            if len(candidates) > 1:
                raise PrintRequestError(f'证书编号 {num} 对应多个批次，请明确选择唯一批次后重试')
            if not candidates:
                raise PrintRequestError(f'证书不存在或已删除：{num}（批次：{sid or "未指定"}）', 404)
            out.append(candidates[0])
        return out

    # ---------- 归档 + 留痕 ----------

    def archive(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        payload = _json_body(request_context)
        if not isinstance(payload, dict):
            return _ok({'success': False, 'message': '请求体必须是 JSON 对象'}, 400)

        html = payload.get('html') or ''
        template_id = (payload.get('templateId') or '').strip()
        if not html:
            return _ok({'success': False, 'message': '缺少要归档的内容'}, 400)

        template = _find_template(template_id) if template_id else None
        doc_type = (payload.get('docType')
                    or (template or {}).get('docType')
                    or 'certificate')
        title = payload.get('title') or (template or {}).get('name') or '打印批次'

        now = datetime.datetime.now()
        log_id = str(uuid.uuid4())
        type_dir = ARCHIVE_TYPE_DIR.get(doc_type, '其他')
        rel_dir = f'{ARCHIVE_ROOT}/{type_dir}/{now.strftime("%Y-%m")}'
        rel_path = (f'{rel_dir}/'
                    f'{_sanitize_filename(title)}_{now.strftime("%Y-%m-%d_%H-%M-%S")}_{log_id}.html')

        snapshot_path = ''
        try:
            os.makedirs(os.path.join(ARCHIVES_DIR, rel_dir), exist_ok=True)
            with open(os.path.join(ARCHIVES_DIR, rel_path), 'x', encoding='utf-8') as f:
                f.write(html)
            snapshot_path = rel_path
        except Exception as e:
            # 归档失败不阻断留痕 —— 打印是用户的当务之急
            logger.error(f"归档打印件失败（不阻断留痕）: {e}")

        try:
            with data_store.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO print_logs
                        (id, doc_type, title, template_id, template_snapshot,
                         entity_type, entity_id, entity_name, item_count, ref_ids,
                         snapshot_path, printed_by, printed_at, ip_address)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        log_id,
                        doc_type,
                        title,
                        template_id,
                        json.dumps(template or {}, ensure_ascii=False),
                        payload.get('entityType'),
                        payload.get('entityId'),
                        payload.get('entityName'),
                        payload.get('itemCount') or 0,
                        json.dumps(payload.get('refIds') or [], ensure_ascii=False),
                        snapshot_path,
                        _username(request_context),
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                        _client_ip(request_context),
                    ),
                )
        except Exception as e:
            logger.error(f"写打印留痕失败: {e}", exc_info=True)
            return _ok({'success': False, 'message': f'留痕写入失败: {e}'}, 500)

        return _ok({
            'success': True,
            'message': '已归档' if snapshot_path else '已记录（归档失败）',
            'logId': log_id,
            'snapshotPath': snapshot_path,
            'archived': bool(snapshot_path),
        })

    # ---------- 记录 ----------

    def logs(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        doc_type = _qp(request_context, 'docType', '')
        where, params = [], []
        if doc_type:
            where.append('doc_type = ?')
            params.append(doc_type)
        sql = 'SELECT * FROM print_logs'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY printed_at DESC LIMIT 200'
        return _ok({'success': True,
                    'logs': data_store.db.fetchall(sql, tuple(params))})

    def get_doc(self, log_id: str) -> Dict[str, Any]:
        row = data_store.db.fetchone('SELECT * FROM print_logs WHERE id = ?', (log_id,))
        if not row:
            return _ok({'success': False, 'message': '记录不存在'}, 404)
        rel = row.get('snapshot_path') or ''
        if not rel:
            return _ok({'success': False, 'message': '该批次没有归档件'}, 404)
        abs_path = _resolve_snapshot(rel)
        if not os.path.isfile(abs_path):
            return _ok({'success': False, 'message': '归档件已丢失'}, 404)
        with open(abs_path, 'r', encoding='utf-8') as f:
            return _ok({'success': True, 'html': f.read(),
                        'title': row.get('title') or ''})

    # ---------- 可选：打开设计稿源文件 ----------

    def open_source(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        payload = _json_body(request_context)
        template_id = (payload or {}).get('templateId', '') if isinstance(payload, dict) else ''
        template = _find_template(template_id) if template_id else None
        src = (template or {}).get('sourcePath') or ''
        if not src:
            return _ok({'success': False, 'message': '该模板未登记设计稿源文件'}, 400)
        abs_path = _abs(src)
        if not os.path.exists(abs_path):
            return _ok({'success': False, 'message': '设计稿源文件不存在'}, 404)
        try:
            _open_with_os(abs_path)
            return _ok({'success': True, 'message': '已打开'})
        except Exception as e:
            logger.warning(f"打开源文件失败（可忽略）: {e}")
            return _ok({'success': True, 'message': 'ok'})
