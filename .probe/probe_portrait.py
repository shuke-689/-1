# -*- coding: utf-8 -*-
"""探针：摸清「达人画像」agg 面板的真实结构，好让 apply_portrait() 点得准。

背景（2026-09-17）：collect.py 里第一版 apply_portrait 直接找文本「女」，
  实测失败。dump 出来的浮层是：
      cls=auxo-popover quick-filter-button-agg-pop ...
      text='达人性别 请选择 达人地区 签约机构 请选择 重置 确认取消'  radios=[]
  → 说明「达人性别」不是单选组，而是个「请选择」子下拉，且面板有「确认」。
     正确的操作序列应该是：点 达人画像 → 点 达人性别 的「请选择」→ 点 女 → 点 确认。

本探针**只读探索**：不改 collect.py、不发任何业务请求、不登录。
跑法（必须先确保采集器/Edge 没在跑）：
    source tools/env.sh && "$PY" .probe/probe_portrait.py
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
SHOT = os.path.join(BASE, "out", "probe_portrait.png")


def log(msg):
    print(msg, flush=True)


# --- 与 collect.py 一致的「找筛选项」JS（复制自 collect.py FIND_FORMITEM_JS）---------
FIND_FORMITEM_JS = """(name) => {
    let exact = null, prefix = null;
    document.querySelectorAll('div.auxo-form-item, .auxo-form-item').forEach(e => {
        const t = (e.innerText || '').trim();
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 8) return;
        if (t === name && !exact) exact = {x: r.x, y: r.y, w: r.width, h: r.height};
        else if (t.startsWith(name) && !prefix) prefix = {x: r.x, y: r.y, w: r.width, h: r.height};
    });
    const b = exact || prefix;
    if (!b) return null;
    return {x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h)};
}"""

# 把弹层里所有「可点叶子元素」列出来（按文档顺序），用于看清结构
DUMP_PANEL_JS = """() => {
    const out = {pops: [], leaves: []};
    const P = '.quick-filter-button-agg-pop';
    const pops = Array.from(document.querySelectorAll(P)).filter(e => {
        const r = e.getBoundingClientRect();
        return r.width > 40 && r.height > 20;
    });
    pops.forEach(p => {
        const r = p.getBoundingClientRect();
        out.pops.push({
            cls: (p.className || '').toString().slice(0, 120),
            box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
            text: (p.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
            html: p.outerHTML.slice(0, 4000)
        });
        p.querySelectorAll('*').forEach(e => {
            const er = e.getBoundingClientRect();
            if (er.width < 4 || er.height < 4) return;
            const t = (e.innerText || '').trim();
            if (!t || t.length > 24) return;
            // 只留「叶子」：没有子元素带同样文本，避免整块容器
            let hasSame = false;
            for (const c of e.children) {
                if ((c.innerText || '').trim() === t) { hasSame = true; break; }
            }
            if (hasSame) return;
            out.leaves.push({
                tag: e.tagName,
                cls: (e.className || '').toString().slice(0, 70),
                t: t.replace(/\\s+/g, ' '),
                box: [Math.round(er.x), Math.round(er.y), Math.round(er.width), Math.round(er.height)],
                cur: getComputedStyle(e).cursor
            });
        });
    });
    return out;
}"""

# 所有可见浮层（不限 class），用于看「请选择」点开后弹出的选项
DUMP_ALL_POPOVERS_JS = """() => {
    const SEL = '.auxo-select-dropdown, .auxo-popover, .auxo-dropdown, .auxo-tooltip, .auxo-cascader-menus';
    const out = [];
    document.querySelectorAll(SEL).forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 40 || r.height < 20) return;
        out.push({
            cls: (e.className || '').toString().slice(0, 110),
            box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
            text: (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 220)
        });
    });
    return out;
}"""

# 在 agg 面板里，找「某个标签之后」的第一个指定文本的可点元素
FIND_AFTER_LABEL_JS = """(args) => {
    const [label, target] = args;
    const P = '.quick-filter-button-agg-pop';
    const pops = Array.from(document.querySelectorAll(P)).filter(e => {
        const r = e.getBoundingClientRect();
        return r.width > 40 && r.height > 20;
    });
    if (!pops.length) return null;
    const p = pops[0];
    const all = Array.from(p.querySelectorAll('*')).filter(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return false;
        const t = (e.innerText || '').trim();
        if (!t || t.length > 30) return false;
        for (const c of e.children) {
            if ((c.innerText || '').trim() === t) return false;
        }
        return true;
    });
    let li = -1;
    for (let i = 0; i < all.length; i++) {
        if ((all[i].innerText || '').trim() === label) { li = i; break; }
    }
    if (li < 0) return null;
    for (let i = li + 1; i < all.length; i++) {
        if ((all[i].innerText || '').trim() === target) {
            const r = all[i].getBoundingClientRect();
            return {tag: all[i].tagName,
                    cls: (all[i].className || '').toString().slice(0, 70),
                    t: (all[i].innerText || '').trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
    }
    return null;
}"""


def click_box(page, b):
    page.mouse.click(int(b["x"] + b.get("w", 0) / 2), int(b["y"] + b.get("h", 0) / 2))


def dump_panel(page, title):
    log("\n" + "=" * 72)
    log("### " + title)
    d = page.evaluate(DUMP_PANEL_JS)
    log("pops=%d leaves=%d" % (len(d["pops"]), len(d["leaves"])))
    for i, p in enumerate(d["pops"][:2]):
        log("  [pop %d] box=%s\n      cls=%s\n      text=%r" % (i, p["box"], p["cls"], p["text"]))
    log("  -- leaves (按文档顺序) --")
    for i, l in enumerate(d["leaves"][:60]):
        log("   %2d) %-8s t=%-12r box=%s cur=%s cls=%s"
            % (i, l["tag"], l["t"], l["box"], l["cur"], l["cls"]))
    if d["pops"]:
        log("  -- 第一个 pop 的 outerHTML --")
        log(d["pops"][0]["html"])
    return d


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
        time.sleep(9)

        txt = page.evaluate("() => document.body.innerText.slice(0, 400)")
        logged = any(m in txt for m in ("主推类目", "找达人", "按商品找达人"))
        log("登录态: %s" % ("已登录" if logged else "未登录（本探针不处理登录，请先在浏览器里登录后重跑）"))
        if not logged:
            log("页面文本前 200 字: %r" % txt[:200])
            ctx.close()
            return

        # ① 点开 达人画像
        box = page.evaluate(FIND_FORMITEM_JS, "达人画像")
        log("\n达人画像 form-item box = %s" % box)
        if not box:
            log("!! 找不到「达人画像」筛选项")
            ctx.close()
            return
        click_box(page, box)
        time.sleep(2.0)
        dump_panel(page, "① 点开「达人画像」之后")

        # ② 点「达人性别」后面的「请选择」
        hit = page.evaluate(FIND_AFTER_LABEL_JS, ["达人性别", "请选择"])
        log("\n② 达人性别 之后的「请选择」= %s" % hit)
        if hit:
            click_box(page, hit)
            time.sleep(1.8)
            log("   -> 点开后可见浮层:")
            for d in page.evaluate(DUMP_ALL_POPOVERS_JS):
                log("      cls=%s box=%s text=%r" % (d["cls"], d["box"], d["text"]))
            page.screenshot(path=SHOT)
            log("   截图: %s" % SHOT)

            # ③ 点「女」
            h2 = page.evaluate(FIND_AFTER_LABEL_JS, ["请选择", "女"])
            log("\n③ 「请选择」之后的「女」= %s" % h2)
            if h2:
                click_box(page, h2)
                time.sleep(1.5)
                log("   -> 点「女」之后，可见浮层:")
                for d in page.evaluate(DUMP_ALL_POPOVERS_JS):
                    log("      cls=%s box=%s text=%r" % (d["cls"], d["box"], d["text"]))
                dump_panel(page, "③ 点了「女」之后的 agg 面板")
            else:
                # 也许「女」在刚弹出的下拉里，用全浮层找
                log("   面板内没找到「女」，尝试在全浮层里找 …")
                page.screenshot(path=SHOT)

        # ④ 找「确认」
        h3 = page.evaluate(FIND_AFTER_LABEL_JS, ["达人性别", "确认"])
        log("\n④ 面板里的「确认」= %s" % h3)
        dump_panel(page, "④ 收尾状态")
        page.screenshot(path=SHOT)
        log("\n最终截图: %s" % SHOT)

        log("\n（探针到此结束；浏览器保持打开，看完可 Ctrl+C）")
        time.sleep(3)
        ctx.close()


if __name__ == "__main__":
    main()
