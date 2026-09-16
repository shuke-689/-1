# -*- coding: utf-8 -*-
"""定位属于自动化配置(.edge-auto)的 Edge 窗口，并截图确认登录页状态。"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win_io as w  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 用 PowerShell 取命令行（Python 里读输出，绕开工具层拿不到 stdout 的问题）
ps = ("Get-CimInstance Win32_Process -Filter \"name='msedge.exe'\" | "
      "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
try:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=90, errors="replace")
    raw = r.stdout.strip()
except Exception as e:
    raw = ""
    print("取进程信息失败: %r" % e)

import json  # noqa: E402
procs = []
if raw:
    try:
        data = json.loads(raw)
        procs = data if isinstance(data, list) else [data]
    except Exception as e:
        print("解析失败: %r  raw head=%r" % (e, raw[:300]))

auto_pids = set()
for d in procs:
    cl = (d.get("CommandLine") or "")
    if ".edge-auto" in cl:
        auto_pids.add(d.get("ProcessId"))

print("自动化 Edge 进程 PID: %s" % sorted(p for p in auto_pids if p))

# 找这些进程的可见窗口
targets = []
for x in w.list_windows(""):
    if x["pid"] in auto_pids and x["visible"]:
        targets.append(x)

print("自动化 Edge 可见窗口 %d 个:" % len(targets))
for x in targets:
    print("  HWND=%-9d pid=%-6d %r" % (x["hwnd"], x["pid"], x["title"][:90]))

if targets:
    # 取最大的那个（主窗口）
    main = max(targets, key=lambda t: w.window_rect(t["hwnd"])[2] * w.window_rect(t["hwnd"])[3])
    print("主窗口: HWND=%s rect=%s" % (main["hwnd"], w.window_rect(main["hwnd"])))
    img = w.screenshot_window(main["hwnd"])
    out = os.path.join(BASE, "out", "stage1_login_window.png")
    img.save(out)
    print("截图: %s  %s" % (out, img.size))
else:
    print("未找到自动化 Edge 窗口 —— 可能已关闭")
