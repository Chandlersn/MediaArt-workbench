"""
Players API routes module.
"""

import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_permission

logger = logging.getLogger(__name__)


class PlayersRouter:
    """Router for player-related API endpoints."""

    def handle_request(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle player-related requests."""
        path = request_context.get('path', '')
        method = request_context.get('method', 'GET')

        try:
            if method == 'GET' and path == '/api/players/list':
                return self.list_players(request_context)
            elif method == 'GET' and path == '/api/players':
                return self.list_players(request_context)
            elif method == 'GET' and path.startswith('/api/players/'):
                player_id = path.split('/')[-1]
                return self.get_player(player_id, request_context)
            # ⚠️ 写入已统一走 POST /api/data/save（见前端 dataService.save）。
            #    原 POST/PUT/DELETE /api/players 无人调用，第二套写路径已退役。
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed',
                             'message': '写入请使用 POST /api/data/save'},
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            logger.error(f"Error handling player request: {e}")
            return {
                'status': 500,
                'body': {'success': False, 'error': 'Internal Server Error', 'message': str(e)},
                'headers': {'Content-Type': 'application/json'}
            }

    @require_permission('players', 'view')
    def list_players(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Get all players with optional filtering."""
        query_params = request_context.get('query_params', {})
        search = query_params.get('search', [''])[0]
        level_filter = query_params.get('level', ['all'])[0]

        players = data_store.players.get_all(order_by='created_at DESC')

        if search:
            search_lower = search[0].lower() if isinstance(search, list) else search.lower()
            players = [p for p in players if search_lower in p.get('name', '').lower()]

        if level_filter and level_filter != 'all':
            players = [p for p in players if p.get('level') == level_filter]

        return {
            'status': 200,
            'body': {'success': True, 'data': players, 'total': len(players)},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('players', 'view')
    def get_player(self, player_id, request_context=None) -> Dict[str, Any]:
        """Get a specific player by ID."""
        player = data_store.players.get_by_id(player_id)
        if player:
            return {
                'status': 200,
                'body': {'success': True, 'data': player},
                'headers': {'Content-Type': 'application/json'}
            }
        return {
            'status': 404,
            'body': {'success': False, 'message': 'Player not found'},
            'headers': {'Content-Type': 'application/json'}
        }

    # 写入方法（create/update/delete_player）已随第二套写路径退役，
    # 统一走 POST /api/data/save → data_store.save_all_data。
