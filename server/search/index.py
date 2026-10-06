# -*- coding: utf-8 -*-
"""全局搜索的全文索引（FTS5）。

## 为什么要索引

原实现每次搜索都把 `projects/players/organizations/finances` 整表读进内存
（`get_all()`），再逐条做子串匹配。数据量涨了会明显变慢 —— 而且每次搜索都要
反序列化 JSON 字段。改为 FTS5 索引后，搜索走索引，不再全表加载。

## 中文分词方案：按字切分 + phrase 查询

FTS5 自带的分词器对中文都不够用（均已实测）：

- `unicode61`（默认）：不切分中文，整串当一个 token。
- `trigram`：要求查询至少 3 个字符 —— **「张三」「展演」这类 2 字词恒为 0 结果**。

所以这里把文本**按字符切开**再入库（`张三` → `张 三`），
查询时用 phrase 语法（`"张 三"` 表示「张」紧跟「三」）。
这样等价于子串匹配（与原 `_match` 的 `in` 语义一致），
且**任意长度的查询都能走索引**，不需要回退 LIKE。

## 索引新鲜度

`save_all_data` 成功后写 `searchIndexRev`（随机串）。
搜索前对比 `searchIndexedRev`，不一致才重建 ——
**保存路径不受影响**，重建只在「数据变了之后的第一次搜索」发生。
"""

import json
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 索引覆盖的模块（顺序即前端展示顺序）
MODULE_ORDER = ('projects', 'players', 'organizations', 'certificates',
                'finances', 'knowledge', 'printLogs')

# 知识库类型归一（与 db.py::_load_knowledge 的 LEGACY_MAP 保持一致）
KNOWLEDGE_TYPES = ('guide', 'troubleshoot', 'case', 'tip', 'reference')
LEGACY_TYPE_MAP = {'solutions': 'guide', 'practices': 'tip', 'training': 'reference'}

REV_KEY = 'searchIndexRev'          # 数据版本（save 时写）
INDEXED_REV_KEY = 'searchIndexedRev'  # 已索引版本（重建后写）

# 索引格式版本：**改动索引结构或索引内容时必须 +1**。
# 否则数据没变、rev 没变，老索引不会重建 —— 新增的字段/模块会静默搜不到。
INDEX_VERSION = 2


# ---------- 小工具 ----------

def _dicts(conn, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    """执行查询并返回 dict 列表（不依赖 row_factory 的具体形态）。"""
    cur = conn.execute(sql, params)
    cols = [d[0] for d in (cur.description or [])]
    out = []
    for row in cur.fetchall():
        out.append(dict(zip(cols, row)))
    return out


def _json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (ValueError, TypeError):
        return fallback


def _get_setting(conn, key: str, default: str = '') -> str:
    rows = _dicts(conn, 'SELECT value FROM settings WHERE key = ?', (key,))
    if not rows:
        return default
    return str(rows[0].get('value') or default)


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        'INSERT OR REPLACE INTO settings (key, value, updated_at) '
        'VALUES (?, ?, datetime("now", "localtime"))',
        (key, value)
    )


def split_chars(text: Any) -> str:
    """把文本按字符切开，供 unicode61 做 phrase 查询。

    中文没有词间空格，unicode61 不会切分；这里手工插空格，
    让每个字符成为独立 token，phrase 查询即可实现子串匹配。
    """
    if text is None:
        return ''
    return ' '.join(ch for ch in str(text) if not ch.isspace())


def build_phrase_query(q: str) -> Optional[str]:
    """把用户输入转成 FTS5 phrase 查询。

    `张三` → `"张 三"`，表示「张」紧跟「三」，即子串匹配。
    返回 None 表示查询为空（调用方应直接返回空结果）。
    """
    chars = [ch for ch in str(q or '') if not ch.isspace() and ch != '"']
    if not chars:
        return None
    return '"' + ' '.join(chars) + '"'


def _date_of(item: Dict[str, Any]) -> str:
    for key in ('created_at', 'updated_at', 'start_date', 'date'):
        value = item.get(key)
        if value:
            return str(value)[:10]
    return ''


