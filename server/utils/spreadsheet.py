"""电子表格解析 → 二维文本（供文件预览渲染成表格）。

**纯标准库、零第三方依赖**，支持三类真实格式（按内容判定，不只看扩展名）：

1. ``xlsx`` / ``xlsm`` —— OOXML（zip + XML）
2. ``xls`` —— OLE2 复合文档 + BIFF 记录流（Excel 97-2003 旧版二进制）
3. HTML / XML 表格 —— 大量「导出为 xls」的文件其实是这种

设计取舍：定位是**预览**，不是完整电子表格引擎。因此只取**首个工作表**、
只读单元格的「显示值」，不解析样式/公式结果/日期序列号（日期会显示为数字），
并对行/列/单元格长度设上限。
"""

import io
import re
import struct
import zipfile
from typing import Any, Dict, List, Optional, Tuple

MAX_ROWS = 300
MAX_COLS = 60
MAX_CELL_CHARS = 500


# ============================================================
# 公共入口
# ============================================================

def spreadsheet_rows(data: bytes, max_rows: int = MAX_ROWS,
                     max_cols: int = MAX_COLS
                     ) -> Tuple[str, str, List[List[str]], bool]:
    """解析表格，返回 ``(格式, 工作表名, 行, 是否截断)``。

    按内容嗅探真实格式——同名不同实的文件很常见（.xls 改名成 .xlsx、
    「导出为 xls」其实是 HTML 表格等）。识别不出则返回 ``('', '', [], False)``。
    """
    # 1) zip → OOXML
    if data[:2] == b'PK':
        try:
            name, rows, trunc = xlsx_rows(data, max_rows, max_cols)
            if rows:
                return 'xlsx', name, rows, trunc
        except Exception:
            pass
    # 2) OLE2 → 旧版 xls（BIFF）
    if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        try:
            rows, trunc = xls_rows(data, max_rows, max_cols)
            if rows:
                return 'xls', '', rows, trunc
        except Exception:
            pass
    # 3) HTML / XML 表格
    if _looks_like_markup(data):
        try:
            rows, trunc = markup_table_rows(data, max_rows, max_cols)
            if rows:
                return 'html', '', rows, trunc
        except Exception:
            pass
    return '', '', [], False


# ============================================================
# 一、xlsx / xlsm（OOXML）
# ============================================================

