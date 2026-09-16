# -*- coding: utf-8 -*-
"""深度侦察：
1) 列出微信进程的全部窗口（含不可见），看「添加朋友/申请添加朋友」是不是独立窗口、类名是什么
2) 检查微信相关进程监听的端口，判断有没有可挂钩的调试端口（CEF/CDP）
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---- 进程枚举 ----
TH32CS_SNAPPROCESS = 0x2


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
pe = PROCESSENTRY32()
pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
proc_names = {}
if kernel32.Process32First(snap, ctypes.byref(pe)):
    while True:
        proc_names[pe.th32ProcessID] = pe.szExeFile.decode("gbk", "replace")
        if not kernel32.Process32Next(snap, ctypes.byref(pe)):
            break
kernel32.CloseHandle(snap)

WECHAT_KEY = ("weixin", "wechat")


def is_wechat_pid(pid):
    name = proc_names.get(pid, "").lower()
    return any(k in name for k in WECHAT_KEY)


# ---- 窗口枚举（含不可见）----
EnumWindows = user32.EnumWindows
Proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

rows = []


def cb(hwnd, lparam):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not is_wechat_pid(pid.value):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 2)
    user32.GetWindowTextW(hwnd, buf, length + 2)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    visible = bool(user32.IsWindowVisible(hwnd))
    parent = user32.GetParent(hwnd)
    rows.append((hwnd, pid.value, proc_names.get(pid.value, "?"), cls.value, buf.value, visible, parent))
    return True


EnumWindows(Proc(cb), 0)

print("=" * 90)
print("微信相关进程窗口（含隐藏）")
print("=" * 90)
for hwnd, pid, exe, cls, title, visible, parent in rows:
    print("HWND=%-10d PID=%-6d %-16s vis=%-5s parent=%-10d" % (hwnd, pid, exe, visible, parent))
    print("    class=%s" % cls)
    print("    title=%r" % title)

print()
print("=" * 90)
print("微信相关进程监听端口 (判断有无 CDP/DevTools 端口)")
print("=" * 90)
try:
    net = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=60, errors="replace")
    wpid = {pid for pid in proc_names if is_wechat_pid(pid)}
    hits = []
    for line in net.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[-1].isdigit() and int(parts[-1]) in wpid:
            hits.append((parts[-1], parts[0], parts[1], parts[3]))
    if not hits:
        print("(未解析到监听端口)")
    for pid, proto, local, state in sorted(set(hits)):
        print("%-8s %-24s %-12s pid=%s" % (proto, local, state, pid))
except Exception as e:
    print("netstat 失败: %r" % e)

print()
print("=" * 90)
print("结论提示：若 listen 列表为空或只有外部连接，说明微信未开放任何可挂钩的调试端口。")
print("=" * 90)
