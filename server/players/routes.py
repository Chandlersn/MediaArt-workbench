"""
Players API routes module.
"""

import json
import logging
from typing import Dict, Any
from server.database.store import data_store
from server.utils.auth_middleware import require_auth, require_permission

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
            elif method == 'POST' and path == '/api/players':
                return self.create_player(request_context)
            elif method == 'PUT' and path.startswith('/api/players/'):
                player_id = path.split('/')[-1]
                return self.update_player(player_id, request_context)
            elif method == 'DELETE' and path.startswith('/api/players/'):
                player_id = path.split('/')[-1]
                return self.delete_player(player_id, request_context)
            else:
                return {
                    'status': 405,
                    'body': {'success': False, 'error': 'Method Not Allowed'},
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

    @require_permission('players', 'edit')
    def create_player(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new player."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        player_id = data_store.players.create(data)
        return {
            'status': 201,
            'body': {'success': True, 'id': player_id, 'message': 'Player created'},
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('players', 'edit')
    def update_player(self, player_id: str, request_context: Dict[str, Any]) -> Dict[str, Any]:
        """Update a player."""
        body = request_context.get('body', b'')
        data = json.loads(body) if body else {}

        success = data_store.players.update(player_id, data)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Player updated' if success else 'Player not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }

    @require_permission('players', 'delete')
    def delete_player(self, player_id, request_context=None) -> Dict[str, Any]:
        """Delete a player."""
        success = data_store.players.delete(player_id)
        return {
            'status': 200,
            'body': {
                'success': success,
                'message': 'Player deleted' if success else 'Player not found'
            },
            'headers': {'Content-Type': 'application/json'}
        }
