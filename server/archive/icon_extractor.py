"""
Windows system file icon extractor module.
Extracts native file type icons using Windows Shell API with high quality.
"""

from __future__ import annotations  # 允许在 Pillow 缺失（Image=None）时仍能定义带注解的函数

import ctypes
import ctypes.wintypes
import io
import logging
import platform
import threading
from typing import Optional, Tuple

try:
    from PIL import Image, ImageEnhance, ImageFilter
    _PIL_AVAILABLE = True
except Exception:  # Pillow 缺失时降级：图标功能不可用，但绝不能拖垮整个 archive 模块
    Image = ImageEnhance = ImageFilter = None  # type: ignore
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_SMALLICON = 0x000000001
SHGFI_USEFILEATTRIBUTES = 0x000000010
DI_NORMAL = 0x0003


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ('hIcon', ctypes.wintypes.HICON),
        ('iIcon', ctypes.c_int),
        ('dwAttributes', ctypes.wintypes.DWORD),
        ('szDisplayName', ctypes.c_wchar * 260),
        ('szTypeName', ctypes.c_wchar * 80),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', ctypes.wintypes.DWORD),
        ('biWidth', ctypes.wintypes.LONG),
        ('biHeight', ctypes.wintypes.LONG),
        ('biPlanes', ctypes.wintypes.WORD),
        ('biBitCount', ctypes.wintypes.WORD),
        ('biCompression', ctypes.wintypes.DWORD),
        ('biSizeImage', ctypes.wintypes.DWORD),
        ('biXPelsPerMeter', ctypes.wintypes.LONG),
        ('biYPelsPerMeter', ctypes.wintypes.LONG),
        ('biClrUsed', ctypes.wintypes.DWORD),
        ('biClrImportant', ctypes.wintypes.DWORD),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.wintypes.LONG),
        ('top', ctypes.wintypes.LONG),
        ('right', ctypes.wintypes.LONG),
        ('bottom', ctypes.wintypes.LONG),
    ]


_icon_cache = {}
_cache_lock = threading.Lock()


def _get_system_dpi() -> int:
    try:
        hdc = user32.GetDC(0)
        dpi = gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(0, hdc)
        return dpi
    except:
        return 96


def _get_best_icon_size() -> int:
    try:
        dpi = _get_system_dpi()
        if dpi >= 192:
            return 64
        elif dpi >= 144:
            return 48
        elif dpi >= 120:
            return 40
        else:
            return 32
    except:
        return 32


def _aggressive_clean_black_artifacts(img: Image.Image) -> Image.Image:
    pixels = img.load()
    width, height = img.size
    
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            
            if a < 15:
                continue
            
            brightness = (r + g + b) / 3
            
            is_dark = brightness < 50 and r < 60 and g < 60 and b < 60
            
            if is_dark:
                transparent_or_dark_neighbors = 0
                
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            nr, ng, nb, na = pixels[nx, ny]
                            
                            is_neighbor_transparent = na < 100
                            is_neighbor_dark = (na >= 100 and 
                                              (nr + ng + nb) / 3 < 80 and 
                                              nr < 90 and ng < 90 and nb < 90)
                            
                            if is_neighbor_transparent or is_neighbor_dark:
                                transparent_or_dark_neighbors += 1
                
                if transparent_or_dark_neighbors >= 3:
                    pixels[x, y] = (r, g, b, 0)
                elif transparent_or_dark_neighbors >= 1:
                    pixels[x, y] = (r, g, b, max(0, a - 150))
    
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            
            if a > 50 and a < 200:
                brightness = (r + g + b) / 3
                
                if brightness < 40:
                    pixels[x, y] = (r, g, b, max(0, int(a * 0.1)))
    
    return img


