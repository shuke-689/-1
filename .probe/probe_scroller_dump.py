# -*- coding: utf-8 -*-
"""诊断：为什么 collect.py 的 `_PICK_SCROLLER` 在达人广场找不到滚动容器。

背景（2026-09-17 15:19 踩到）：
  登录态正常、四项筛选接口校验都通过，但 `LIST_SCROLLER_JS` 连续 20 次返回 null
  → 日志刷「等达人列表容器渲染…(20/20)」→「容器始终未出现」；
  随后 20 屏滚动全是「容器还没出现，等待中…」。
  但 `out/collect/nocontainer_ghq.png` 截图里**达人列表明明已经渲染出来了**。
  → 所以不是没数据，是**选择条件不匹配**。

`_PICK_SCROLLER` 的判定是：
    gap = scrollHeight - clientHeight
    要求 gap > 50 且 clientHeight >= 120
本探针把页面上**所有**有溢出（gap>0）的元素都 dump 出来，看清真实结构。

只读：不改筛选、不点达人、不发请求（除了页面自身加载）。
输出 out/probe_scroller/
用法：
    "$PY" .probe/probe_scroller_dump.py

⚠️ 写这个探针时踩到的坑（别重犯）：
   `collect.LIST_SCROLLER_JS` 本身就是完整的 `() => {...}`。
   若写成 `page.evaluate("() => {" + JS + "}")` —— 就变成「一个返回函数的函数」，
   Playwright 序列化不了函数 → 返回 null → **误判成「容器找不到」**，
   白折腾一轮。正确写法：`page.evaluate(C.LIST_SCROLLER_JS)`。
"""
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠️ 先 import collect —— 它在 import 时就把 sys.stdout 换成了 utf-8 的 TextIOWrapper。
#    **不要**再自己包一层：两个 TextIOWrapper 抢同一个 buffer，
#    先被 GC 的那个会把 buffer 关掉 -> 之后所有 print 报
#    「ValueError: I/O operation on closed file」（踩过两次了）。
sys.path.insert(0, BASE)
import collect as C  # noqa: E402  （直接用线上的 LIST_SCROLLER_JS / DUMP_OVERFLOW_JS）

OUT = os.path.join(BASE, "out", "probe_scroller")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
os.makedirs(OUT, exist_ok=True)


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# ① 环境信息：窗口/视口尺寸（怀疑窗口没最大化 -> 视口过小 -> clientHeight < 120 被判掉）
ENV_JS = """() => ({
    innerW: window.innerWidth, innerH: window.innerHeight,
    outerW: window.outerWidth, outerH: window.outerHeight,
    dpr: window.devicePixelRatio,
    docClientH: document.documentElement.clientHeight,
    docScrollH: document.documentElement.scrollHeight,
    bodyClientH: document.body.clientHeight,
    bodyScrollH: document.body.scrollHeight,
})"""

# ② 所有「有溢出」的元素（不做 clientHeight>=120 的过滤，就是为了看被过滤掉的是谁）
ALL_OVERFLOW_JS = """() => {
    const out = [];
    document.querySelectorAll('*').forEach(e => {
        const gap = e.scrollHeight - e.clientHeight;
        if (gap <= 0) return;
        const r = e.getBoundingClientRect();
        const cs = getComputedStyle(e);
        out.push({
            tag: e.tagName,
            cls: (e.className || '').toString().slice(0, 90),
            id: e.id || '',
            gap: gap,
            ch: e.clientHeight, sh: e.scrollHeight,
            w: Math.round(r.width), h: Math.round(r.height),
            x: Math.round(r.x), y: Math.round(r.y),
            ovY: cs.overflowY, pos: cs.position,
        });
    });
    out.sort((a, b) => b.gap - a.gap);
    return out.slice(0, 25);
}"""

# ③ 现有 _PICK_SCROLLER 的判定结果（**直接用 collect.py 的线上常量**，不复制）
PICK_JS = C.LIST_SCROLLER_JS

