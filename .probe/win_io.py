# -*- coding: utf-8 -*-
"""Windows 窗口输入/截图底层工具库。

用于驱动微信这类「无 UIA 控件树」的自绘程序：靠窗口定位 + 固定坐标 + 键鼠注入 + 截图校验。

主要能力：
  find_window(title)          按标题找顶层窗口
  list_windows(keyword)       列出匹配窗口
  set_foreground(hwnd)        置前并激活
  window_rect(hwnd)           窗口位置尺寸
  move_window(hwnd,x,y,w,h)   规范化窗口位置（让坐标可预测）
  click(x, y)                 绝对坐标左键单击
  click_in_window(hwnd,rx,ry) 窗口内相对坐标单击
  paste_text(text)            经剪贴板粘贴文本（中文最可靠）
  send_keys(vk_list)          发送按键
  screenshot_window(hwnd)     截取窗口位图 -> PIL.Image
  screenshot_region(x,y,w,h)  截取屏幕区域 -> PIL.Image
"""
import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetProcessDPIAware()

# ---------------- 关键：64 位句柄/指针必须声明返回类型，否则会被截断成 int32 ----------------
DWORD = wt.DWORD
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
gdi32 = ctypes.windll.gdi32

user32.FindWindowW.restype = wt.HWND
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.GetForegroundWindow.restype = wt.HWND
user32.OpenClipboard.argtypes = [wt.HWND]
user32.OpenClipboard.restype = wt.BOOL
user32.GetClipboardData.restype = wt.HANDLE
user32.GetClipboardData.argtypes = [wt.UINT]
user32.SetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetFocus.argtypes = [wt.HWND]
user32.AttachThreadInput.argtypes = [DWORD, DWORD, wt.BOOL]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(DWORD)]
user32.GetWindowThreadProcessId.restype = DWORD
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
kernel32.GetCurrentThreadId.restype = DWORD

gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, DWORD]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]

# ---------------- 输入结构 ----------------
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
DWORD = wt.DWORD


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", DWORD), ("dwFlags", DWORD), ("time", DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", INPUT_UNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_VIRTUALDESK = 0x4000

VK = {
    "CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "ENTER": 0x0D, "TAB": 0x09,
    "ESC": 0x1B, "BACK": 0x08, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "A": 0x41, "C": 0x43, "V": 0x56, "X": 0x58, "F": 0x46, "Z": 0x5A,
}


def _send(*inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    return user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))


def _mouse(flags, dx=0, dy=0):
    mi = MOUSEINPUT(int(dx), int(dy), 0, flags, 0, 0)
    return INPUT(INPUT_MOUSE, INPUT_UNION(mi=mi))


def _key(vk, up=False):
    ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki))


def _uni(ch, up=False):
    ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, 0)
    return INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki))


# ---------------- 窗口 ----------------
def list_windows(keyword=None, visible_only=False):
    out = []
    CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, lp):
        if visible_only and not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(h, b, n + 2)
        title = b.value
        if keyword and keyword not in title:
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        pid = DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        out.append({"hwnd": h, "title": title, "cls": cls.value,
                    "pid": pid.value, "visible": bool(user32.IsWindowVisible(h))})
        return True

    user32.EnumWindows(CB(cb), 0)
    return out


def find_window(title, exact=True):
    if exact:
        h = user32.FindWindowW(None, title)
        return h or None
    wins = list_windows(title)
    return wins[0]["hwnd"] if wins else None


def window_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def client_rect(hwnd):
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


SW_RESTORE = 9


def set_foreground(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    # 附加线程输入，绕过前台锁定限制
    fg = user32.GetForegroundWindow()
    cur = kernel32.GetCurrentThreadId()
    t_fg = user32.GetWindowThreadProcessId(fg, None)
    t_tg = user32.GetWindowThreadProcessId(hwnd, None)
    if t_fg:
        user32.AttachThreadInput(cur, t_fg, True)
    if t_tg:
        user32.AttachThreadInput(cur, t_tg, True)
    user32.BringWindowToTop(hwnd)
    ok = user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    if t_tg:
        user32.AttachThreadInput(cur, t_tg, False)
    if t_fg:
        user32.AttachThreadInput(cur, t_fg, False)
    time.sleep(0.25)
    return bool(ok)


def move_window(hwnd, x, y, w=None, h=None):
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040
    cur = window_rect(hwnd)
    w = w or cur[2]
    h = h or cur[3]
    user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_NOZORDER | SWP_SHOWWINDOW)
    time.sleep(0.2)
    return window_rect(hwnd)