def _enhance_image_quality(img: Image.Image, target_size: int) -> Image.Image:
    original_size = img.size[0]
    
    if original_size < target_size:
        intermediate_size = min(int(original_size * 2), target_size)
        img = img.resize((intermediate_size, intermediate_size), Image.Resampling.LANCZOS)
        
        if intermediate_size < target_size:
            img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    elif original_size > target_size:
        img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    img = _aggressive_clean_black_artifacts(img)
    
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.2)
    
    return img


def _extract_icon_to_png(hIcon, size: int = 48) -> Optional[bytes]:
    try:
        best_size = _get_best_icon_size()
        
        hdc = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = best_size
        bmi.biHeight = -best_size
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0
        bmi.biSizeImage = best_size * best_size * 4

        hbm = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, None, None, 0)
        old_bmp = gdi32.SelectObject(hdc_mem, hbm)

        brush = gdi32.CreateSolidBrush(0x00000000)
        rect = RECT(0, 0, best_size, best_size)
        user32.FillRect(hdc_mem, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)

        user32.DrawIconEx(hdc_mem, 0, 0, hIcon, best_size, best_size, 0, 0, DI_NORMAL)

        pixel_count = best_size * best_size
        pixels = (ctypes.c_uint32 * pixel_count)()
        gdi32.GetDIBits(hdc_mem, hbm, 0, best_size, pixels, ctypes.byref(bmi), 0)

        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc)

        rgba = bytearray(pixel_count * 4)
        for i in range(pixel_count):
            v = pixels[i]
            r = (v >> 16) & 0xFF
            g = (v >> 8) & 0xFF
            b = v & 0xFF
            a = (v >> 24) & 0xFF
            
            if a > 0 and a < 255:
                brightness = (r + g + b) / 3
                
                if brightness < 45 and r < 55 and g < 55 and b < 55:
                    a = max(0, int(a * 0.15))
            
            rgba[i * 4] = r
            rgba[i * 4 + 1] = g
            rgba[i * 4 + 2] = b
            rgba[i * 4 + 3] = a

        img = Image.frombytes('RGBA', (best_size, best_size), bytes(rgba))
        img = _enhance_image_quality(img, size)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()
        
    except Exception as e:
        logger.error(f"Error extracting icon to PNG: {e}")
        return None


def get_file_icon(ext: str, size: int = 48) -> Optional[bytes]:
    if platform.system() != 'Windows' or not _PIL_AVAILABLE:
        return None

    ext = ext.lstrip('.').lower()
    cache_key = f"{ext}_{size}"

    with _cache_lock:
        if cache_key in _icon_cache:
            return _icon_cache[cache_key]

    sfi = SHFILEINFO()
    flags = SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES
    result = shell32.SHGetFileInfoW(
        f'.{ext}', 0, ctypes.byref(sfi), ctypes.sizeof(sfi), flags
    )

    if not result or not sfi.hIcon:
        logger.warning(f"Failed to get icon for extension: .{ext}")
        return None

    try:
        png_data = _extract_icon_to_png(sfi.hIcon, size)
        
        if png_data:
            with _cache_lock:
                _icon_cache[cache_key] = png_data
        
        return png_data
    finally:
        user32.DestroyIcon(sfi.hIcon)


def get_folder_icon(size: int = 48) -> Optional[bytes]:
    if platform.system() != 'Windows' or not _PIL_AVAILABLE:
        return None

    cache_key = f"__folder__{size}"

    with _cache_lock:
        if cache_key in _icon_cache:
            return _icon_cache[cache_key]

    sfi = SHFILEINFO()
    flags = SHGFI_ICON | SHGFI_LARGEICON
    result = shell32.SHGetFileInfoW(
        'C:\\Windows', 0, ctypes.byref(sfi), ctypes.sizeof(sfi), flags
    )

    if not result or not sfi.hIcon:
        logger.warning("Failed to get folder icon")
        return None

    try:
        png_data = _extract_icon_to_png(sfi.hIcon, size)
        
        if png_data:
            with _cache_lock:
                _icon_cache[cache_key] = png_data
        
        return png_data
    finally:
        user32.DestroyIcon(sfi.hIcon)