# ④ 如果有 overflow-y:auto/scroll 但 gap==0，说明是「虚拟列表」：内容用 transform 撑，
#    scrollHeight 永远等于 clientHeight -> 靠 gap 永远找不到。
VIRTUAL_HINT_JS = """() => {
    const hits = [];
    document.querySelectorAll('*').forEach(e => {
        const cs = getComputedStyle(e);
        if (cs.overflowY !== 'auto' && cs.overflowY !== 'scroll') return;
        const r = e.getBoundingClientRect();
        if (r.height < 120) return;
        hits.push({tag: e.tagName, cls: (e.className || '').toString().slice(0, 90),
                   gap: e.scrollHeight - e.clientHeight,
                   ch: e.clientHeight, sh: e.scrollHeight,
                   h: Math.round(r.height), y: Math.round(r.y)});
    });
    return hits;
}"""

# ⑤ 达人行数（确认列表真的渲染了）
ROWS_JS = """() => ({
    links: document.querySelectorAll('a[href*="daren-profile"], a[href*="uid="]').length,
    avatars: document.querySelectorAll('img[src*="aweme"], img[src*="avatar"]').length,
    tableBody: document.querySelectorAll('div.auxo-table-body').length,
    table: document.querySelectorAll('div.auxo-table').length,
    bodyLen: (document.body.innerText || '').length,
    bodyHead: (document.body.innerText || '').slice(0, 300),
})"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(14)
        page.screenshot(path=os.path.join(OUT, "01_loaded.png"))

        log("=" * 70)
        log("① 窗口 / 视口尺寸")
        try:
            env = page.evaluate(ENV_JS)
            log(json.dumps(env, ensure_ascii=False, indent=1))
        except Exception as e:
            log("  !! %s" % str(e)[:120])

        log("=" * 70)
        log("⑤ 列表渲染情况（证明列表在不在）")
        try:
            log(json.dumps(page.evaluate(ROWS_JS), ensure_ascii=False, indent=1)[:900])
        except Exception as e:
            log("  !! %s" % str(e)[:120])

        log("=" * 70)
        log("③ 现有 collect.py 的 _PICK_SCROLLER 判定结果")
        log("   （直接用 C.LIST_SCROLLER_JS。注意：它本身已是 `() => {...}`，")
        log("     **不能再包一层** —— 包了就变成「返回一个函数」，evaluate 序列化不了 → 假 null）")
        try:
            r = page.evaluate(PICK_JS)
            log("  -> %s" % ("null（真找不到容器）"
                             if r is None else json.dumps(r, ensure_ascii=False)))
        except Exception as e:
            log("  !! %s" % str(e)[:120])

        log("=" * 70)
        log("④ overflow-y:auto|scroll 且高度>=120 的元素（虚拟列表嫌疑）")
        try:
            for h in (page.evaluate(VIRTUAL_HINT_JS) or [])[:15]:
                log("  %s" % json.dumps(h, ensure_ascii=False))
        except Exception as e:
            log("  !! %s" % str(e)[:120])

        log("=" * 70)
        log("② 所有「有溢出」的元素 top25（gap 降序，看被 clientHeight>=120 过滤掉的是谁）")
        try:
            for h in (page.evaluate(ALL_OVERFLOW_JS) or []):
                log("  gap=%-7d ch=%-6d sh=%-7d %4dx%-5d @(%-5d,%-5d) ovY=%-7s %s%s"
                    % (h["gap"], h["ch"], h["sh"], h["w"], h["h"], h["x"], h["y"],
                       h["ovY"], h["tag"], ("." + h["cls"]) if h["cls"] else ""))
        except Exception as e:
            log("  !! %s" % str(e)[:120])

        page.screenshot(path=os.path.join(OUT, "02_final.png"))
        log("=" * 70)
        log("诊断结束；截图见 out/probe_scroller/")
        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
