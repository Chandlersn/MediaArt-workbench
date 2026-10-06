"""Read-only print checks on an already normalized template and certificate batch."""
import hashlib
import json
import math
import re


MAX_ISSUES = 200
MAX_VALUE_LENGTH = 500
MAX_FIELDS = 200
DEFAULT_FONT_PT = 12
_BRACKETS = (('（', '）'), ('(', ')'), ('【', '】'), ('[', ']'), ('{', '}'), ('<', '>'))
_PUNCTUATION = re.compile(r'^[\s\-—–_/\\.，。、;；:：?？!！*·~^°|｜…]+$')


def value_text(value):
    return '' if value is None else str(value)


def is_empty(value):
    return not value_text(value).strip()


def is_placeholder(value):
    text = value_text(value).strip()
    if not text:
        return False
    return bool(_PUNCTUATION.fullmatch(text)) or any(
        text.startswith(left) and text.endswith(right) and len(text) > 2
        for left, right in _BRACKETS
    )


def number(value):
    if isinstance(value, bool) or value is None or value == '':
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def estimate_width_mm(value, font_size):
    em = sum(1 if ord(char) > 255 else 0.55 for char in value_text(value))
    return em * font_size * 25.4 / 72


def available_width_mm(field, page_width):
    x = number(field.get('x', 0))
    align = field.get('align') or 'center'
    percent = min(x, 100 - x) * 2 if align == 'center' else (x if align == 'right' else 100 - x)
    return page_width * max(0, percent) / 100


def validation_token(template, records):
    content = json.dumps({'version': 1, 'template': template, 'records': records},
                         ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def inspect_batch(template, records, known_columns, page_sizes):
    issues = []
    issue_count = 0
    can_generate = True

    def add(kind, column, label, severity, message, record=None, value=None):
        nonlocal issue_count, can_generate
        issue_count += 1
        if severity == 'error':
            can_generate = False
        if len(issues) >= MAX_ISSUES:
            return
        issues.append({
            'kind': kind, 'column': column, 'label': value_text(label)[:200],
            'severity': severity, 'message': message,
            'reference': ({'certNumber': record.get('certNumber', ''),
                           'sessionId': record.get('sessionId') or ''} if record is not None else None),
            'playerName': value_text((record or {}).get('playerName'))[:200],
            'value': value_text(value)[:MAX_VALUE_LENGTH],
        })

    page_id = template.get('pageSize') or 'A4_L'
    spec = page_sizes.get(page_id) if isinstance(page_id, str) else None
    if spec is None:
        add('layout', '', '纸张', 'error', '模板纸张规格无效，请修改模板')
    if not isinstance(template.get('background'), str) or not template['background'].strip():
        add('layout', '', '底图', 'error', '模板没有底图，请先上传底图')
    fields = template.get('fields')
    if not isinstance(fields, list) or not fields:
        add('layout', '', '打印字段', 'error', '模板没有有效的打印字段，请修改模板')
        fields = []
    elif len(fields) > MAX_FIELDS:
        add('layout', '', '打印字段', 'error', f'模板打印字段不能超过 {MAX_FIELDS} 个')
        fields = []

    # Template errors precede record warnings so actionable blockers remain visible.
    valid_fields = []
    for field in fields:
        if not isinstance(field, dict):
            add('layout', '', '打印字段', 'error', '模板字段格式无效，请修改模板')
            continue
        column = field.get('column') or ''
        label = field.get('label') or column or '未命名字段'
        if column not in known_columns:
            add('missing-field', column, label, 'error', '字段不存在于证书数据中，请修改模板')
            continue
        x, y = number(field.get('x', 0)), number(field.get('y', 0))
        size = number(field.get('fontSize', DEFAULT_FONT_PT))
        align = field.get('align') or 'center'
        bad = (x is None or y is None or not 0 <= x <= 100 or not 0 <= y < 100
               or size is None or not 1 <= size <= 500 or align not in ('left', 'center', 'right'))
        if not bad:
            bad = ((align == 'center' and x in (0, 100))
                   or (align == 'left' and x == 100) or (align == 'right' and x == 0))
        if bad:
            add('layout', column, label, 'error', '字段位置、对齐或字号无效，可能超出纸面，请修改模板')
            continue
        valid_fields.append((field, column, label, size))

    for field, column, label, size in valid_fields:
        for record in records:
            value = record.get(column)
            if is_empty(value):
                add('empty', column, label, 'warning', '此字段尚未填写，打印时将留空', record, value)
            elif is_placeholder(value):
                add('placeholder', column, label, 'warning', '此字段疑似占位内容，请核对后再打印', record, value)
            elif spec and estimate_width_mm(value, size) > available_width_mm(field, spec['width_mm']):
                add('overlong', column, label, 'warning',
                    '按字号估算文字可能超出纸面，请缩短内容或调整模板后核对预览', record, value)

    return {
        'success': True, 'itemCount': len(records), 'issueCount': issue_count,
        'issues': issues, 'canGenerate': can_generate,
        'validationToken': validation_token(template, records),
        'truncated': issue_count > len(issues),
    }


def empty_warnings(template, records):
    warnings = []
    for field in template.get('fields') or []:
        column = field.get('column')
        count = sum(is_empty(record.get(column)) for record in records)
        if count:
            warnings.append({'column': column, 'label': field.get('label') or column, 'count': count})
    return warnings