# ---------------- 鼠标 ----------------
def click(x, y, double=False):
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    ax = int(x * 65535 / (sw - 1))
    ay = int(y * 65535 / (sh - 1))
    _send(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay))
    time.sleep(0.06)
    _send(_mouse(MOUSEEVENTF_LEFTDOWN), _mouse(MOUSEEVENTF_LEFTUP))
    if double:
        time.sleep(0.08)
        _send(_mouse(MOUSEEVENTF_LEFTDOWN), _mouse(MOUSEEVENTF_LEFTUP))
    time.sleep(0.12)


def click_in_window(hwnd, rx, ry, double=False):
    x, y, _, _ = window_rect(hwnd)
    click(x + rx, y + ry, double)


# ---------------- 键盘 ----------------
def send_keys(seq):
    """seq: 形如 ['CTRL','A'] 或 ['ENTER']，最后一个键为普通按下"""
    mods = seq[:-1]
    keys = set(VK[m.upper()] for m in mods)
    for vk in keys:
        _send(_key(vk))
    key = seq[-1]
    vk = VK.get(key.upper()) if isinstance(key, str) and key.upper() in VK else None
    if vk:
        _send(_key(vk), _key(vk, up=True))
    elif isinstance(key, str):
        for ch in key:
            _send(_uni(ch), _uni(ch, up=True))
    for vk in keys:
        _send(_key(vk, up=True))
    time.sleep(0.12)


def type_text(text):
    for ch in text:
        _send(_uni(ch), _uni(ch, up=True))
    time.sleep(0.15)


def paste_text(text):
    """写剪贴板后 Ctrl+V，中文输入最可靠"""
    set_clipboard(text)
    time.sleep(0.12)
    send_keys(["CTRL", "V"])
    time.sleep(0.25)


def clear_field(hwnd=None):
    send_keys(["CTRL", "A"])
    send_keys(["DELETE"])
    time.sleep(0.1)


# ---------------- 剪贴板 ----------------
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def get_clipboard():
    if not user32.OpenClipboard(None):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.c_wchar_p(p).value
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def set_clipboard(text):
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    for _ in range(12):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, size)
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        user32.CloseClipboard()
    time.sleep(0.08)


# ---------------- 截图 ----------------
def screenshot_region(x, y, w, h):
    from PIL import Image
    hdc = user32.GetDC(0)
    memdc = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
    bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, w, h)
    ctypes.windll.gdi32.SelectObject(memdc, bmp)
    SRCCOPY = 0x00CC0020
    ctypes.windll.gdi32.BitBlt(memdc, 0, 0, w, h, hdc, x, y, SRCCOPY)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", DWORD),
                    ("biSizeImage", DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", DWORD), ("biClrImportant", DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    ctypes.windll.gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    ctypes.windll.gdi32.DeleteObject(bmp)
    ctypes.windll.gdi32.DeleteDC(memdc)
    user32.ReleaseDC(0, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def screenshot_window(hwnd):
    x, y, w, h = window_rect(hwnd)
    return screenshot_region(x, y, w, h)


user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.PrintWindow.restype = wt.BOOL


def print_window(hwnd, flags=2):
    """用 PrintWindow 直接抓窗口自身位图（PW_RENDERFULLCONTENT=2）。
    对 Qt/硬件加速窗口比屏幕 BitBlt 更可靠，且不要求窗口在最前。
    返回 (PIL.Image, ok)
    """
    from PIL import Image
    x, y, w, h = window_rect(hwnd)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", DWORD),
                    ("biSizeImage", DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", DWORD), ("biClrImportant", DWORD)]

    hdc = user32.GetDC(0)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)
    ok = bool(user32.PrintWindow(hwnd, memdc, flags))
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(0, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB"), ok


def screenshot_desktop():
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return screenshot_region(0, 0, sw, sh)
