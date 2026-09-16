# -*- coding: utf-8 -*-
"""探测本机可见顶层窗口，判断微信/Edge 是否可被系统 UI 自动化访问。"""
import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

results = []


def _cb(hwnd, lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    results.append((hwnd, pid.value, cls.value, title))
    return True


EnumWindows(EnumWindowsProc(_cb), 0)

KEYWORDS = ("微信", "weixin", "wechat", "edge", "抖音", "douyin")
print("可见顶层窗口总数: %d" % len(results))
print("-" * 78)
hits = 0
for hwnd, pid, cls, title in results:
    low = (title + " " + cls).lower()
    if any(k in low for k in KEYWORDS):
        hits += 1
        print("HWND=%-10d PID=%-8d CLASS=%-28s TITLE=%s" % (hwnd, pid, cls, title))
print("-" * 78)
print("命中目标窗口数: %d" % hits)
