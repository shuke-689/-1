# -*- coding: utf-8 -*-
"""诊断：达人广场列表到底怎么才能真正触发「下一页」加载。

背景：collect.py 用 page.mouse.wheel 翻屏，结果不稳定 ——
  18:13 跑到 92 个达人（8 屏），18:16 只拿到 7 个（70 屏全无新增）。
说明鼠标滚轮没有可靠地作用在列表容器上。

本脚本依次实测 4 种方式，各自跑 6 轮，看接口响应条数是否增长：
  A. mouse.wheel（鼠标移到列表中心后滚）
  B. JS 直接改可滚动容器的 scrollTop
  C. 点击列表后按 End / PageDown
  D. 滚轮后强制等待更久

输出 out/probe_scroll/
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "probe_scroll")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
os.makedirs(OUT, exist_ok=True)


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# 找出真正可滚动的容器
FIND_SCROLLER_JS = """() => {
    let best = null, bestGap = 0;
    document.querySelectorAll('*').forEach(e => {
        const gap = e.scrollHeight - e.clientHeight;
        if (gap > bestGap && e.clientHeight > 200 && e.clientHeight < 2000) {
            bestGap = gap; best = e;
        }
    });
    if (!best) return null;
    const r = best.getBoundingClientRect();
    return {tag: best.tagName,
            cls: (best.className || '').toString().slice(0, 70),
            gap: bestGap, ch: best.clientHeight, sh: best.scrollHeight,
            top: best.scrollTop,
            box: {x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height)}};
}"""

SCROLL_JS = """(dy) => {
    let best = null, bestGap = 0;
    document.querySelectorAll('*').forEach(e => {
        const gap = e.scrollHeight - e.clientHeight;
        if (gap > bestGap && e.clientHeight > 200 && e.clientHeight < 2000) {
            bestGap = gap; best = e;
        }
    });
    if (!best) { window.scrollBy(0, dy); return {tag:'window', top: window.scrollY}; }
    best.scrollTop = best.scrollTop + dy;
    // 有些虚拟列表监听 wheel / scroll 事件，补发一次
    best.dispatchEvent(new WheelEvent('wheel', {deltaY: dy, bubbles: true}));
    best.dispatchEvent(new Event('scroll', {bubbles: true}));
    return {tag: best.tagName, cls: (best.className||'').toString().slice(0,40),
            top: best.scrollTop, sh: best.scrollHeight};
}"""

COUNT_ROWS_JS = """() => {
    // 页面上渲染出来的达人卡片/行数（粗略：找 uid 链接或头像块）
    const a = document.querySelectorAll('a[href*="daren-profile"], a[href*="uid="]');
    const img = document.querySelectorAll('img[src*="aweme"], img[src*="avatar"]');
    return {links: a.length, avatars: img.length,
            bodyLen: (document.body.innerText||'').length};
}"""


def main():
    from playwright.sync_api import sync_playwright

    apis = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                if "search_feed_author" in resp.url:
                    b = resp.text()
                    if b and b.strip().startswith("{"):
                        apis.append(json.loads(b))
            except Exception:
                pass
        page.on("response", on_response)

        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(12)
        page.screenshot(path=os.path.join(OUT, "01_loaded.png"))
        log("rows = %s" % page.evaluate(COUNT_ROWS_JS))

    # 第二轮：真正开始测
        def got():
            return sum(len((d.get("data") or {}).get("list") or []) for d in apis)

        log("初始接口响应 %d 条 / 达人 %d 个" % (len(apis), got()))
        sc = page.evaluate(FIND_SCROLLER_JS)
        log("可滚动容器: %s" % json.dumps(sc, ensure_ascii=False))

        def trial(name, fn, rounds=6, wait=3.0):
            before_n, before_got = len(apis), got()
            for i in range(rounds):
                try:
                    fn(i)
                except Exception as e:
                    log("  %s 第%d轮异常: %s" % (name, i + 1, str(e)[:80]))
                time.sleep(wait)
            after_n, after_got = len(apis), got()
            log(">>> [%s] 响应 %d->%d 条，达人 %d->%d 个 %s" % (
                name, before_n, after_n, before_got, after_got,
                "✅ 有效" if after_got > before_got else "❌ 无效"))
            return after_got - before_got

        # A) 鼠标移到列表中心再滚
        cx, cy = 1200, 800
        if sc:
            cx = sc["box"]["x"] + sc["box"]["w"] // 2
            cy = sc["box"]["y"] + sc["box"]["h"] // 2
        page.mouse.move(cx, cy)
        time.sleep(0.5)
        log("方式A：鼠标移到 (%d,%d) 后 wheel" % (cx, cy))

        def fa(i):
            page.mouse.wheel(0, 3600)
        trial("A mouse.wheel@列表中心", fa)

        # B) JS 直接改 scrollTop
        log("方式B：JS 改 scrollTop")

        def fb(i):
            r = page.evaluate(SCROLL_JS, 3000)
            if i == 0:
                log("    JS 返回: %s" % json.dumps(r, ensure_ascii=False))
        trial("B JS scrollTop", fb)

        # C) 点列表后按 End
        log("方式C：点击列表后按 End")

        def fc(i):
            if i == 0:
                page.mouse.click(cx, cy)
                time.sleep(0.6)
            page.keyboard.press("End")
        trial("C 键盘 End", fc)

        # D) 长时间等待 + 滚轮
        log("方式D：wheel + 6 秒长等待")

        def fd(i):
            page.mouse.wheel(0, 5000)
        trial("D wheel+长等待", fd, rounds=4, wait=6.0)

        page.screenshot(path=os.path.join(OUT, "02_final.png"))
        log("最终 rows = %s" % page.evaluate(COUNT_ROWS_JS))
        log("最终接口响应 %d 条 / 达人 %d 个" % (len(apis), got()))

        json.dump({"apis": len(apis), "daren": got()},
                  open(os.path.join(OUT, "result.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