def xlsx_rows(data: bytes, max_rows: int = MAX_ROWS, max_cols: int = MAX_COLS
              ) -> Tuple[str, List[List[str]], bool]:
    """解析 .xlsx / .xlsm 的**首个工作表**，返回 (工作表名, 二维文本, 是否截断)。

    相关部件：
      - xl/sharedStrings.xml      共享字符串表（t="s" 的单元格按索引引用它）
      - xl/workbook.xml           工作表名与顺序
      - xl/worksheets/sheetN.xml  单元格数据
    """
    import html as _html
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()

        shared: List[str] = []
        if 'xl/sharedStrings.xml' in names:
            sx = z.read('xl/sharedStrings.xml').decode('utf-8', 'ignore')
            for si in re.findall(r'<si>(.*?)</si>', sx, re.S):
                shared.append(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S)))

        sheet_name = ''
        if 'xl/workbook.xml' in names:
            wb = z.read('xl/workbook.xml').decode('utf-8', 'ignore')
            m = re.search(r'<sheet[^>]*name="([^"]*)"', wb)
            if m:
                sheet_name = _html.unescape(m.group(1))

        sheet_files = sorted(n for n in names
                             if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
        if not sheet_files:
            return sheet_name, [], False

        sx = z.read(sheet_files[0]).decode('utf-8', 'ignore')
        rows: List[List[str]] = []
        truncated = False
        for row_xml in re.findall(r'<row\b[^>]*>(.*?)</row>', sx, re.S):
            if len(rows) >= max_rows:
                truncated = True
                break
            cells: Dict[int, str] = {}
            for attrs, body in re.findall(r'<c\b([^>]*)>(.*?)</c>', row_xml, re.S):
                ref = re.search(r'r="([A-Z]+)\d+"', attrs)
                if not ref:
                    continue
                col = 0
                for ch in ref.group(1):          # A->0, B->1, ... AA->26
                    col = col * 26 + (ord(ch) - 64)
                col -= 1
                if col >= max_cols:
                    continue
                mt = re.search(r't="([^"]+)"', attrs)
                ttype = mt.group(1) if mt else ''
                if ttype == 'inlineStr':
                    val = ''.join(re.findall(r'<t[^>]*>(.*?)</t>', body, re.S))
                else:
                    mv = re.search(r'<v[^>]*>(.*?)</v>', body, re.S)
                    val = mv.group(1) if mv else ''
                    if ttype == 's' and val != '':
                        try:
                            val = shared[int(val)]
                        except (ValueError, IndexError):
                            pass
                cells[col] = _html.unescape(val)[:MAX_CELL_CHARS]
            if cells:                            # 跳过完全空白的行
                rows.append([cells.get(i, '') for i in range(max(cells) + 1)])
        return sheet_name, rows, truncated


# ============================================================
# 二、xls（OLE2 复合文档 + BIFF 记录流）
# ============================================================

_OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF


def _ole_streams(data: bytes) -> Optional[Dict[str, bytes]]:
    """解析 OLE2 复合文档，返回 ``{流名: 流数据}``；非 OLE2 返回 None。

    只实现预览所需的最小子集：头部 → DIFAT/FAT → 目录项 → 流数据
    （小于 mini 阈值的流走迷你 FAT + 根条目的迷你流）。
    """
    if len(data) < 512 or data[:8] != _OLE_MAGIC:
        return None
    ssz = 1 << struct.unpack_from('<H', data, 30)[0]      # 扇区大小（通常 512）
    mssz = 1 << struct.unpack_from('<H', data, 32)[0]     # 迷你扇区大小（通常 64）
    n_fat = struct.unpack_from('<I', data, 44)[0]
    dir_start = struct.unpack_from('<I', data, 48)[0]
    mini_cutoff = struct.unpack_from('<I', data, 56)[0]
    minifat_start = struct.unpack_from('<I', data, 60)[0]
    difat_start = struct.unpack_from('<I', data, 68)[0]

    def sector(i: int) -> bytes:
        off = 512 + i * ssz
        return data[off:off + ssz]

    # ---- DIFAT：前 109 项在头部，其余在 DIFAT 扇区链里 ----
    fat_sectors: List[int] = []
    for i in range(109):
        s = struct.unpack_from('<I', data, 76 + 4 * i)[0]
        if s < _ENDOFCHAIN:
            fat_sectors.append(s)
    nxt, guard = difat_start, 0
    while nxt < _ENDOFCHAIN and guard < 4096:
        sec = sector(nxt)
        per = ssz // 4 - 1
        for i in range(per):
            s = struct.unpack_from('<I', sec, 4 * i)[0]
            if s < _ENDOFCHAIN:
                fat_sectors.append(s)
        nxt = struct.unpack_from('<I', sec, ssz - 4)[0]
        guard += 1
    if n_fat:
        fat_sectors = fat_sectors[:n_fat]

    # ---- FAT ----
    FAT: List[int] = []
    for fs in fat_sectors:
        sec = sector(fs)
        FAT.extend(struct.unpack_from('<I', sec, 4 * i)[0] for i in range(ssz // 4))

    def chain(start: int) -> List[int]:
        out: List[int] = []
        cur, guard = start, 0
        seen = set()
        while cur < _ENDOFCHAIN and guard < 1000000 and cur not in seen:
            seen.add(cur)
            out.append(cur)
            if cur >= len(FAT):
                break
            cur = FAT[cur]
            guard += 1
        return out

    def read_chain(start: int, size: Optional[int] = None) -> bytes:
        buf = b''.join(sector(i) for i in chain(start))
        return buf[:size] if size is not None else buf

    # ---- 目录项 ----
    dirdata = read_chain(dir_start)
    entries: List[Dict[str, Any]] = []
    for off in range(0, max(0, len(dirdata) - 127), 128):
        e = dirdata[off:off + 128]
        nlen = struct.unpack_from('<H', e, 64)[0]
        if nlen < 2:
            continue
        name = e[:nlen - 2].decode('utf-16-le', 'ignore')
        entries.append({
            'name': name,
            'type': e[66],
            'start': struct.unpack_from('<I', e, 116)[0],
            'size': struct.unpack_from('<Q', e, 120)[0],
        })

    root = next((e for e in entries if e['type'] == 5), None)

    # ---- 迷你 FAT + 迷你流（根条目持有） ----
    miniFAT: List[int] = []
    if minifat_start < _ENDOFCHAIN:
        mf = read_chain(minifat_start)
        miniFAT = list(struct.unpack_from('<I', mf, 4 * i)[0]
                       for i in range(len(mf) // 4))
    ministream = read_chain(root['start'], root['size']) if root else b''

    def read_stream(e: Dict[str, Any]) -> bytes:
        size = int(e['size'])
        if size < mini_cutoff:                      # 走迷你流
            out = bytearray()
            cur, guard = e['start'], 0
            while cur < _ENDOFCHAIN and guard < 1000000:
                off = cur * mssz
                out += ministream[off:off + mssz]
                if cur >= len(miniFAT):
                    break
                cur = miniFAT[cur]
                guard += 1
            return bytes(out[:size])
        return read_chain(e['start'], size)

    streams: Dict[str, bytes] = {}
    for e in entries:
        if e['type'] == 2:                          # 2 = stream
            try:
                streams[e['name']] = read_stream(e)
            except Exception:
                continue
    return streams


def _rk_to_float(rk: int) -> float:
    """BIFF 的 RK 编码 → 浮点数（bit1 整数标志 / bit0 除以 100 标志）。"""
    if rk & 0x02:
        val = rk >> 2
        if val & 0x20000000:                        # 30 位有符号
            val -= 0x40000000
        num = float(val)
    else:
        num = struct.unpack('<d', struct.pack('<Q', (rk & 0xFFFFFFFC) << 32))[0]
    if rk & 0x01:
        num /= 100.0
    return num


def _fmt_num(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f'{v:.6g}'


def _parse_sst(buf: bytes) -> List[str]:
    """解析 SST（共享字符串表）记录体。

    调用方应已把紧随其后的 CONTINUE 记录拼进来（否则长字符串会缺失）。
    字符串可能被 CONTINUE 从中间截断（标准另有处理），此处按拼接结果解析，
    属预览可接受的近似。
    """
    if len(buf) < 8:
        return []
    _total, unique = struct.unpack_from('<II', buf, 0)
    off, n = 8, len(buf)
    out: List[str] = []
    while off + 3 <= n and len(out) < unique:
        cch = struct.unpack_from('<H', buf, off)[0]
        off += 2
        flags = buf[off]
        off += 1
        rich, ext, wide = flags & 0x08, flags & 0x04, flags & 0x01
        nrun = cbext = 0
        if rich:
            if off + 2 > n:
                break
            nrun = struct.unpack_from('<H', buf, off)[0]
            off += 2
        if ext:
            if off + 4 > n:
                break
            cbext = struct.unpack_from('<I', buf, off)[0]
            off += 4
        need = cch * 2 if wide else cch
        if off + need > n:
            break
        raw = buf[off:off + need]
        off += need
        out.append(raw.decode('utf-16-le' if wide else 'latin-1', 'ignore'))
        off += nrun * 4 + cbext
    return out


def xls_rows(data: bytes, max_rows: int = MAX_ROWS, max_cols: int = MAX_COLS
             ) -> Tuple[List[List[str]], bool]:
    """解析旧版 .xls（BIFF8）的单元格，返回 (二维文本, 是否截断)。

    支持 LABELSST / LABEL / NUMBER / RK / MULRK / BOOLERR 这几类最常见的单元格记录，
    足以覆盖普通表格；公式的计算结果缓存、样式、日期序列号不在预览范围内。
    """
    streams = _ole_streams(data) or {}
    wb = streams.get('Workbook') or streams.get('Book')
    if not wb:                                      # 流名异常时，取最像 BIFF 的流
        cands = [v for v in streams.values()
                 if v[:2] in (b'\x09\x08', b'\x09\x04', b'\x08\x09')]
        wb = max(cands, key=len) if cands else b''
    if not wb:
        return [], False

    sst: List[str] = []
    cells: Dict[Tuple[int, int], str] = {}
    off, n = 0, len(wb)
    while off + 4 <= n:
        rec, ln = struct.unpack_from('<HH', wb, off)
        body = wb[off + 4:off + 4 + ln]
        nxt = off + 4 + ln

        if rec == 0x00FC:                           # SST：拼接后续 CONTINUE
            buf = bytearray(body)
            o = nxt
            while o + 4 <= n:
                r2, l2 = struct.unpack_from('<HH', wb, o)
                if r2 != 0x003C:                    # CONTINUE
                    break
                buf += wb[o + 4:o + 4 + l2]
                o += 4 + l2
            sst = _parse_sst(bytes(buf))
            off = o
            continue

        if rec == 0x00FD and len(body) >= 10:       # LABELSST → 引用 SST
            r, c, _xf, isst = struct.unpack_from('<HHHI', body, 0)
            if 0 <= isst < len(sst):
                cells[(r, c)] = sst[isst]
        elif rec == 0x0204 and len(body) >= 9:      # LABEL → 内联字符串
            r, c = struct.unpack_from('<HH', body, 0)
            cch = struct.unpack_from('<H', body, 6)[0]
            flags = body[8]
            raw = body[9:9 + (cch * 2 if flags & 0x01 else cch)]
            cells[(r, c)] = raw.decode('utf-16-le' if flags & 0x01 else 'latin-1', 'ignore')
        elif rec == 0x0203 and len(body) >= 14:     # NUMBER → IEEE double
            r, c = struct.unpack_from('<HH', body, 0)
            cells[(r, c)] = _fmt_num(struct.unpack_from('<d', body, 6)[0])
        elif rec == 0x027E and len(body) >= 10:     # RK
            r, c = struct.unpack_from('<HH', body, 0)
            cells[(r, c)] = _fmt_num(_rk_to_float(struct.unpack_from('<I', body, 6)[0]))
        elif rec == 0x00BD and len(body) >= 6:      # MULRK → 一行多列
            r, c0 = struct.unpack_from('<HH', body, 0)
            for i in range(max(0, (len(body) - 6) // 6)):
                rk = struct.unpack_from('<I', body, 4 + i * 6 + 2)[0]
                cells[(r, c0 + i)] = _fmt_num(_rk_to_float(rk))
        elif rec == 0x0205 and len(body) >= 8:      # BOOLERR
            r, c = struct.unpack_from('<HH', body, 0)
            val = body[6]
            cells[(r, c)] = ('TRUE' if val else 'FALSE') if body[7] == 0 else '#ERR'
        off = nxt

    if not cells:
        return [], False

    row_idx = sorted({r for (r, _c) in cells})
    truncated = len(row_idx) > max_rows
    rows: List[List[str]] = []
    for r in row_idx[:max_rows]:
        cols = [c for (rr, c) in cells if rr == r]
        width = min(max(cols) + 1, max_cols)
        rows.append([cells.get((r, c), '')[:MAX_CELL_CHARS] for c in range(width)])
    return rows, truncated


# ============================================================
# 三、HTML / XML 表格（大量「导出为 xls」其实长这样）
# ============================================================

def _looks_like_markup(data: bytes) -> bool:
    head = data[:4096].lstrip(b'\xef\xbb\xbf \t\r\n').lower()
    return head.startswith(b'<') and (b'<table' in head or b'<html' in head)


def markup_table_rows(data: bytes, max_rows: int = MAX_ROWS, max_cols: int = MAX_COLS
                      ) -> Tuple[List[List[str]], bool]:
    """从 HTML/XML 里取第一张表的行（按 <tr>/<td> 粗解析）。"""
    import html as _html
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'big5', 'latin-1'):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return [], False
    m = re.search(r'<table\b.*?</table>', text, re.S | re.I)
    if not m:
        return [], False
    rows: List[List[str]] = []
    truncated = False
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', m.group(0), re.S | re.I):
        if len(rows) >= max_rows:
            truncated = True
            break
        cells = []
        for td in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr, re.S | re.I):
            val = re.sub(r'<[^>]+>', '', td)
            cells.append(_html.unescape(val).strip().replace('\xa0', ' ')[:MAX_CELL_CHARS])
            if len(cells) >= max_cols:
                break
        if any(c for c in cells):
            rows.append(cells)
    return rows, truncated
