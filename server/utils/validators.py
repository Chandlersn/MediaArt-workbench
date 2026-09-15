"""字段校验（电话 / 身份证号）。

⚠️ 规则需与前端 `src/utils/formValidator.js` 保持一致：
前端负责即时提示，后端负责兜底（API 直连、批量导入都要挡住脏数据）。
"""

import re
from datetime import datetime

# 电话允许的分隔符：空格、横线、中英文括号（如 136-1111-0014 / 010-8888 6666）
_PHONE_SEP = re.compile(r'[\s\-()（）]')
_MOBILE = re.compile(r'^1[3-9]\d{9}$')      # 手机号
_LANDLINE = re.compile(r'^0\d{9,11}$')      # 座机（区号 + 号码，共 10~12 位）
_SERVICE = re.compile(r'^[48]00\d{7}$')     # 400 / 800 服务号

# 身份证 18 位校验（GB 11643-1999）
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = '10X98765432'


def normalize_phone(value) -> str:
    """去掉分隔符，便于校验与比对。"""
    return _PHONE_SEP.sub('', str(value or '')).strip()


def validate_phone(value):
    """校验电话。合法或为空 → None；否则返回错误文案。"""
    raw = str(value or '').strip()
    if not raw:
        return None
    n = normalize_phone(raw)
    if _MOBILE.match(n) or _LANDLINE.match(n) or _SERVICE.match(n):
        return None
    return '电话格式不正确（手机号 11 位，或座机含区号，如 010-88886666）'


def validate_id_card(value):
    """校验 18 位身份证号（格式 + 出生日期 + 校验位）。合法或为空 → None。"""
    v = str(value or '').strip().upper()
    if not v:
        return None
    if not re.match(r'^\d{17}[\dX]$', v):
        return '身份证号应为 18 位（末位可为 X）'
    try:
        birth = datetime.strptime(v[6:14], '%Y%m%d')
    except ValueError:
        return '身份证号中的出生日期无效'
    if birth.year < 1900 or birth > datetime.now():
        return '身份证号中的出生日期无效'
    total = sum(int(v[i]) * _ID_WEIGHTS[i] for i in range(17))
    if _ID_CHECK[total % 11] != v[17]:
        return '身份证号校验位不正确'
    return None


def validate_person_fields(data) -> str:
    """校验 data 中出现的 phone / idCard（未出现的字段跳过，便于局部更新）。

    返回第一条错误信息；全部通过返回 ''。
    """
    data = data or {}
    if 'phone' in data:
        err = validate_phone(data.get('phone'))
        if err:
            return err
    if 'idCard' in data:
        err = validate_id_card(data.get('idCard'))
        if err:
            return err
    return ''
