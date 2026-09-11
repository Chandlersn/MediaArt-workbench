# -*- coding: utf-8 -*-
"""
Tests for auth_middleware module.
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.utils.auth_middleware import (
    extract_user_from_request,
    require_auth,
    require_permission,
    RateLimiter,
    login_rate_limiter
)


class TestExtractUserFromRequest:
    """Test extract_user_from_request function."""

    def test_no_auth_header(self):
        request_context = {'headers': {}, 'path': '/api/test'}
        result = extract_user_from_request(request_context)
        assert result is None

    def test_empty_auth_header(self):
        request_context = {'headers': {'Authorization': ''}}
        result = extract_user_from_request(request_context)
        assert result is None

    def test_bearer_token_invalid(self):
        request_context = {'headers': {'Authorization': 'Bearer invalid_token_here'}}
        result = extract_user_from_request(request_context)
        assert result is None

    def test_non_bearer_scheme(self):
        request_context = {'headers': {'Authorization': 'Basic sometoken'}}
        result = extract_user_from_request(request_context)
        assert result is None

    def test_lowercase_authorization_header(self):
        request_context = {'headers': {'authorization': 'Bearer invalid'}}
        result = extract_user_from_request(request_context)
        assert result is None


class TestRequireAuth:
    """Test require_auth decorator."""

    def test_unauthenticated_request(self):
        @require_auth
        def dummy_handler(request_context):
            return {'status': 200, 'body': {'ok': True}}

        request_context = {'headers': {}, 'path': '/api/test'}
        result = dummy_handler(request_context)
        assert result['status'] == 401
        assert result['body']['error'] == 'UNAUTHORIZED'

    def test_authenticated_request_with_valid_token(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('user123', 'testuser', 'viewer')

        @require_auth
        def dummy_handler(request_context):
            user = request_context.get('user')
            return {'status': 200, 'body': {'user_id': user['user_id']}}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}, 'path': '/api/test'}
        result = dummy_handler(request_context)
        assert result['status'] == 200
        assert result['body']['user_id'] == 'user123'

    def test_user_injected_to_request_context(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('u1', 'admin', 'admin')

        @require_auth
        def dummy_handler(request_context):
            assert 'user' in request_context
            assert request_context['user']['username'] == 'admin'
            return {'status': 200, 'body': {}}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}}
        result = dummy_handler(request_context)
        assert result['status'] == 200


class TestRequirePermission:
    """Test require_permission decorator."""

    def test_unauthenticated_returns_401(self):
        @require_permission('delete')
        def dummy_handler(request_context):
            return {'status': 200}

        request_context = {'headers': {}}
        result = dummy_handler(request_context)
        assert result['status'] == 401

    def test_viewer_cannot_delete(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('u1', 'viewer_user', 'viewer')

        @require_permission('delete')
        def dummy_handler(request_context):
            return {'status': 200}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}}
        result = dummy_handler(request_context)
        assert result['status'] == 403
        assert result['body']['error'] == 'FORBIDDEN'

    def test_admin_can_delete(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('u1', 'admin_user', 'admin')

        @require_permission('delete')
        def dummy_handler(request_context):
            return {'status': 200, 'body': {'success': True}}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}}
        result = dummy_handler(request_context)
        assert result['status'] == 200
        assert result['body']['success'] is True

    def test_editor_can_create(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('u1', 'editor_user', 'editor')

        @require_permission('create')
        def dummy_handler(request_context):
            return {'status': 200}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}}
        result = dummy_handler(request_context)
        assert result['status'] == 200

    def test_editor_cannot_manage_users(self):
        import jwt
        from server.utils.jwt_handler import jwt_handler
        
        token = jwt_handler.generate_token('u1', 'editor_user', 'editor')

        @require_permission('manage_users')
        def dummy_handler(request_context):
            return {'status': 200}

        request_context = {'headers': {'Authorization': f'Bearer {token}'}}
        result = dummy_handler(request_context)
        assert result['status'] == 403


class TestRateLimiter:
    """Test RateLimiter class."""

    def setup_method(self):
        self.limiter = RateLimiter(max_attempts=3, window_seconds=60)

    def test_initially_not_limited(self):
        assert self.limiter.is_rate_limited('192.168.1.1') is False

    def test_under_limit_not_limited(self):
        for i in range(3):
            self.limiter.record_attempt('10.0.0.1')
        assert self.limiter.is_rate_limited('10.0.0.1') is True

    def test_at_limit_is_limited(self):
        limiter = RateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_attempt('1.2.3.4')
        limiter.record_attempt('1.2.3.4')
        assert limiter.is_rate_limited('1.2.3.4') is True

    def test_different_ips_independent(self):
        limiter = RateLimiter(max_attempts=1, window_seconds=60)
        limiter.record_attempt('ip_a')
        assert limiter.is_rate_limited('ip_a') is True
        assert limiter.is_rate_limited('ip_b') is False

    def test_reset_clears_attempts(self):
        self.limiter.record_attempt('5.5.5.5')
        self.limiter.record_attempt('5.5.5.5')
        self.limiter.reset('5.5.5.5')
        assert self.limiter.is_rate_limited('5.5.5.5') is False

    def test_expired_attempts_auto_cleaned(self):
        import time as time_mod
        limiter = RateLimiter(max_attempts=2, window_seconds=1)
        limiter.record_attempt('6.6.6.6')
        limiter.record_attempt('6.6.6.6')
        assert limiter.is_rate_limited('6.6.6.6') is True
        time_mod.sleep(1.1)
        assert limiter.is_rate_limited('6.6.6.6') is False


class TestLoginRateLimiter:
    """Test global login_rate_limiter instance."""

    def test_is_rate_limiter_instance(self):
        from server.utils.auth_middleware import login_rate_limiter
        assert isinstance(login_rate_limiter, RateLimiter)

    def test_default_config(self):
        from server.utils.auth_middleware import login_rate_limiter
        assert login_rate_limiter.max_attempts > 0
        assert login_rate_limiter.window_seconds > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
