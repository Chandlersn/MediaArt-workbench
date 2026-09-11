"""
输入数据校验工具模块
提供常见字段的校验规则和校验方法
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union


class Validator:
    """数据校验器"""

    # 校验规则配置
    RULES = {
        'email': {
            'pattern': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'message': '请输入有效的邮箱地址'
        },
        'phone': {
            'pattern': r'^1[3-9]\d{9}$',
            'message': '请输入有效的11位手机号码'
        },
        'id_card': {
            'pattern': r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$',
            'message': '请输入有效的18位身份证号码'
        },
        'url': {
            'pattern': r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$',
            'message': '请输入有效的URL地址'
        },
        'date': {
            'pattern': r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$',
            'message': '请输入有效的日期格式 (YYYY-MM-DD)'
        },
        'time': {
            'pattern': r'^([01]\d|2[0-3]):[0-5]\d$',
            'message': '请输入有效的时间格式 (HH:MM)'
        },
        'number': {
            'pattern': r'^-?\d+(\.\d+)?$',
            'message': '请输入有效的数字'
        },
        'positive_integer': {
            'pattern': r'^[1-9]\d*$',
            'message': '请输入正整数'
        },
        'username': {
            'pattern': r'^[a-zA-Z][a-zA-Z0-9_]{2,19}$',
            'message': '用户名必须以字母开头，3-20位字母数字下划线'
        },
        'password': {
            'pattern': r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{6,}$',
            'message': '密码至少6位，必须包含字母和数字'
        },
        'chinese_name': {
            'pattern': r'^[\u4e00-\u9fa5]{2,10}$',
            'message': '请输入有效的中文姓名（2-10个汉字）'
        },
        'postal_code': {
            'pattern': r'^[1-9]\d{5}$',
            'message': '请输入有效的邮政编码'
        },
        'bank_card': {
            'pattern': r'^[1-9]\d{15,18}$',
            'message': '请输入有效的银行卡号'
        }
    }

    @classmethod
    def validate(cls, value: Any, rule_name: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        验证单个字段

        Args:
            value: 要验证的值
            rule_name: 规则名称
            options: 额外选项

        Returns:
            {'valid': bool, 'message': str}
        """
        options = options or {}

        # 空值处理
        if value is None or (isinstance(value, str) and value.strip() == ''):
            if options.get('required'):
                return {'valid': False, 'message': options.get('required_message', '此字段为必填项')}
            return {'valid': True, 'message': ''}

        # 转换为字符串
        str_value = str(value).strip()

        # 获取规则
        rule = cls.RULES.get(rule_name)
        if not rule:
            print(f"未知的校验规则: {rule_name}")
            return {'valid': True, 'message': ''}

        # 正则验证
        pattern = rule.get('pattern')
        if pattern and not re.match(pattern, str_value):
            return {'valid': False, 'message': options.get('message', rule.get('message', '验证失败'))}

        return {'valid': True, 'message': ''}

    @classmethod
    def validate_length(cls, value: Any, min_len: Optional[int] = None,
                       max_len: Optional[int] = None, options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        验证字符串长度

        Args:
            value: 要验证的值
            min_len: 最小长度
            max_len: 最大长度
            options: 额外选项

        Returns:
            {'valid': bool, 'message': str}
        """
        options = options or {}

        if not value and options.get('required'):
            return {'valid': False, 'message': options.get('required_message', '此字段为必填项')}

        if not value:
            return {'valid': True, 'message': ''}

        length = len(str(value).strip())

        if min_len is not None and length < min_len:
            return {'valid': False, 'message': options.get('message', f'长度不能少于{min_len}个字符')}

        if max_len is not None and length > max_len:
            return {'valid': False, 'message': options.get('message', f'长度不能超过{max_len}个字符')}

        return {'valid': True, 'message': ''}

    @classmethod
    def validate_range(cls, value: Any, min_val: Optional[Union[int, float]] = None,
                      max_val: Optional[Union[int, float]] = None,
                      options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        验证数字范围

        Args:
            value: 要验证的值
            min_val: 最小值
            max_val: 最大值
            options: 额外选项

        Returns:
            {'valid': bool, 'message': str}
        """
        options = options or {}

        if value is None and options.get('required'):
            return {'valid': False, 'message': options.get('required_message', '此字段为必填项')}

        if value is None:
            return {'valid': True, 'message': ''}

        try:
            num = float(value)
        except (ValueError, TypeError):
            return {'valid': False, 'message': '请输入有效的数字'}

        if min_val is not None and num < min_val:
            return {'valid': False, 'message': options.get('message', f'数值不能小于{min_val}')}

        if max_val is not None and num > max_val:
            return {'valid': False, 'message': options.get('message', f'数值不能大于{max_val}')}

        return {'valid': True, 'message': ''}

    @classmethod
    def validate_date_range(cls, start_date: str, end_date: str,
                           options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        验证日期范围

        Args:
            start_date: 开始日期
            end_date: 结束日期
            options: 额外选项

        Returns:
            {'valid': bool, 'message': str}
        """
        options = options or {}

        if not start_date or not end_date:
            if options.get('required'):
                return {'valid': False, 'message': '请选择日期范围'}
            return {'valid': True, 'message': ''}

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')

            if start > end:
                return {'valid': False, 'message': options.get('message', '开始日期不能晚于结束日期')}

            return {'valid': True, 'message': ''}
        except ValueError as e:
            return {'valid': False, 'message': f'日期格式错误: {str(e)}'}

    @classmethod
    def validate_required(cls, value: Any, field_name: str = '此字段') -> Dict[str, Any]:
        """
        验证必填字段

        Args:
            value: 要验证的值
            field_name: 字段名称

        Returns:
            {'valid': bool, 'message': str}
        """
        if value is None or value == '':
            return {'valid': False, 'message': f'{field_name}不能为空'}

        if isinstance(value, str) and value.strip() == '':
            return {'valid': False, 'message': f'{field_name}不能为空'}

        if isinstance(value, (list, dict)) and len(value) == 0:
            return {'valid': False, 'message': f'{field_name}不能为空'}

        return {'valid': True, 'message': ''}

    @classmethod
    def validate_enum(cls, value: Any, enum_values: List[Any],
                     options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        验证枚举值

        Args:
            value: 要验证的值
            enum_values: 允许的枚举值列表
            options: 额外选项

        Returns:
            {'valid': bool, 'message': str}
        """
        options = options or {}

        if not value and options.get('required'):
            return {'valid': False, 'message': options.get('required_message', '请选择一个选项')}

        if not value:
            return {'valid': True, 'message': ''}

        if value not in enum_values:
            return {'valid': False, 'message': options.get('message', '请选择有效的选项')}

        return {'valid': True, 'message': ''}

    @classmethod
    def validate_all(cls, data: Dict[str, Any], schema: Dict[str, List]) -> Tuple[bool, Dict[str, str]]:
        """
        批量验证多个字段

        Args:
            data: 要验证的数据对象
            schema: 验证规则模式

        Returns:
            (valid, errors) - (是否有效, 错误信息字典)
        """
        errors = {}
        valid = True

        for field, rules in schema.items():
            value = data.get(field)
            field_errors = []

            # 处理多个规则
            for rule in rules:
                result = None

                if isinstance(rule, str):
                    # 简单规则名称
                    result = cls.validate(value, rule)
                elif isinstance(rule, dict):
                    # 复杂规则对象
                    rule_type = rule.get('type')

                    if rule_type == 'required':
                        result = cls.validate_required(value, rule.get('field_name', field))
                    elif rule_type == 'length':
                        result = cls.validate_length(value, rule.get('min'), rule.get('max'), rule)
                    elif rule_type == 'range':
                        result = cls.validate_range(value, rule.get('min'), rule.get('max'), rule)
                    elif rule_type == 'enum':
                        result = cls.validate_enum(value, rule.get('values', []), rule)
                    elif rule_type == 'dateRange':
                        result = cls.validate_date_range(
                            data.get(rule.get('start_field')),
                            data.get(rule.get('end_field')),
                            rule
                        )
                    elif rule_type == 'custom':
                        # 自定义验证函数
                        validate_func = rule.get('validate')
                        if validate_func and callable(validate_func):
                            result = validate_func(value, data)
                    else:
                        result = cls.validate(value, rule_type, rule)

                if result and not result.get('valid'):
                    field_errors.append(result.get('message', '验证失败'))
                    valid = False

            if field_errors:
                errors[field] = field_errors[0]  # 只取第一个错误

        return valid, errors

    @classmethod
    def validate_id_card_advanced(cls, id_card: str) -> Dict[str, Any]:
        """
        验证身份证号码（增强版，包含校验位验证）

        Args:
            id_card: 身份证号码

        Returns:
            {'valid': bool, 'message': str, 'info': dict}
        """
        if not id_card:
            return {'valid': False, 'message': '请输入身份证号码', 'info': None}

        trimmed = id_card.strip().upper()

        # 基本格式验证
        if not re.match(cls.RULES['id_card']['pattern'], trimmed):
            return {'valid': False, 'message': '身份证号码格式错误', 'info': None}

        # 校验位验证
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

        try:
            total = sum(int(trimmed[i]) * weights[i] for i in range(17))
            check_code = check_codes[total % 11]

            if trimmed[17] != check_code:
                return {'valid': False, 'message': '身份证号码校验位错误', 'info': None}

            # 解析信息
            info = {
                'province': trimmed[0:2],
                'city': trimmed[0:4],
                'district': trimmed[0:6],
                'birth_date': f"{trimmed[6:10]}-{trimmed[10:12]}-{trimmed[12:14]}",
                'gender': '男' if int(trimmed[16]) % 2 == 1 else '女'
            }

            return {'valid': True, 'message': '', 'info': info}
        except Exception as e:
            return {'valid': False, 'message': f'身份证号码验证失败: {str(e)}', 'info': None}

    @classmethod
    def add_rule(cls, name: str, rule: Dict[str, Any]) -> None:
        """
        添加自定义验证规则

        Args:
            name: 规则名称
            rule: 规则对象 {'pattern': str, 'message': str}
        """
        if name in cls.RULES:
            print(f"规则 {name} 已存在，将被覆盖")
        cls.RULES[name] = rule


# 常用验证模式
class ValidationPatterns:
    """常用验证模式"""

    # 项目名称：1-50个字符，允许中英文、数字、下划线、横线
    PROJECT_NAME = {
        'pattern': r'^[\u4e00-\u9fa5a-zA-Z0-9_-]{1,50}$',
        'message': '项目名称为1-50个字符，允许中英文、数字、下划线、横线'
    }

    # 机构名称：2-50个字符
    ORG_NAME = {
        'pattern': r'^[\u4e00-\u9fa5a-zA-Z0-9()（）]{2,50}$',
        'message': '机构名称为2-50个字符'
    }

    # 选手姓名：2-20个字符
    PLAYER_NAME = {
        'pattern': r'^[\u4e00-\u9fa5a-zA-Z]{2,20}$',
        'message': '姓名为2-20个字符，仅允许中英文'
    }

    # 金额：正数，最多两位小数
    AMOUNT = {
        'pattern': r'^\d+(\.\d{1,2})?$',
        'message': '请输入有效的金额（最多两位小数）'
    }

    # 备注：最多500个字符
    NOTE = {
        'max_length': 500,
        'message': '备注不能超过500个字符'
    }


# 表单验证模式
class FormSchemas:
    """表单验证模式"""

    # 项目表单验证模式
    PROJECT = {
        'name': [
            {'type': 'required', 'field_name': '项目名称'},
            {'type': 'length', 'min': 1, 'max': 50, 'message': '项目名称为1-50个字符'}
        ],
        'type': [
            {'type': 'length', 'max': 20, 'message': '项目类型不能超过20个字符'}
        ],
        'status': [
            {'type': 'enum', 'values': ['筹备中', '进行中', '已结束', '已归档'], 'message': '请选择有效的状态'}
        ],
        'manager': [
            {'type': 'length', 'max': 20, 'message': '负责人姓名不能超过20个字符'}
        ],
        'startDate': [
            {'type': 'date'}
        ],
        'endDate': [
            {'type': 'date'}
        ],
        'description': [
            {'type': 'length', 'max': 500, 'message': '描述不能超过500个字符'}
        ]
    }

    # 机构表单验证模式
    ORGANIZATION = {
        'name': [
            {'type': 'required', 'field_name': '机构名称'},
            {'type': 'length', 'min': 2, 'max': 50, 'message': '机构名称为2-50个字符'}
        ],
        'type': [
            {'type': 'required', 'field_name': '机构类型'},
            {'type': 'enum', 'values': ['培训机构', '艺术团体', '设备供应商', '媒体合作', '场地提供', '其他']}
        ],
        'contact': [
            {'type': 'length', 'max': 20, 'message': '联系人姓名不能超过20个字符'}
        ],
        'phone': [
            {'type': 'phone', 'message': '请输入有效的手机号码'}
        ],
        'address': [
            {'type': 'length', 'max': 200, 'message': '地址不能超过200个字符'}
        ],
        'note': [
            {'type': 'length', 'max': 500, 'message': '备注不能超过500个字符'}
        ]
    }

    # 选手表单验证模式
    PLAYER = {
        'name': [
            {'type': 'required', 'field_name': '选手姓名'},
            {'type': 'length', 'min': 2, 'max': 20, 'message': '姓名为2-20个字符'}
        ],
        'gender': [
            {'type': 'enum', 'values': ['男', '女'], 'message': '请选择有效的性别'}
        ],
        'category': [
            {'type': 'enum', 'values': ['音乐', '舞蹈', '美术', '戏剧', '其他']}
        ],
        'phone': [
            {'type': 'phone', 'message': '请输入有效的手机号码'}
        ],
        'idCard': [
            {'type': 'id_card', 'message': '请输入有效的身份证号码'}
        ],
        'note': [
            {'type': 'length', 'max': 500, 'message': '备注不能超过500个字符'}
        ]
    }

    # 用户表单验证模式
    USER = {
        'username': [
            {'type': 'required', 'field_name': '用户名'},
            {'type': 'username'}
        ],
        'password': [
            {'type': 'required', 'field_name': '密码'},
            {'type': 'password'}
        ],
        'role': [
            {'type': 'enum', 'values': ['admin', 'editor', 'viewer']}
        ]
    }

    # 财务表单验证模式
    FINANCE = {
        'type': [
            {'type': 'required', 'field_name': '类型'},
            {'type': 'enum', 'values': ['收入', '支出']}
        ],
        'category': [
            {'type': 'required', 'field_name': '分类'},
            {'type': 'length', 'max': 20, 'message': '分类不能超过20个字符'}
        ],
        'title': [
            {'type': 'required', 'field_name': '摘要'},
            {'type': 'length', 'min': 1, 'max': 100, 'message': '摘要为1-100个字符'}
        ],
        'amount': [
            {'type': 'required', 'field_name': '金额'},
            {'type': 'range', 'min': 0, 'max': 999999999, 'message': '金额必须在有效范围内'}
        ],
        'date': [
            {'type': 'required', 'field_name': '日期'},
            {'type': 'date'}
        ],
        'note': [
            {'type': 'length', 'max': 500, 'message': '备注不能超过500个字符'}
        ]
    }
