# -*- coding: utf-8 -*-
"""探针：摸清达人广场的**类目筛选入口**，为「主推类目不筛选、改在下方查看达人处选类目」做准备。

用户 2026-09-17 新要求（原话）：
  「再次添加规则，在主推类目中，不对类目进行筛选，只在下方查看达人时，
    选择之前所要求的类目达人，然后粉丝画像中，粉丝性别选择女性偏多，
    达人画像中，达人性别选择女。」

本探针只做**只读侦察**：把页面上所有跟「类目」有关的可点元素、tab、
筛选栏 form-item、以及列表区域上方的控件全 dump 出来，好判断「下方查看达人」
到底指哪个控件（可能是「带货类目」这个入口，也可能列表另有类目筛选）。

跑法：source tools/env.sh && "$PY" .probe/probe_square.py
"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
SHOT = os.path.join(BASE, "out", "probe_square.png")


def log(m):
    print(m, flush=True)


# 把所有「短文本叶子元素」按文档顺序列出来 —— 结构一览无余
LEAVES_JS = """(args) => {
    const [maxLen, mustContain] = args;
    const out = [];
    document.querySelectorAll('body *').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return;
        const t = (e.innerText || '').trim().replace(/\\s+/g, ' ');
        if (!t || t.length > maxLen) return;
        if (mustContain && t.indexOf(mustContain) < 0) return;
        for (const c of e.children) {
            if ((c.innerText || '').trim().replace(/\\s+/g, ' ') === t) return;
        }
        if (r.top < 0 || r.top > window.innerHeight) return;
        out.push({tag: e.tagName,
                  cls: (e.className || '').toString().slice(0, 64),
                  t: t,
                  x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height),
                  cur: getComputedStyle(e).cursor});
    });
    return out;
}"""

FORMITEMS_JS = """() => {
    const out = [];
    document.querySelectorAll('div.auxo-form-item, .auxo-form-item').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 8) return;
        out.push({t: (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 40),
                  x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height)});
    });
    return out;
}"""


def show(items, title, limit=90):
    log("\n" + "=" * 74)
    log("### %s  (n=%d)" % (title, len(items)))
    for i, it in enumerate(items[:limit]):
        log("  %2d) %-6s t=%-22r box=[%d,%d,%d,%d] cur=%s cls=%s"
            % (i, it.get("tag", "?"), it["t"], it["x"], it["y"], it["w"], it["h"],
               it.get("cur", "?"), it.get("cls", "")))


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            viewport={"width": 2552, "height": 1262},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        log("打开达人广场 …")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(10)

        txt = page.evaluate("() => document.body.innerText.slice(0, 400)")
        if not any(m in txt for m in ("主推类目", "找达人", "按商品找达人")):
            log("!! 未登录，先手动登录再重跑")
            ctx.close()
            return
        log("登录态: 已登录")

        # 1) 筛选栏 form-item 全量
        show(page.evaluate(FORMITEMS_JS), "筛选栏 form-item")

        # 2) 所有含「类目」的短文本元素
        show(page.evaluate(LEAVES_JS, [16, "类目"]), "含「类目」的叶子")

        # 3) 所有含「查看达人」的元素
        show(page.evaluate(LEAVES_JS, [30, "查看达人"]), "含「查看达人」的叶子")

        # 4) tab 类控件
        tabs = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('[role=tab], .auxo-tabs-tab, .auxo-radio-button-wrapper, .auxo-tabs-nav-list > *').forEach(e => {
                const r = e.getBoundingClientRect();
                if (r.width < 10 || r.height < 8) return;
                out.push({tag: e.tagName, t: (e.innerText||'').trim().slice(0,24),
                          x: Math.round(r.x), y: Math.round(r.y),
                          w: Math.round(r.width), h: Math.round(r.height),
                          cls: (e.className||'').toString().slice(0,54)});
            });
            return out;
        }""")
        show(tabs, "tab / radio-button 控件")

        # 5) 左侧导航
        nav = page.evaluate(LEAVES_JS, [14, None])
        band = [n for n in nav if n["x"] < 200]
        show(band, "左侧导航区叶子（x<200）", 60)

        page.screenshot(path=SHOT, full_page=False)
        log("\n截图: %s" % SHOT)
        time.sleep(2)
        ctx.close()


if __name__ == "__main__":
    main()
