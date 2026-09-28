# -*- coding: utf-8 -*-
"""只读探针：用自动化 profile 打开达人广场，判定登录态并留证截图。

不点任何按钮、不改任何配置。产出：
  out/collect/_loginstate_now.png
  stdout: 正文前 1200 字 + 命中标记
"""
import io
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

import collect as C  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MARK = ("主推类目", "找达人", "按商品找达人", "达人广场")
BAD = ("登录", "扫码", "二维码", "未登录")


def main():
    urls = [u for u in sys.argv[1:] if u.startswith("http")] or [C.DAREN]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for u in urls:
            body = ""
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=90_000)
            except Exception as e:
                print("goto 异常: %s" % str(e)[:150])
            time.sleep(10)
            for _ in range(3):
                try:
                    body = page.evaluate("() => (document.body.innerText || '')")
                    if body.strip():
                        break
                except Exception as e:
                    print("读正文异常: %s" % str(e)[:100])
                time.sleep(3)
            tag = "".join(ch if ch.isalnum() else "_" for ch in u)[-40:]
            try:
                page.screenshot(path=os.path.join(BASE, "out", "collect",
                                                 "_loginstate_%s.png" % tag))
            except Exception as e:
                print("截图失败: %s" % str(e)[:120])
            print("=== %s" % u)
            print("URL: %s" % page.url)
            print("正文长度: %d" % len(body or ""))
            hit = [m for m in MARK if m in (body or "")]
            bad = [m for m in BAD if m in (body or "")]
            print("命中登录标记: %s" % hit)
            print("命中未登录标记: %s" % bad)
            print("--- 正文前 900 字 ---")
            print((body or "")[:900])
        time.sleep(1)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
