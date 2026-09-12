"""
Notifications API routes module.

补齐模块化后端缺失的「通知中心」接口（前端 notificationService.js / NotificationPanel.vue
依赖），统一挂在 /api/notifications 前缀下：

    GET    /api/notifications/unread-count                      未读数         -> {count}
    GET    /api/notifications?page&pageSize&type&isRead         列表+分页      -> {data,total,unreadCount}
    POST   /api/notifications/read      {id}                    单个已读
    POST   /api/notifications/read-all                          全部已读
    POST   /api/notifications/create    {title,content,type,link}
    DELETE /api/notifications/{id}                              删除单条

约定说明：
- 数据库表 notifications 的列是 `read`（0/1）与 `created_at`，而前端消费的是
  `isRead` 与 `createdAt`，这里显式做一次字段映射（不依赖模型自动驼峰转换，
  因为 `read` 无下划线不会被转换，且 notifications 表没有 updated_at 列，
  走通用 Model.create/update 会因补写 updated_at 而报错，故统一用原始 SQL）。
- 鉴权：与 knowledge/search 路由一致，在 handle_request 内联完成，不使用函数式装饰器。
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from server.database.store import data_store
from server.utils.auth_middleware import extract_user_from_request

logger = logging.getLogger(__name__)

TABLE = 'notifications'
JSON_HEADERS = {'Content-Type': 'application/json'}


def _ok(body: Dict[str, Any], status: int = 200) -> Dict[str, Any]:
    return {'status': status, 'body': body, 'headers': dict(JSON_HEADERS)}


def _qp(request_context: Dict[str, Any], key: str, default: str = '') -> str:
    qp = request_context.get('query_params', {}) or {}
    val = qp.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


def _row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id': row.get('id'),
        'title': row.get('title'),
        'content': row.get('content') or '',
        'type': row.get('type') or 'info',
        'isRead': bool(row.get('read', 0)),
        'createdAt': row.get('created_at') or row.get('createdAt'),
        'link': row.get('link') or None,
    }


class NotificationsRouter:
    """Router for the notification center endpoints."""

    # ---------- 工具 ----------
    def _auth(self, request_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user = extract_user_from_request(request_context)
        if not user:
            return _ok({'success': False, 'message': '认证失败，Token 无效或缺失',
                        'error': 'UNAUTHORIZED'}, 401)
        request_context['user'] = user
        return None

    # ---------- 分发 ----------
    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')
        norm = path.split('?')[0]

        try:
            if norm == '/api/notifications/unread-count' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.unread_count()

            if norm == '/api/notifications' and method == 'GET':
                if (a := self._auth(request_context)):
                    return a
                return self.list_notifications(request_context)

            if norm == '/api/notifications/read' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.mark_read(request_context)

            if norm == '/api/notifications/read-all' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.mark_all_read()

            if norm == '/api/notifications/create' and method == 'POST':
                if (a := self._auth(request_context)):
                    return a
                return self.create(request_context)

            if norm.startswith('/api/notifications/') and method == 'DELETE':
                if (a := self._auth(request_context)):
                    return a
                return self.delete(norm.rsplit('/', 1)[-1])

            return _ok({'success': False, 'error': 'Method Not Allowed'}, 405)
        except Exception as e:
            logger.error(f"处理通知请求失败: {e}", exc_info=True)
            return _ok({'success': False, 'error': 'Internal Server Error', 'message': str(e)}, 500)

    # ---------- 业务 ----------
    def unread_count(self) -> Dict[str, Any]:
        try:
            n = data_store.db.fetchval(f"SELECT COUNT(*) FROM {TABLE} WHERE read = 0")
            return _ok({'success': True, 'count': int(n or 0)})
        except Exception as e:
            logger.error(f"统计未读通知失败: {e}")
            return _ok({'success': True, 'count': 0})

    def list_notifications(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            page = max(1, int(_qp(request_context, 'page', '1') or 1))
        except ValueError:
            page = 1
        try:
            page_size = max(1, int(_qp(request_context, 'pageSize', '20') or 20))
        except ValueError:
            page_size = 20
        ntype = _qp(request_context, 'type', 'all') or 'all'
        is_read = _qp(request_context, 'isRead', 'all') or 'all'

        where = []
        params: list = []
        if ntype and ntype != 'all':
            where.append('type = ?')
            params.append(ntype)
        if is_read in ('true', '1', 'read'):
            where.append('read = 1')
        elif is_read in ('false', '0', 'unread'):
            where.append('read = 0')
        where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

        try:
            total = data_store.db.fetchval(f"SELECT COUNT(*) FROM {TABLE} {where_sql}", tuple(params)) or 0
            unread = data_store.db.fetchval(f"SELECT COUNT(*) FROM {TABLE} WHERE read = 0") or 0
            rows = data_store.db.fetchall(
                f"SELECT * FROM {TABLE} {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params) + (page_size, (page - 1) * page_size)
            )
            return _ok({
                'success': True,
                'data': [_row_to_item(r) for r in rows],
                'total': int(total),
                'unreadCount': int(unread),
                'page': page,
                'pageSize': page_size,
            })
        except Exception as e:
            logger.error(f"查询通知列表失败: {e}")
            return _ok({'success': True, 'data': [], 'total': 0, 'unreadCount': 0})

    def mark_read(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        nid = data.get('id')
        if not nid:
            return _ok({'success': False, 'message': '缺少通知 id'}, 400)
        try:
            data_store.db.execute(f"UPDATE {TABLE} SET read = 1 WHERE id = ?", (nid,))
            return _ok({'success': True, 'message': 'ok'})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    def mark_all_read(self) -> Dict[str, Any]:
        try:
            data_store.db.execute(f"UPDATE {TABLE} SET read = 1")
            return _ok({'success': True, 'message': 'ok'})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)

    def create(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}
        title = (data.get('title') or '').strip()
        if not title:
            return _ok({'success': False, 'message': '标题不能为空'}, 400)
        nid = data.get('id') or str(uuid.uuid4())
        try:
            # notifications 表仅有 (id,title,content,type,read,created_at)，
            # 若表恰好含 link 列则一并写入，否则忽略。
            cols = {c.get('name') for c in data_store.db.fetchall("PRAGMA table_info(notifications)")}
            fields = ['id', 'title', 'content', 'type', 'read', 'created_at']
            values = [
                nid, title, data.get('content') or '',
                data.get('type') or 'info',
                1 if data.get('isRead') else 0,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ]
            if 'link' in cols:
                fields.append('link')
                values.append(data.get('link') or None)
            placeholders = ', '.join(['?'] * len(fields))
            data_store.db.execute(
                f"INSERT INTO {TABLE} ({', '.join(fields)}) VALUES ({placeholders})",
                tuple(values)
            )
            return _ok({'success': True, 'id': nid})
        except Exception as e:
            logger.error(f"创建通知失败: {e}")
            return _ok({'success': False, 'message': str(e)}, 500)

    def delete(self, notification_id: str) -> Dict[str, Any]:
        if not notification_id:
            return _ok({'success': False, 'message': '缺少通知 id'}, 400)
        try:
            data_store.db.execute(f"DELETE FROM {TABLE} WHERE id = ?", (notification_id,))
            return _ok({'success': True, 'message': '已删除'})
        except Exception as e:
            return _ok({'success': False, 'message': str(e)}, 500)
