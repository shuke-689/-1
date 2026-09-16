# -*- coding: utf-8 -*-
"""针对微信「添加朋友」独立窗口做 UIA + MSAA(IAccessible) 双重探测。
若两者都拿不到控件，则确认必须走 OCR + 键鼠模拟。
"""
import io
import sys
import ctypes
import ctypes.wintypes as wt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32


def find_window_by_title(title):
    return user32.FindWindowW(None, title)


def enum_child_windows(hwnd, depth=0, maxdepth=4):
    """用 Win32 EnumChildWindows 拿原生子窗口（很多自绘 UI 连子窗口都没有）"""
    out = []
    CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, lp):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        n = user32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(h, b, n + 2)
        rect = wt.RECT()
        user32.GetWindowRect(h, ctypes.byref(rect))
        out.append((h, cls.value, b.value, (rect.left, rect.top, rect.right, rect.bottom)))
        if depth < maxdepth:
            out.extend(enum_child_windows(h, depth + 1, maxdepth))
        return True

    user32.EnumChildWindows(hwnd, CB(cb), 0)
    return out


for title in ("添加朋友", "申请添加朋友", "微信"):
    hwnd = find_window_by_title(title)
    print("=" * 88)
    print("窗口 %r -> HWND=%s" % (title, hwnd))
    if not hwnd:
        print("  (未找到，可能没打开)")
        continue

    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print("  位置尺寸: (%d,%d)-(%d,%d)  %dx%d" % (
        rect.left, rect.top, rect.right, rect.bottom,
        rect.right - rect.left, rect.bottom - rect.top))

    kids = enum_child_windows(hwnd)
    print("  Win32 原生子窗口数: %d" % len(kids))
    for h, cls, txt, r in kids[:15]:
        print("     HWND=%-10d class=%-30s text=%r rect=%s" % (h, cls, txt, r))

    # --- UIA 探测 ---
    try:
        import uiautomation as auto
        ctrl = auto.ControlFromHandle(hwnd)
        if ctrl is None:
            print("  [UIA] ControlFromHandle 返回 None")
        else:
            print("  [UIA] 根控件: Name=%r Type=%s Class=%r" % (
                ctrl.Name, ctrl.ControlTypeName, ctrl.ClassName))
            stack = [(ctrl, 0)]
            total = 0
            by_type = {}
            while stack:
                cur, d = stack.pop()
                try:
                    ch = cur.GetChildren()
                except Exception:
                    ch = []
                for c in ch:
                    total += 1
                    t = c.ControlTypeName
                    by_type[t] = by_type.get(t, 0) + 1
                    if d < 3:
                        stack.append((c, d + 1))
            print("  [UIA] 后代控件总数=%d" % total)
            print("  [UIA] 类型分布: %s" % by_type)
    except Exception as e:
        print("  [UIA] 探测失败: %r" % e)

    # --- MSAA / IAccessible 探测 ---
    try:
        import comtypes.client as cc
        import comtypes.gen.Accessibility as acc
        oleacc = ctypes.oledll.oleacc
        OBJID_CLIENT = 0xFFFFFFFC
        ptr = ctypes.POINTER(acc.IAccessible)()
        hr = oleacc.AccessibleObjectFromWindow(
            hwnd, OBJID_CLIENT,
            ctypes.byref(acc.IAccessible._iid_), ctypes.byref(ptr))
        print("  [MSAA] AccessibleObjectFromWindow hr=%s" % hr)
        if ptr:
            try:
                name = ptr.accName(0)
                role = ptr.accRole(0)
                cnt = ptr.accChildCount
                print("  [MSAA] 根: name=%r role=%s childCount=%s" % (name, role, cnt))
            except Exception as e2:
                print("  [MSAA] 根属性读取失败: %r" % e2)
    except Exception as e:
        print("  [MSAA] 探测失败: %r" % e)

print("=" * 88)
