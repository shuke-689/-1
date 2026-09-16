# -*- coding: utf-8 -*-
"""最小诊断：检查 .edge-auto/profile 的登录态是否还有效。

打开达人广场，打印最终 URL / 标题 / 是否出现「登录」按钮，并截图。
用法：
  python .probe/probe_login.py
"""
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


def main():
    from playwright.sync_api import sync_playwright
    shot = os.path.join(BASE, "out", "collect", "login_check.png")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("goto", C.DAREN)
        try:
            page.goto(C.DAREN, wait_until="domcontentloaded", timeout=90_000)
        except Exception as e:
            print("goto 异常:", str(e)[:120])
        time.sleep(10)
        try:
            print("最终 URL :", page.url)
            print("标题     :", page.title())
        except Exception as e:
            print("取 url/title 失败:", str(e)[:120])
        try:
            info = page.evaluate("""() => {
                const txt = (document.body.innerText || '').slice(0, 600);
                const hasLogin = /登录|扫码登录|请先登录/.test(txt);
                const btns = [];
                document.querySelectorAll('button, a').forEach(e => {
                    const t = (e.innerText||'').trim();
                    if (t === '登录' || t === '立即登录') btns.push(t);
                });
                return {hasLogin: hasLogin, loginBtns: btns.slice(0, 5), head: txt.slice(0, 220)};
            }""")
            print("页面含登录字样:", info["hasLogin"], "| 登录按钮:", info["loginBtns"])
            print("正文开头:", info["head"].replace("\n", " / ")[:220])
        except Exception as e:
            print("页面探测失败:", str(e)[:150])
        try:
            page.screenshot(path=shot)
            print("截图:", shot)
        except Exception:
            pass
        time.sleep(1.5)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
