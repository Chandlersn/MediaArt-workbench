"""
XSS 防护工具模块
提供 HTML 实体编码、危险字符过滤、URL 编码等功能
"""

import re
import html
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, unquote


class XSSProtection:
    """XSS 防护工具类"""

    # 危险标签列表
    DANGEROUS_TAGS = [
        'script', 'iframe', 'object', 'embed', 'applet',
        'meta', 'link', 'style', 'base', 'form',
        'svg', 'math'
    ]

    # 危险属性列表
    DANGEROUS_ATTRIBUTES = [
        'onload', 'onerror', 'onclick', 'onmouseover', 'onmouseout',
        'onkeydown', 'onkeyup', 'onkeypress', 'onfocus', 'onblur',
        'onsubmit', 'onreset', 'onchange', 'oninput', 'onscroll',
        'onresize', 'ondrag', 'ondrop', 'oncontextmenu',
        'formaction', 'action', 'xlink:href'
    ]

    # 允许的 URL 协议
    ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel', 'ftp']

    # 危险的 URL 协议
    DANGEROUS_PROTOCOLS = ['javascript', 'vbscript', 'data']

    @staticmethod
    def escape_html(text: Any) -> str:
        """
        HTML 实体编码

        Args:
            text: 要编码的文本

        Returns:
            编码后的字符串
        """
        if text is None:
            return ''

        if not isinstance(text, str):
            text = str(text)

        return html.escape(text, quote=True)

    @staticmethod
    def unescape_html(text: str) -> str:
        """
        HTML 实体解码

        Args:
            text: 要解码的文本

        Returns:
            解码后的字符串
        """
        if not text or not isinstance(text, str):
            return ''

        return html.unescape(text)

    @staticmethod
    def filter_dangerous_chars(text: str, options: Optional[Dict] = None) -> str:
        """
        过滤危险字符

        Args:
            text: 要过滤的文本
            options: 过滤选项

        Returns:
            过滤后的字符串
        """
        if not text or not isinstance(text, str):
            return ''

        options = options or {}
        result = text

        # 移除 null 字节
        result = result.replace('\x00', '')

        # 移除控制字符（保留换行、制表符）
        if options.get('remove_control_chars', True):
            result = re.sub(r'[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result)

        # 移除或转义 JavaScript 协议
        if options.get('filter_js_protocol', True):
            result = re.sub(r'javascript\s*:', '', result, flags=re.IGNORECASE)
            result = re.sub(r'vbscript\s*:', '', result, flags=re.IGNORECASE)
            result = re.sub(r'data\s*:', '', result, flags=re.IGNORECASE)

        # 移除事件处理器
        if options.get('filter_event_handlers', True):
            result = re.sub(r'on\w+\s*=', '', result, flags=re.IGNORECASE)

        return result

    def filter_html_tags(self, html_content: str, options: Optional[Dict] = None) -> str:
        """
        过滤 HTML 标签

        Args:
            html_content: 要过滤的 HTML 内容
            options: 过滤选项

        Returns:
            过滤后的字符串
        """
        if not html_content or not isinstance(html_content, str):
            return ''

        options = options or {}
        result = html_content

        # 允许的标签列表
        allowed_tags = options.get('allowed_tags', [
            'p', 'br', 'strong', 'em', 'u', 'i', 'b',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd',
            'blockquote', 'pre', 'code',
            'a', 'img', 'span', 'div',
            'table', 'thead', 'tbody', 'tr', 'th', 'td'
        ])

        # 移除危险标签
        if options.get('remove_dangerous_tags', True):
            for tag in self.DANGEROUS_TAGS:
                # 移除成对标签
                pattern = rf'<{tag}[^>]*>.*?</{tag}>'
                result = re.sub(pattern, '', result, flags=re.IGNORECASE | re.DOTALL)

                # 移除自闭合标签
                pattern = rf'<{tag}[^>]*/?>'
                result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # 移除不在允许列表中的标签
        if options.get('strict_mode'):
            def replace_tag(match):
                tag_name = match.group(1).lower()
                if tag_name in allowed_tags:
                    return match.group(0)
                return ''

            result = re.sub(r'</?([a-z][a-z0-9]*)\b[^>]*>', replace_tag, result, flags=re.IGNORECASE)

        # 移除危险属性
        result = self.filter_dangerous_attributes(result, options)

        return result

    def filter_dangerous_attributes(self, html_content: str, options: Optional[Dict] = None) -> str:
        """
        过滤危险属性

        Args:
            html_content: HTML 内容
            options: 过滤选项

        Returns:
            过滤后的字符串
        """
        if not html_content or not isinstance(html_content, str):
            return ''

        result = html_content

        # 移除危险属性
        for attr in self.DANGEROUS_ATTRIBUTES:
            # 匹配属性="值" 或 属性='值'
            pattern = rf'\s+{attr}\s*=\s*["\'][^"\']*["\']'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

            # 匹配属性=值（无引号）
            pattern = rf'\s+{attr}\s*=\s*[^\s>]+'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # 移除 javascript: 协议
        result = re.sub(r'(\s+href\s*=\s*["\'])javascript:[^"\']*["\']', r'\1#', result, flags=re.IGNORECASE)
        result = re.sub(r'(\s+src\s*=\s*["\'])javascript:[^"\']*["\']', r'\1#', result, flags=re.IGNORECASE)

        return result

    @staticmethod
    def encode_url(url: str) -> str:
        """
        URL 参数编码

        Args:
            url: URL 字符串

        Returns:
            编码后的 URL
        """
        if not url or not isinstance(url, str):
            return ''

        try:
            # 解码已编码的 URL（防止双重编码）
            decoded = url
            try:
                decoded = unquote(url)
            except Exception:
                pass

            # 编码 URL
            return quote(decoded, safe=':/?#[]@!$&\'()*+,;=')
        except Exception as e:
            print(f'URL 编码失败: {e}')
            return ''

    @staticmethod
    def decode_url(url: str) -> str:
        """
        URL 解码

        Args:
            url: 编码的 URL 字符串

        Returns:
            解码后的 URL
        """
        if not url or not isinstance(url, str):
            return ''

        try:
            return unquote(url)
        except Exception as e:
            print(f'URL 解码失败: {e}')
            return url

    def validate_url(self, url: str) -> Dict[str, Any]:
        """
        验证 URL 安全性

        Args:
            url: URL 字符串

        Returns:
            {'safe': bool, 'message': str}
        """
        if not url or not isinstance(url, str):
            return {'safe': False, 'message': 'URL 不能为空'}

        trimmed = url.strip()

        # 检查协议
        has_protocol = re.match(r'^[a-z]+:', trimmed, re.IGNORECASE)

        if has_protocol:
            protocol = has_protocol.group(0).lower().rstrip(':')
            if protocol not in self.ALLOWED_PROTOCOLS:
                return {'safe': False, 'message': f'不允许的协议: {protocol}'}

        # 检查危险协议
        for proto in self.DANGEROUS_PROTOCOLS:
            if trimmed.lower().startswith(proto + ':'):
                return {'safe': False, 'message': f'禁止使用 {proto}: 协议'}

        # 检查是否包含脚本注入
        if re.search(r'<script', trimmed, re.IGNORECASE) or re.search(r'on\w+\s*=', trimmed, re.IGNORECASE):
            return {'safe': False, 'message': 'URL 包含潜在的脚本代码'}

        return {'safe': True, 'message': ''}

    def sanitize_json(self, data: Any, options: Optional[Dict] = None) -> Any:
        """
        清洗 JSON 数据

        Args:
            data: 要清洗的数据
            options: 清洗选项

        Returns:
            清洗后的数据
        """
        if data is None:
            return data

        options = options or {}

        # 字符串处理
        if isinstance(data, str):
            result = data

            if options.get('escape_html', True):
                result = self.escape_html(result)

            if options.get('filter_dangerous', True):
                result = self.filter_dangerous_chars(result, options)

            return result

        # 列表处理
        if isinstance(data, list):
            return [self.sanitize_json(item, options) for item in data]

        # 字典处理
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # 清洗键名
                clean_key = self.escape_html(key)
                # 递归清洗值
                result[clean_key] = self.sanitize_json(value, options)
            return result

        # 其他类型直接返回
        return data

    def sanitize_form_data(self, form_data: Dict[str, Any], schema: Optional[Dict] = None) -> Dict[str, Any]:
        """
        清洗表单数据

        Args:
            form_data: 表单数据字典
            schema: 字段清洗规则

        Returns:
            清洗后的数据
        """
        if not form_data or not isinstance(form_data, dict):
            return {}

        schema = schema or {}
        result = {}

        for key, value in form_data.items():
            field_schema = schema.get(key, {})
            clean_value = value

            # 字符串处理
            if isinstance(clean_value, str):
                # 去除首尾空格
                if field_schema.get('trim', True):
                    clean_value = clean_value.strip()

                # HTML 转义
                if field_schema.get('escape_html', True):
                    clean_value = self.escape_html(clean_value)

                # 过滤危险字符
                if field_schema.get('filter_dangerous', True):
                    clean_value = self.filter_dangerous_chars(clean_value, field_schema)

                # 允许特定 HTML 标签
                if field_schema.get('allow_html'):
                    clean_value = self.filter_html_tags(clean_value, {
                        'allowed_tags': field_schema.get('allowed_tags'),
                        'strict_mode': True
                    })

            # 列表处理
            if isinstance(clean_value, list):
                clean_value = [
                    self.escape_html(item.strip()) if isinstance(item, str) else item
                    for item in clean_value
                ]

            result[key] = clean_value

        return result

    def create_safe_html(self, html_content: str, options: Optional[Dict] = None) -> str:
        """
        创建安全的 HTML 内容

        Args:
            html_content: HTML 字符串
            options: 选项

        Returns:
            安全的 HTML
        """
        if not html_content or not isinstance(html_content, str):
            return ''

        result = html_content

        # 过滤危险标签
        result = self.filter_html_tags(result, options)

        # 过滤危险属性
        result = self.filter_dangerous_attributes(result, options)

        # 过滤危险字符
        result = self.filter_dangerous_chars(result, options)

        return result

    @staticmethod
    def whitelist_filter(text: str, pattern: str) -> str:
        """
        白名单过滤器

        Args:
            text: 输入字符串
            pattern: 允许的字符模式（正则）

        Returns:
            过滤后的字符串
        """
        if not text or not isinstance(text, str):
            return ''

        matches = re.findall(pattern, text)
        return ''.join(matches)

    @staticmethod
    def blacklist_filter(text: str, pattern: str) -> str:
        """
        黑名单过滤器

        Args:
            text: 输入字符串
            pattern: 禁止的字符模式（正则）

        Returns:
            过滤后的字符串
        """
        if not text or not isinstance(text, str):
            return ''

        return re.sub(pattern, '', text)


# 创建全局实例
xss_protection = XSSProtection()


# 便捷函数
def escape_html(text: Any) -> str:
    """HTML 实体编码"""
    return xss_protection.escape_html(text)


def sanitize_input(data: Any, options: Optional[Dict] = None) -> Any:
    """清洗输入数据"""
    return xss_protection.sanitize_json(data, options)


def sanitize_form(form_data: Dict[str, Any], schema: Optional[Dict] = None) -> Dict[str, Any]:
    """清洗表单数据"""
    return xss_protection.sanitize_form_data(form_data, schema)


def validate_url(url: str) -> Dict[str, Any]:
    """验证 URL 安全性"""
    return xss_protection.validate_url(url)


def filter_html(html_content: str, options: Optional[Dict] = None) -> str:
    """过滤 HTML 内容"""
    return xss_protection.filter_html_tags(html_content, options)
