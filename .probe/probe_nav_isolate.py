# -*- coding: utf-8 -*-
"""逐个导航到给定 URL，每次导航后观察浏览器是否仍然存活（隔离"是不是站点导致 Edge 崩"）。"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROFILE = os.path.join(BASE, ".edge-auto", "profile")
URLS = [u for u in sys.argv[1:] if u.startswith("http")] or [
    "https://www.bing.com/",
    "https://buyin.jinritemai.com/dashboard/servicehall/daren-square",
]


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


from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE, channel="msedge", headless=False,
        no_viewport=True,
        args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        timeout=120_000,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for u in URLS:
        print("=" * 60)
        print("goto %s" % u)
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=90_000)
            print("  goto OK")
        except Exception as e:
            print("  goto 异常: %s %s" % (type(e).__name__, str(e)[:300]))
        for i in range(3):
            time.sleep(4)
            try:
                url = page.url
                body = page.evaluate("() => (document.body.innerText||'').slice(0,300)")
                print("  t+%ds url=%s | 正文 %d 字: %s"
                      % ((i + 1) * 4, url, len(body), body.replace("\n", " / ")[:200]))
            except Exception as e:
                print("  t+%ds 掉线: %s %s | edge-auto=%s"
                      % ((i + 1) * 4, type(e).__name__, str(e)[:150], count()))
                break
    try:
        ctx.close()
    except Exception:
        pass
