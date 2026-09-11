# -*- coding: utf-8 -*-
"""
XSS 防护模块测试
"""
import pytest
from server.utils.xss_protection import XSSProtection, sanitize_input, sanitize_form


class TestXSSProtection:
    """测试 XSS 防护"""

    def test_sanitize_script_tag(self):
        """测试清洗 script 标签 - 默认会 escape_html"""
        input_text = '<script>alert("xss")</script>'
        result = sanitize_input(input_text)
        # 默认会 escape_html，所以 < 会变成 &lt;
        assert '&lt;' in result
        assert '<script>' not in result

    def test_sanitize_onclick(self):
        """测试清洗 onclick 事件"""
        input_text = '<div onclick="alert(1)">test</div>'
        result = sanitize_input(input_text)
        assert 'onclick' not in result or '&lt;' in result

    def test_sanitize_javascript_protocol(self):
        """测试清洗 javascript 协议"""
        input_text = '<a href="javascript:alert(1)">link</a>'
        result = sanitize_input(input_text)
        assert 'javascript:' not in result

    def test_sanitize_normal_text(self):
        """正常文本应该保留"""
        input_text = '这是一段正常文本'
        result = sanitize_input(input_text)
        assert '正常文本' in result

    def test_sanitize_html_entities(self):
        """测试 HTML 实体转义 - 默认启用"""
        input_text = '<test>'
        result = sanitize_input(input_text)
        assert '&lt;' in result
        assert '<' not in result

    def test_trim_with_sanitize_form(self):
        """测试 sanitize_form 的 trim 功能"""
        form_data = {'username': '  test  '}
        schema = {'username': {'trim': True}}
        result = sanitize_form(form_data, schema)
        assert result['username'] == 'test'


class TestXSSProtectionClass:
    """测试 XSSProtection 类"""

    def test_filter_dangerous_chars(self):
        """测试过滤危险字符"""
        protector = XSSProtection()

        dangerous = 'javascript:alert(1)'
        result = protector.filter_dangerous_chars(dangerous)
        assert 'javascript:' not in result

    def test_escape_html(self):
        """测试 HTML 转义"""
        protector = XSSProtection()

        dangerous = '<script>'
        result = protector.escape_html(dangerous)
        assert '<' not in result
        assert '&lt;' in result


class TestSanitizeForm:
    """测试表单清洗"""

    def test_sanitize_form_basic(self):
        """测试基本表单清洗"""
        form_data = {
            'username': '  testuser<script>  ',
            'description': '<p>normal content</p>'
        }

        schema = {
            'username': {'trim': True, 'escape_html': True, 'filter_dangerous': True},
            'description': {'trim': False, 'escape_html': False}
        }

        result = sanitize_form(form_data, schema)

        # username 应该被 trim 和 escape
        assert '<script>' not in result['username']
        assert result['username'].strip() == 'testuser&lt;script&gt;'

        # description 保留原始 HTML（因为 escape_html=False）
        assert '<p>' in result['description']

    def test_sanitize_form_with_none_values(self):
        """测试包含 None 值的表单"""
        form_data = {
            'username': 'test',
            'optional': None
        }

        schema = {
            'username': {'trim': True},
            'optional': {'trim': True}
        }

        result = sanitize_form(form_data, schema)
        assert result['username'] == 'test'
        assert result['optional'] is None