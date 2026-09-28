# -*- coding: utf-8 -*-
"""最小复现：只启动自动化 Edge，保持 20 秒，打印完整异常与进程数变化。"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROFILE = os.path.join(BASE, ".edge-auto", "profile")


def count():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
             "Where-Object {$_.CommandLine -like '*edge-auto*'}).Count"],
            stderr=subprocess.DEVNULL, timeout=60)
        return out.decode(errors="replace").strip()
    except Exception as e:
        return "ERR:%s" % str(e)[:60]


print("启动前 edge-auto 数:", count())
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
            timeout=120_000,
        )
    except Exception as e:
        print("!! 启动失败：")
        print(type(e).__name__, str(e)[:4000])
        sys.exit(1)
    print("启动成功，pages=%d" % len(ctx.pages))
    for i in range(4):
        time.sleep(5)
        try:
            n = len([pg for pg in ctx.pages if not pg.is_closed()])
            url = ctx.pages[0].url if ctx.pages else "(无页面)"
            print("t+%ds 存活页=%d url=%s edge-auto=%s" % ((i + 1) * 5, n, url, count()))
        except Exception as e:
            print("t+%ds 异常：%s | edge-auto=%s" % ((i + 1) * 5, str(e)[:200], count()))
            break
    try:
        ctx.close()
        print("ctx.close() OK")
    except Exception as e:
        print("ctx.close() 异常：%s" % str(e)[:200])
time.sleep(2)
print("退出后 edge-auto 数:", count())
