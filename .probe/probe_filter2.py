# -*- coding: utf-8 -*-
"""摸清「找达人」筛选栏的真实交互：
1. 主推类目 = 直接可见的多选按钮（已验证）
2. 视频结算总额 / 粉丝量 / 有联系方式 点开后的真实选项文本
3. 筛选后收割 search_feed_author 接口，核对区间是否真的生效
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

# 屏幕上所有「短文本 + 可点击/浮层」候选，用于发现面板选项
VISIBLE_JS = """() => {
    const out = [];
    document.querySelectorAll('*').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 24 || t.includes('\\n')) return;
        const r = e.getBoundingClientRect();
        if (r.width < 8 || r.height < 8 || r.height > 70) return;
        if (r.y < 0 || r.y > 2100 || r.x < 500) return;
        out.push({t:t, x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height),
                  cls:(e.className||'').toString().slice(0,80)});
    });
    return out;
}"""


def dump(log, title, ymin=0):
    d = page.evaluate(VISIBLE_JS) if False else None


def main():
    global page
    from playwright.sync_api import sync_playwright

    apis = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_resp(resp):
            try:
                if "search_feed_author" in resp.url:
                    b = resp.text()
                    if b:
                        apis.append(json.loads(b))
            except Exception:
                pass

        page.on("response", on_resp)

        def visible(ymin=0, ymax=2100, xmin=500):
            return [d for d in page.evaluate(VISIBLE_JS)
                    if ymin <= d["y"] <= ymax and d["x"] >= xmin]

        def show(items, tag, limit=60):
            print("  -- %s (%d) --" % (tag, len(items)))
            seen = set()
            for it in items[:limit]:
                k = (it["t"], round(it["x"] / 20), round(it["y"] / 20))
                if k in seen:
                    continue
                seen.add(k)
                print("     y=%-5d x=%-5d w=%-4d %-26s | %s" % (
                    it["y"], it["x"], it["w"], it["t"][:26], it["cls"][:62]))

        def click_exact(text, ymin=200, ymax=560, cls_kw=None):
            """精确文本点击：返回实际点击的矩形"""
            hits = page.evaluate("""(args) => {
                const [name, ymin, ymax, kw] = args;
                const out = [];
                document.querySelectorAll('*').forEach(e => {
                    const cls = (e.className||'').toString();
                    if (kw && !cls.includes(kw)) return;
                    if (!kw && !/auxo-btn|auxo-form-item|auxo-radio|auxo-checkbox/.test(cls)) return;
                    const t = (e.innerText||'').trim();
                    if (t !== name) return;
                    const r = e.getBoundingClientRect();
                    if (r.y < ymin || r.y > ymax || r.width < 8 || r.height < 8) return;
                    out.push({x:Math.round(r.x), y:Math.round(r.y),
                              w:Math.round(r.width), h:Math.round(r.height),
                              cls:cls.slice(0,90)});
                });
                return out;
            }""", [text, ymin, ymax, cls_kw])
            if not hits:
                print("     !! 没找到精确文本: %s" % text)
                return None
            h = hits[0]
            print("     点击 '%s' @(%d,%d) cls=%s" % (text, h["x"] + h["w"] // 2,
                                                   h["y"] + h["h"] // 2, h["cls"][:60]))
            page.mouse.click(h["x"] + h["w"] / 2, h["y"] + h["h"] / 2)
            time.sleep(1.6)
            return h

        print("=" * 74)
        print("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)
        print("  初始筛选栏:")
        show(visible(260, 430), "filter bar")

        print()
        print("=" * 74)
        print("[1] 主推类目 -> 点「个护家清」按钮")
        click_exact("个护家清", 260, 300)
        time.sleep(3)
        print("  表格前 3 行（点后）:")
        show(visible(560, 800), "rows", 30)

        print()
        print("[2] 再点「美妆」（验证多选）")
        click_exact("美妆", 260, 300)
        time.sleep(3)
        apis.clear()

        print()
        print("=" * 74)
        print("[3] 视频结算总额 -> 看面板选项")
        click_exact("视频结算总额", 340, 380)
        time.sleep(1.5)
        show(visible(300, 1000), "after click 视频结算总额", 80)

        print()
        print("=" * 74)
        print("[4] 粉丝量 -> 看面板选项")
        page.keyboard.press("Escape")
        time.sleep(0.6)
        click_exact("粉丝量", 390, 420)
        time.sleep(1.5)
        show(visible(300, 1000), "after click 粉丝量", 80)

        print()
        print("=" * 74)
        print("[5] 有联系方式 -> 看是否直接生效")
        page.keyboard.press("Escape")
        time.sleep(0.6)
        click_exact("有联系方式", 390, 420)
        time.sleep(3)
        show(visible(260, 440), "filter bar after 有联系方式", 80)

        print()
        print("=" * 74)
        print("[6] 收割接口响应，核对筛选是否生效")
        for s in range(3):
            page.mouse.wheel(0, 3000)
            time.sleep(2.2)
        print("  接口响应 %d 条" % len(apis))
        for d in apis:
            for a in (d.get("data") or {}).get("list") or []:
                ab = a.get("author_base") or {}
                si = (a.get("sale_info") or {}).get("video_total_sales_settle") or {}
                print("     %-22s fans=%-8s gender=%-3s city=%-10s videoSettle=%s-%s cate=%s" % (
                    (ab.get("nickname") or "")[:20], ab.get("fans_num"), ab.get("gender"),
                    ab.get("city") or "", si.get("sale_low"), si.get("sale_high"),
                    ab.get("author_level")))
            break

        print()
        print("  当前筛选栏回显:")
        show(visible(260, 440), "final filter bar", 80)

        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
