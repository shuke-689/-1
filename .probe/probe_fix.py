# -*- coding: utf-8 -*-
"""诊断 collect.py 的两个问题：
1) 「主推类目」筛选 chip 的真实定位方式（为什么点「美妆」失败）
2) 取不到微信号的达人主页，联系方式区长什么样
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
PROFILE_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=%s&enter_from=1&scene=1&author_type=1"

FAILED = {
    "青姐日记": "v2_0a2bd84e6db61cc7aa423a2aebf831a96b8754f33ba5019cb69bb98de175bbb7e75b2036e9c8a73947b14957541a4b0a3c0000000000000000000050e7e9c7292b26f86f3a3aed10f66e7e4e2fe7d408dea9b13f58f69372f0b9a302060da40a715ffd36b84fe913bbd522224b10a2a99c0e18e5ade4c901200122010366b6e8f2",
    "禾禾": "v2_0a2c61c9fe48344790a7f722a3823501b35296439d723104b7445ce689a25ff797e196b0fe10bd8153b7fa1977ad1a4b0a3c0000000000000000000050e7e9c7292b26f86f3a3aed10f66e7e4e2fe7d408dea9b13f58f69372f0b9a302060da40a715ffd36b84fe913bbd522224b10a2a99c0e18e5ade4c901200122010341cfb9b1",
}

# 找筛选栏 chip：文本短、位于页面上部、可点击
CHIPS_JS = """() => {
    const out = [];
    document.querySelectorAll('div,span,button,a,label').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 30 || t.includes('\\n')) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 16 || r.height > 70) return;
        if (r.y < 60 || r.y > 460) return;
        const cls = (e.className||'').toString();
        out.push({tag:e.tagName, cls:cls.slice(0,90), text:t,
                  rect:{x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}});
    });
    return out;
}"""

# 达人主页联系方式区
CONTACT_JS = """() => {
    const out = {rows: [], icons: [], text: ''};
    const body = document.body.innerText || '';
    out.text = body.replace(/\\n{2,}/g, '\\n').slice(0, 2500);
    document.querySelectorAll('*').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 60 || t.includes('\\n')) return;
        if (!/微信|手机号|联系方式/.test(t)) return;
        const r = e.getBoundingClientRect();
        if (r.width < 5 || r.height < 5) return;
        out.rows.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,110), text:t,
                       rect:{x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}});
    });
    document.querySelectorAll('span,i,div,svg,img,button').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 6 || r.height < 6 || r.width > 70 || r.height > 70) return;
        const cls = (e.className||'').toString();
        if (!/contact-item-btn|index__copy|icon-copy|copy|Copy|eye|Eye/.test(cls)) return;
        out.icons.push({tag:e.tagName, cls:cls.slice(0,110),
                        rect:{x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}});
    });
    return out;
}"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("=" * 70)
        print("A. 达人广场筛选栏 chip 结构")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)
        chips = page.evaluate(CHIPS_JS)
        seen = set()
        for c in chips:
            key = (c["text"], round(c["rect"]["y"] / 10))
            if key in seen:
                continue
            seen.add(key)
            print("  y=%-4d x=%-5d w=%-4d h=%-3d %-6s %-28s | %s" % (
                c["rect"]["y"], c["rect"]["x"], c["rect"]["w"], c["rect"]["h"],
                c["tag"], c["text"][:28], c["cls"][:60]))

        print()
        print("  点击「主推类目」chip 后看面板项:")
        try:
            page.locator("text=主推类目").first.click(timeout=6000)
            time.sleep(2.5)
            panel = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('*').forEach(e => {
                    const t = (e.innerText||'').trim();
                    if (!t || t.length > 12 || t.includes('\\n')) return;
                    const r = e.getBoundingClientRect();
                    if (r.width < 20 || r.height < 16 || r.height > 60) return;
                    if (r.y < 100 || r.y > 700) return;
                    out.push({t:t, x:Math.round(r.x), y:Math.round(r.y),
                              cls:(e.className||'').toString().slice(0,80)});
                });
                return out;
            }""")
            seen2 = set()
            for it in panel:
                k = (it["t"], round(it["x"] / 20), round(it["y"] / 20))
                if k in seen2:
                    continue
                seen2.add(k)
                print("     y=%-4d x=%-5d %-12s | %s" % (it["y"], it["x"], it["t"][:12], it["cls"][:70]))
        except Exception as e:
            print("     点击失败: %s" % str(e)[:120])

        print()
        print("=" * 70)
        print("B. 取不到微信号的达人主页")
        for name, uid in FAILED.items():
            print("-" * 70)
            print("  【%s】" % name)
            try:
                page.goto(PROFILE_URL % uid, wait_until="domcontentloaded", timeout=60_000)
                time.sleep(5)
                # 往下滚，确保联系方式区渲染
                for _ in range(3):
                    page.mouse.wheel(0, 1200)
                    time.sleep(1.2)
                page.mouse.wheel(0, -6000)
                time.sleep(1.5)
                d = page.evaluate(CONTACT_JS)
                print("  rows(%d):" % len(d["rows"]))
                for r in d["rows"]:
                    print("     y=%-5d x=%-5d %-14s | %s | %s" % (
                        r["rect"]["y"], r["rect"]["x"], r["text"][:14], r["tag"], r["cls"][:60]))
                print("  icons(%d):" % len(d["icons"]))
                for r in d["icons"]:
                    print("     y=%-5d x=%-5d %-6s | %s" % (
                        r["rect"]["y"], r["rect"]["x"], r["tag"], r["cls"][:70]))
                print("  页面文本片段:")
                txt = d["text"]
                print("    " + txt[:1200].replace("\n", "\n    "))
            except Exception as e:
                print("  异常: %s" % str(e)[:140])

        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
