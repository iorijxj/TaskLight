"""Win32 分层窗口绘制。

tkinter 的 Canvas 画 RGBA 图时，透明像素显示的是 Canvas 底色而非桌面 ——
要让透明真正穿透，只能走 WS_EX_LAYERED + UpdateLayeredWindow，它按逐像素
alpha 与桌面混合，抗锯齿边缘也能正确过渡。

窗口位置与尺寸仍由 tkinter 的 geometry 管，这里只负责把像素贴上去。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image, ImageChops

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
BI_RGB = 0
DIB_RGB_COLORS = 0
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x02


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


def _declare_signatures() -> None:
    """显式声明句柄类型。

    ctypes 默认按 c_int（32 位）收发，而 64 位 Windows 的句柄是 64 位指针。
    必须成套声明 —— 只给一半函数加 restype，另一半仍按 32 位收参数，会直接
    抛 OverflowError，比不加更糟。
    """
    point_p = ctypes.POINTER(wintypes.POINT)
    _user32.GetParent.restype = wintypes.HWND
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetWindowLongW.restype = wintypes.LONG
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongW.restype = wintypes.LONG
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    _user32.GetDC.restype = wintypes.HDC
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.UpdateLayeredWindow.restype = wintypes.BOOL
    _user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND,
        wintypes.HDC,
        point_p,
        ctypes.POINTER(wintypes.SIZE),
        wintypes.HDC,
        point_p,
        wintypes.COLORREF,
        ctypes.POINTER(_BLENDFUNCTION),
        wintypes.DWORD,
    ]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    _gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BITMAPINFO),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]


_declare_signatures()


def resolve_hwnd(widget_id: int) -> int:
    """tkinter 的 winfo_id 在有窗口装饰时返回子窗口，取其顶层父窗口。"""
    parent = _user32.GetParent(widget_id)
    return parent or widget_id


def enable(hwnd: int) -> None:
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)


def _premultiplied_bgra(image: Image.Image) -> bytes:
    """UpdateLayeredWindow 要求预乘 alpha 的 BGRA。

    ImageChops.multiply 的语义正是 a*b/255，即预乘，且是 C 实现 —— 纯 Python
    逐像素算 96 万次会明显卡顿。通道按 B,G,R,A 顺序合并即得 Windows 要的字节序。
    """
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    return Image.merge(
        "RGBA",
        (
            ImageChops.multiply(blue, alpha),
            ImageChops.multiply(green, alpha),
            ImageChops.multiply(red, alpha),
            alpha,
        ),
    ).tobytes()


def paint(hwnd: int, image: Image.Image) -> bool:
    """把整张 RGBA 图贴到分层窗口上。失败返回 False，调用方可降级处理。"""
    try:
        return _paint(hwnd, image)
    except OSError:
        return False


def _paint(hwnd: int, image: Image.Image) -> bool:
    user32, gdi32 = _user32, _gdi32
    width, height = image.size
    data = _premultiplied_bgra(image)

    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    header = _BITMAPINFOHEADER(
        ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, BI_RGB, 0, 0, 0, 0, 0
    )
    info = _BITMAPINFO(header, (wintypes.DWORD * 3)())
    pixels = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(
        screen_dc, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(pixels), None, 0
    )
    try:
        if not bitmap:
            return False
        ctypes.memmove(pixels, data, len(data))
        old = gdi32.SelectObject(mem_dc, bitmap)
        size = wintypes.SIZE(width, height)
        source = wintypes.POINT(0, 0)
        blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(
            hwnd,
            screen_dc,
            None,
            ctypes.byref(size),
            mem_dc,
            ctypes.byref(source),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )
        gdi32.SelectObject(mem_dc, old)
        return bool(ok)
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
