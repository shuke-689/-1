# -*- coding: utf-8 -*-
"""探针：查清「粉丝量」筛选为什么读到结算字段的下拉。

背景（2026-09-17 10:43 实跑踩到）
---------------------------------
collect_ghq.log：
    [sale] 直播结算总额 下拉选项: 1w以下 | 1w-10w | ...
    [sale] 直播结算总额 -> 1w-10w OK
    [fans] 粉丝量 下拉选项: 1w以下 | 1w-10w | ...     ← 错！这是结算的下拉
    [fans] 下拉里没有 10w以下
（连试 3 次全失败 -> 粉丝量筛选从未生效）

代码侧的疑点：
  · FIND_FORMITEM_JS 遍历所有 div.auxo-form-item，**用最后一个匹配项**；
  · DROPDOWN_JS 取**最后一个可见**的 .auxo-select-dropdown（dds[dds.length-1]）。
两者都是「取最后一个」——只要页面上同时有多个可见下拉，就会串。

本探针回答三个问题：
  1. 点开「直播结算总额」并选完后，页面上还剩几个可见下拉？（Escape 有没有关掉）
  2. 再点「粉丝量」时，页面上有几个可见下拉？各自 box 与选项是什么？
  3. 「粉丝量」的 form-item 矩形在哪？有没有被上面的下拉盖住？

只读，不写任何数据。
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
OUTP = os.path.join(BASE, "out", "probe_fans_dd.json")

from playwright.sync_api import sync_playwright  # noqa: E402

LOGGED_IN_MARK = ("主推类目", "找达人", "按商品找达人")

# 列出**所有**可见下拉（不是只取最后一个）
ALL_DD_JS = """() => {
    const dds = Array.from(document.querySelectorAll('.auxo-select-dropdown'))
        .filter(e => e.getBoundingClientRect().height > 10);
    return dds.map((dd, i) => {
        const dr = dd.getBoundingClientRect();
        return {
            idx: i,
            cls: (dd.className||'').toString(),
            x: Math.round(dr.x), y: Math.round(dr.y),
            w: Math.round(dr.width), h: Math.round(dr.height),
            items: Array.from(dd.querySelectorAll('.auxo-select-item-option-content'))
                .map(e => (e.innerText||'').trim())
        };
    });
}"""

# 页面上所有 form-item 的名字 + 矩形（看「粉丝量」到底在哪、是否唯一）
ALL_FORMITEM_JS = """() => {
    const out = [];
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        out.push({t:(e.innerText||'').trim().replace(/\\n/g,' ').slice(0,30),
                  x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height)});
    });
    return out;
}"""


def main():
    rec = {"steps": []}

    def note(msg, **kw):
        line = {"msg": msg}
        line.update(kw)
        rec["steps"].append(line)
        print("[probe] " + msg, flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(DAREN, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        time.sleep(3)

        body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        if not any(m in body for m in LOGGED_IN_MARK):
            note("!! 未登录 -> 中止")
            rec["ok"] = False
            json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            ctx.close()
            return
        note("登录态 OK")

        def dump_dds(tag):
            dds = page.evaluate(ALL_DD_JS)
            note("%s：可见下拉 %d 个" % (tag, len(dds)))
            for d in dds:
                note("   #%d box=(x%d,y%d,w%d,h%d) items=%s" % (
                    d["idx"], d["x"], d["y"], d["w"], d["h"], d["items"]))
            return dds

        def find_item(name):
            return page.evaluate("""(name) => {
                let out = [];
                document.querySelectorAll('div.auxo-form-item').forEach(e => {
                    if ((e.innerText||'').trim() !== name) return;
                    const r = e.getBoundingClientRect();
                    if (r.width < 20 || r.height < 10) return;
                    out.push({x:Math.round(r.x), y:Math.round(r.y),
                              w:Math.round(r.width), h:Math.round(r.height)});
                });
                return out;
            }""", name)

        def click_box(b):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(1.6)

        # ---- 0) 初始状态 ----
        note("初始 form-item 数：%d" % len(page.evaluate(ALL_FORMITEM_JS)))
        note("「粉丝量」匹配到的元素：%s" % find_item("粉丝量"))
        note("「直播结算总额」匹配到的元素：%s" % find_item("直播结算总额"))
        note("「结算总额」匹配到的元素：%s" % find_item("结算总额"))
        dump_dds("初始")

        # ---- 1) 点开直播结算总额并选 1w-10w（复现 collect 的流程） ----
        boxes = find_item("直播结算总额")
        if not boxes:
            note("!! 没找到直播结算总额")
            ctx.close()
            return
        note("点击「直播结算总额」@%s" % boxes[-1])
        click_box(boxes[-1])
        dds = dump_dds("点开直播结算总额后")
        # 选 1w-10w
        tgt = None
        for d in dds:
            if "1w-10w" in d["items"]:
                # 取该下拉里 1w-10w 的坐标
                tgt = d
                break
        if tgt is None:
            note("!! 没有含 1w-10w 的下拉")
            ctx.close()
            return
        # 用 JS 拿选项中心点
        pt = page.evaluate("""() => {
            const dds = Array.from(document.querySelectorAll('.auxo-select-dropdown'))
                .filter(e => e.getBoundingClientRect().height > 10);
            for (const dd of dds) {
                const el = Array.from(dd.querySelectorAll('.auxo-select-item-option-content'))
                    .find(e => (e.innerText||'').trim() === '1w-10w');
                if (el) { const r = el.getBoundingClientRect();
                          return {x:Math.round(r.x), y:Math.round(r.y),
                                  w:Math.round(r.width), h:Math.round(r.height)}; }
            }
            return null;
        }""")
        note("1w-10w 选项位置 = %s" % pt)
        if pt:
            page.mouse.click(pt["x"] + pt["w"] / 2.0, pt["y"] + pt["h"] / 2.0)
            time.sleep(1.5)
        note("已点击 1w-10w；接着按 Escape（复现 apply_formitem）")
        page.keyboard.press("Escape")
        time.sleep(1.2)
        dump_dds("选完 1w-10w + Escape 之后")

        # ---- 2) 点「粉丝量」 ----
        fboxes = find_item("粉丝量")
        note("「粉丝量」位置 = %s（共 %d 个匹配）" % (fboxes, len(fboxes)))
        if fboxes:
            click_box(fboxes[-1])
            dump_dds("点开粉丝量之后")

        rec["ok"] = True
        json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("[probe] 已写入 %s" % OUTP, flush=True)
        ctx.close()


if __name__ == "__main__":
    main()