def _parse_print_refs(raw: Any) -> List[str]:
    """从 `print_logs.ref_ids` 里取出证书编号。

    历史格式是纯字符串数组 `["C-001", ...]`；新格式是对象数组
    `[{"certNumber": "C-001", "sessionId": "..."}]` —— 两种都要兼容，
    否则老留痕会被静默漏掉。
    """
    values = _json(raw, [])
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        number = value.get('certNumber') if isinstance(value, dict) else value
        number = str(number or '').strip()
        if number:
            out.append(number)
    return out


def _join_text(*parts: Any) -> str:
    """把若干可搜索字段拼成一段文本（跳过 None 与非字符串容器）。"""
    out: List[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            out.extend(str(x) for x in part if x is not None)
        elif isinstance(part, dict):
            out.extend(str(v) for v in part.values() if isinstance(v, (str, int, float)))
        else:
            out.append(str(part))
    return ' '.join(x for x in out if x)


# ---------- 索引构建 ----------

def _build_docs(conn) -> List[Tuple]:
    """产出所有待索引的文档行（与 search/routes.py 的展示语义保持一致）。"""
    proj_map = {r['id']: (r.get('name') or '')
                for r in _dicts(conn, 'SELECT id, name FROM projects')}
    org_map = {r['id']: (r.get('name') or '')
               for r in _dicts(conn, 'SELECT id, name FROM organizations')}

    docs: List[Tuple] = []

    def add(module, doc_id, title, sub, category, entity_names, doc_date, route, searchable):
        docs.append((
            str(doc_id or ''), module, title or '', sub or '', category or '',
            entity_names or '', doc_date or '', route or '', split_chars(searchable),
        ))

    # ---- 项目 ----
    for p in _dicts(conn, 'SELECT * FROM projects'):
        add('projects', p.get('id'), p.get('name') or '(未命名)',
            p.get('type') or '', p.get('type') or '', p.get('name') or '',
            _date_of(p), f"/projects/{p.get('id')}",
            _join_text(p.get('name'), p.get('type'), p.get('manager'), p.get('description')))

    # ---- 选手 ----
    for p in _dicts(conn, 'SELECT * FROM players'):
        names = []
        if proj_map.get(p.get('project_id')):
            names.append(proj_map[p['project_id']])
        if org_map.get(p.get('org_id')):
            names.append(org_map[p['org_id']])
        add('players', p.get('id'), p.get('name') or '(未命名)',
            p.get('category') or '', p.get('category') or '', ' '.join(names),
            _date_of(p), f"/players/{p.get('id')}",
            _join_text(p.get('name'), p.get('category'), p.get('phone'),
                       p.get('note'), p.get('stage')))

    # ---- 机构 ----
    for o in _dicts(conn, 'SELECT * FROM organizations'):
        add('organizations', o.get('id'), o.get('name') or '(未命名)',
            o.get('type') or '', o.get('type') or '', o.get('name') or '',
            _date_of(o), f"/organizations/{o.get('id')}",
            _join_text(o.get('name'), o.get('type'), o.get('contact'),
                       o.get('phone'), o.get('note')))

    # ---- 证书（原实现漏了，这里补上：证书是核心数据，搜不到是明显缺口）----
    for c in _dicts(conn, 'SELECT * FROM certificates'):
        title = c.get('player_name') or '(未命名)'
        sub = ' '.join(x for x in (c.get('award'), c.get('cert_round')) if x)
        add('certificates', c.get('cert_number'), title, sub,
            c.get('award') or '', c.get('org_name') or '',
            _date_of(c), '/certificates',
            _join_text(c.get('player_name'), c.get('award'), c.get('work_name'),
                       c.get('cert_number'), c.get('cert_round'), c.get('group_name'),
                       c.get('instructor'), c.get('org_name'), c.get('receiving_org'),
                       c.get('language'), c.get('promotion')))

    # ---- 财务 ----
    for f in _dicts(conn, 'SELECT * FROM finances'):
        add('finances', f.get('id'), f.get('title') or '(无摘要)',
            f"{f.get('type') or ''} {f.get('category') or ''}".strip(),
            f.get('type') or f.get('category') or '', '',
            _date_of(f), '/finance',
            _join_text(f.get('title'), f.get('category'), f.get('note'), f.get('type')))

    # ---- 知识库（type 需按 legacy 映射归一，与 db.py 一致）----
    for k in _dicts(conn, 'SELECT * FROM knowledge'):
        raw_type = k.get('type') or 'guide'
        ktype = LEGACY_TYPE_MAP.get(raw_type, raw_type)
        if ktype not in KNOWLEDGE_TYPES:
            ktype = raw_type
        add('knowledge', k.get('id'), k.get('title') or '(未命名)',
            ktype, ktype, '', _date_of(k), f"/knowledge/{k.get('id')}",
            _join_text(k.get('title'), k.get('description'),
                       _json(k.get('tags'), []), _json(k.get('fields'), {})))

    # ---- 打印留痕 ----
    # 留痕的 ref_ids 只存证书编号，单看搜不到人。这里把编号关联回证书，
    # 把**选手名**一起索引进去 —— 这样搜「张三」能找到「张三的证书打印过」。
    cert_names = {c.get('cert_number'): (c.get('player_name') or '')
                  for c in _dicts(conn, 'SELECT cert_number, player_name FROM certificates')}
    for log in _dicts(conn, 'SELECT * FROM print_logs'):
        refs = _parse_print_refs(log.get('ref_ids'))
        names = [cert_names[n] for n in refs if cert_names.get(n)]
        printed_at = str(log.get('printed_at') or '')
        add('printLogs', log.get('id'), log.get('title') or '(打印批次)',
            f"{log.get('item_count') or 0} 份 · {printed_at[:16]}",
            log.get('doc_type') or '', ' '.join(names),
            printed_at[:10], '/print',
            _join_text(log.get('title'), names, refs, printed_at))

    return docs


def rebuild(conn) -> int:
    """全量重建搜索索引。返回索引文档数。"""
    docs = _build_docs(conn)
    # 清空旧索引。注意：`INSERT INTO ... VALUES('delete-all')` 只适用于
    # contentless / external-content 的 FTS5 表，我们这张是普通表，只能用 DELETE。
    conn.execute('DELETE FROM search_index')
    if docs:
        conn.executemany(
            'INSERT INTO search_index '
            '(doc_id, module, display_title, display_sub, category, '
            ' entity_names, doc_date, route, body) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            docs
        )
    return len(docs)


def mark_dirty(conn) -> None:
    """标记索引已过期（在数据保存成功后调用）。"""
    _set_setting(conn, REV_KEY, uuid.uuid4().hex)


def ensure_fresh(conn) -> bool:
    """确保索引与数据一致；不一致则重建。返回是否发生了重建。

    版本号把「索引格式版本」也算进去 —— 改了 `_build_docs` 却没碰数据时，
    靠它强制重建，避免新索引内容静默失效。
    """
    current = f'{INDEX_VERSION}:{_get_setting(conn, REV_KEY)}'
    indexed = _get_setting(conn, INDEXED_REV_KEY)
    try:
        count = conn.execute('SELECT count(*) FROM search_index').fetchone()[0]
    except Exception:
        count = 0
    # 索引为空也要重建（老库首次使用、或上次重建失败）
    if current == indexed and count:
        return False
    try:
        n = rebuild(conn)
        _set_setting(conn, INDEXED_REV_KEY, current)
        logger.info(f"搜索索引已重建：{n} 条")
        return True
    except Exception as e:
        logger.error(f"重建搜索索引失败: {e}", exc_info=True)
        return False


# ---------- 查询 ----------

def search(conn, q: str) -> List[Dict[str, Any]]:
    """按关键词查索引，返回候选文档（未做 type/entity/date 过滤）。

    调用方负责过滤与分页；这里只负责「文本命中」这一层。
    """
    phrase = build_phrase_query(q)
    if not phrase:
        return []
    try:
        return _dicts(
            conn,
            'SELECT doc_id, module, display_title, display_sub, category, '
            '       entity_names, doc_date, route '
            'FROM search_index WHERE search_index MATCH ?',
            (phrase,)
        )
    except Exception as e:
        logger.warning(f"搜索索引查询失败（返回空结果）: {e}")
        return []


def all_docs(conn, limit: int = 2000) -> List[Dict[str, Any]]:
    """无关键词时列出索引中的文档（受 limit 限制，调用方再做每模块截断）。"""
    try:
        return _dicts(
            conn,
            'SELECT doc_id, module, display_title, display_sub, category, '
            '       entity_names, doc_date, route '
            'FROM search_index LIMIT ?',
            (int(limit),)
        )
    except Exception as e:
        logger.warning(f"读取搜索索引失败: {e}")
        return []
