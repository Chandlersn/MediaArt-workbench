# -*- coding: utf-8 -*-
"""
认证模块测试
"""
import pytest
from server.utils.jwt_handler import JWTHandler, jwt_handler


class TestJWTHandler:
    """测试 JWT 处理器"""

    def test_generate_token(self):
        """测试创建 token"""
        token = jwt_handler.generate_token('u001', 'testuser', 'editor')
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self):
        """测试验证有效 token"""
        token = jwt_handler.generate_token('u001', 'testuser', 'editor')
        verified = jwt_handler.verify_token(token)
        assert verified is not None
        assert verified.get('user_id') == 'u001'
        assert verified.get('username') == 'testuser'
        assert verified.get('role') == 'editor'

    def test_verify_invalid_token(self):
        """测试验证无效 token"""
        verified = jwt_handler.verify_token('invalid_token_string')
        assert verified is None

    def test_verify_empty_token(self):
        """测试验证空 token"""
        verified = jwt_handler.verify_token('')
        assert verified is None
        verified = jwt_handler.verify_token(None)
        assert verified is None

    def test_token_contains_expiration(self):
        """测试 token 包含过期时间"""
        token = jwt_handler.generate_token('u001', 'testuser')
        verified = jwt_handler.verify_token(token)
        assert 'exp' in verified
        assert verified['exp'] > 0

    def test_generate_refresh_token(self):
        """测试创建 refresh token"""
        refresh_token = jwt_handler.generate_refresh_token('u001', 'testuser')
        assert refresh_token is not None
        assert isinstance(refresh_token, str)

    def test_refresh_token_longer_expiration(self):
        """refresh token 过期时间应该更长"""
        access_token = jwt_handler.generate_token('u001', 'testuser')
        refresh_token = jwt_handler.generate_refresh_token('u001', 'testuser')

        access_verified = jwt_handler.verify_token(access_token)
        refresh_verified = jwt_handler.verify_token(refresh_token)

        # refresh token 过期时间应该比 access token 长
        assert refresh_verified['exp'] > access_verified['exp']

    def test_create_token_response(self):
        """测试创建完整 token 响应"""
        from server.utils import create_token_response
        response = create_token_response(
            user_id='u001',
            username='testuser',
            role='editor'
        )
        assert 'access_token' in response
        assert 'refresh_token' in response
        assert 'expires_in' in response
        assert response['access_token'] is not None
        assert response['refresh_token'] is not None