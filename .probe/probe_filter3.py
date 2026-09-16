# -*- coding: utf-8 -*-
"""定位「视频结算总额」这类区间筛选的真实触发点。
dump form-item 的 HTML 结构 + 点击后所有浮层（popover/dropdown/trigger）的内容。
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

POPOVERS_JS = """() => {
    const out = {triggers: [], popovers: [], bodyTail: []};
    document.querySelectorAll('*').forEach(e => {
        const cls = (e.className||'').toString();
        if (/auxo-trigger|auxo-popover|auxo-dropdown|auxo-select-dropdown|auxo-tooltip/.test(cls)) {
            const r = e.getBoundingClientRect();
            const t = (e.innerText||'').trim().replace(/\\n/g, ' | ').slice(0, 400);
            const rec = {cls: cls.slice(0,120), t: t, w:Math.round(r.width), h:Math.round(r.height),
                         x:Math.round(r.x), y:Math.round(r.y),
                         vis: (r.width>0 && r.height>0)};
            if (/auxo-trigger/.test(cls)) out.triggers.push(rec);
            else out.popovers.push(rec);
        }
    });
    const kids = Array.from(document.body.children);
    kids.slice(-6).forEach(e => {
        const r = e.getBoundingClientRect();
        out.bodyTail.push({cls:(e.className||'').toString().slice(0,80),
                           id:e.id||'', w:Math.round(r.width), h:Math.round(r.height),
                           x:Math.round(r.x), y:Math.round(r.y)});
    });
    return out;
}"""

FORMITEM_HTML_JS = """(name) => {
    const hits = [];
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        const t = (e.innerText||'').trim();
        if (t !== name) return;
        const r = e.getBoundingClientRect();
        hits.push({y:Math.round(r.y), x:Math.round(r.x), w:Math.round(r.width), h:Math.round(r.height),
                   html: e.outerHTML.slice(0, 1400)});
    });
    return hits;
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

        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        print("=" * 78)
        print("[A] 「视频结算总额」form-item 的 HTML")
        for h in page.evaluate(FORMITEM_HTML_JS, "视频结算总额"):
            print("  @(%d,%d) %dx%d" % (h["x"], h["y"], h["w"], h["h"]))
            print("  " + h["html"].replace("><", ">\n  <"))

        print()
        print("=" * 78)
        print("[B] 点击 form-item 中心，看浮层")
        box = page.evaluate("""() => {
            let out = null;
            document.querySelectorAll('div.auxo-form-item').forEach(e => {
                if ((e.innerText||'').trim() !== '视频结算总额') return;
                const r = e.getBoundingClientRect();
                out = {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
            });
            return out;
        }""")
        print("  box = %s" % box)
        if box:
            page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            time.sleep(2.0)
            d = page.evaluate(POPOVERS_JS)
            print("  triggers(%d):" % len(d["triggers"]))
            for t in d["triggers"][:20]:
                print("     vis=%-5s %dx%d @(%d,%d) %s | %s" % (
                    t["vis"], t["w"], t["h"], t["x"], t["y"], t["cls"][:70], t["t"][:120]))
            print("  popovers(%d):" % len(d["popovers"]))
            for t in d["popovers"][:20]:
                print("     vis=%-5s %dx%d @(%d,%d) %s | %s" % (
                    t["vis"], t["w"], t["h"], t["x"], t["y"], t["cls"][:70], t["t"][:200]))
            print("  body 末尾子元素:")
            for t in d["bodyTail"]:
                print("     %dx%d @(%d,%d) cls=%s id=%s" % (
                    t["w"], t["h"], t["x"], t["y"], t["cls"][:60], t["id"]))

        print()
        print("=" * 78)
        print("[C] 改点 form-item 右侧（尾部箭头区域）")
        page.keyboard.press("Escape")
        time.sleep(0.8)
        if box:
            tx = box["x"] + box["w"] - 10
            ty = box["y"] + box["h"] / 2
            print("  点 (%d,%d)" % (tx, ty))
            page.mouse.click(tx, ty)
            time.sleep(2.0)
            d = page.evaluate(POPOVERS_JS)
            print("  triggers(%d) popovers(%d)" % (len(d["triggers"]), len(d["popovers"])))
            for t in d["popovers"][:12]:
                print("     vis=%-5s %dx%d @(%d,%d) | %s" % (
                    t["vis"], t["w"], t["h"], t["x"], t["y"], t["t"][:260]))
            for t in d["triggers"][:12]:
                print("     TRIG vis=%-5s %dx%d @(%d,%d) | %s" % (
                    t["vis"], t["w"], t["h"], t["x"], t["y"], t["t"][:160]))

        print()
        print("=" * 78)
        print("[D] 屏幕可见文本（用于找 1w-10w 这类选项）")
        items = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('*').forEach(e => {
                const t = (e.innerText||'').trim();
                if (!t || t.length > 20 || t.includes('\\n')) return;
                const r = e.getBoundingClientRect();
                if (r.width < 6 || r.height < 6 || r.height > 60) return;
                if (!/[0-9]/.test(t)) return;
                if (!/w|万|以下|以上|区间/.test(t)) return;
                out.push({t:t, x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width),
                          h:Math.round(r.height), cls:(e.className||'').toString().slice(0,70)});
            });
            return out;
        }""")
        seen = set()
        for it in items:
            k = (it["t"], round(it["x"] / 15), round(it["y"] / 15))
            if k in seen:
                continue
            seen.add(k)
            print("     y=%-5d x=%-5d %-16s | %s" % (it["y"], it["x"], it["t"][:16], it["cls"][:60]))

        time.sleep(2)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
