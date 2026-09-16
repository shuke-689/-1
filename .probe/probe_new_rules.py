# -*- coding: utf-8 -*-
"""探测三条新规则所需的页面交互：
  A) 主推类目「个护家清 -> 个人护理」的多级菜单（规则1）
  B) 达人主页「带货分析」tab 与带货商品表结构（规则3）
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "probe_rules")
os.makedirs(OUT, exist_ok=True)
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
PROFILE_URL = ("https://buyin.jinritemai.com/dashboard/servicehall/"
               "daren-profile?uid=%s&enter_from=1&scene=1&author_type=1")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


DUMP_VISIBLE_JS = """() => {
    const out = [];
    document.querySelectorAll('div,li,span,a,button').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 24 || t.includes('\\n')) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 14 || r.width > 400 || r.height > 80) return;
        const st = getComputedStyle(e);
        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return;
        out.push({t: t, tag: e.tagName, x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height),
                  cls: (e.className||'').toString().slice(0, 90)});
    });
    return out;
}"""


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ----------------- A) 类目多级菜单 -----------------
        log("=" * 66)
        log("A) 打开达人广场，探测主推类目多级菜单")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        btns = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('button.auxo-btn, a.auxo-btn, div').forEach(e => {
                const t = (e.innerText||'').trim();
                if (t !== '个护家清') return;
                const r = e.getBoundingClientRect();
                if (r.y < 230 || r.y > 360 || r.width < 20 || r.height < 10) return;
                out.push({t:t, tag:e.tagName, x:Math.round(r.x), y:Math.round(r.y),
                          w:Math.round(r.width), h:Math.round(r.height),
                          cls:(e.className||'').toString().slice(0,80)});
            });
            return out;
        }""")
        log("  「个护家清」候选元素: %s" % json.dumps(btns, ensure_ascii=False))

        if btns:
            b = btns[0]
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(2.5)
            log("  已点击「个护家清」，截图 panel_after_click.png")
            page.screenshot(path=os.path.join(OUT, "panel_after_click.png"))

            vis = page.evaluate(DUMP_VISIBLE_JS)
            # 只保留 x 在类目面板一列附近、y 在 250-1000 的可点项
            panel = [v for v in vis if v["x"] > 500 and 240 < v["y"] < 1100]
            log("  面板可视元素 %d 个:" % len(panel))
            for v in panel[:60]:
                log("     %-4s x=%-5d y=%-5d w=%-4d h=%-3d %-24r %s" % (
                    v["tag"], v["x"], v["y"], v["w"], v["h"], v["t"][:22], v["cls"][:40]))

            # 找「个人护理」
            gr = [v for v in vis if v["t"] == "个人护理"]
            log("  「个人护理」候选: %s" % json.dumps(gr, ensure_ascii=False))
            if gr:
                g = gr[0]
                page.mouse.move(g["x"] + g["w"] / 2.0, g["y"] + g["h"] / 2.0)
                time.sleep(1.8)
                page.screenshot(path=os.path.join(OUT, "panel_hover_geren.png"))
                log("  已悬停「个人护理」，截图 panel_hover_geren.png")
                page.mouse.click(g["x"] + g["w"] / 2.0, g["y"] + g["h"] / 2.0)
                time.sleep(2.5)
                page.screenshot(path=os.path.join(OUT, "panel_after_geren.png"))
                applied = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('div.auxo-form-item, .auxo-select-selection-item').forEach(e => {
                        const t = (e.innerText||'').trim();
                        if (t && t.length < 40) out.push(t);
                    });
                    return out.slice(0, 20);
                }""")
                log("  点「个人护理」后筛选项回显: %s" % " | ".join(applied))
                cur = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('button.auxo-btn, a.auxo-btn').forEach(e => {
                        const r = e.getBoundingClientRect();
                        if (r.y < 230 || r.y > 360) return;
                        const t = (e.innerText||'').trim();
                        if (t) out.push(t + (('auxo-btn-secondary'===((e.className||'').match(/auxo-btn-secondary/)||[''])[0]) ? '[选中]' : ''));
                    });
                    return out;
                }""")
                log("  类目行当前按钮: %s" % " | ".join(cur))

        # ----------------- B) 达人主页「带货分析」 -----------------
        log("=" * 66)
        log("B) 打开一个达人主页，探测「带货分析」")
        uid = None
        try:
            ds = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
            uid = (ds[0] or {}).get("uid")
            log("  用例达人: %s uid=%s" % (ds[0].get("nickname"), uid))
        except Exception as e:
            log("  读取 darens.json 失败: %s" % e)

        if uid:
            page.goto(PROFILE_URL % uid, wait_until="domcontentloaded", timeout=90_000)
            time.sleep(6)
            page.screenshot(path=os.path.join(OUT, "profile_top.png"))

            vis = page.evaluate(DUMP_VISIBLE_JS)
            tabs = [v for v in vis if v["t"] in ("概览", "场景分析", "粉丝分析", "带货分析", "评价详情")]
            log("  找到 tab 候选 %d 个:" % len(tabs))
            for v in tabs:
                log("     %-6s x=%-5d y=%-5d w=%-4d h=%-3d %-10r %s" % (
                    v["tag"], v["x"], v["y"], v["w"], v["h"], v["t"], v["cls"][:50]))

            ga = [v for v in vis if v["t"] == "带货分析"]
            if ga:
                g = ga[0]
                page.mouse.click(g["x"] + g["w"] / 2.0, g["y"] + g["h"] / 2.0)
                time.sleep(4)
                page.screenshot(path=os.path.join(OUT, "profile_daihuo.png"))
                log("  已点「带货分析」，截图 profile_daihuo.png")

                # dump 表头 + 前若干行
                tbl = page.evaluate("""() => {
                    const res = {heads: [], rows: [], tables: []};
                    document.querySelectorAll('table').forEach((tb, ti) => {
                        const r = tb.getBoundingClientRect();
                        if (r.width < 200 || r.height < 50) return;
                        res.tables.push({i: ti, x: Math.round(r.x), y: Math.round(r.y),
                                         w: Math.round(r.width), h: Math.round(r.height),
                                         cls: (tb.className||'').toString().slice(0,80)});
                        const heads = Array.from(tb.querySelectorAll('th')).map(e => (e.innerText||'').trim());
                        if (heads.length) res.heads.push(heads);
                        Array.from(tb.querySelectorAll('tbody tr')).slice(0, 10).forEach(tr => {
                            const tds = Array.from(tr.querySelectorAll('td'))
                                .map(e => (e.innerText||'').trim().replace(/\\n+/g, ' / ').slice(0, 60));
                            if (tds.length) res.rows.push(tds);
                        });
                    });
                    return res;
                }""")
                log("  表格: %s" % json.dumps(tbl.get("tables"), ensure_ascii=False))
                log("  表头: %s" % json.dumps(tbl.get("heads"), ensure_ascii=False))
                log("  行样本:")
                for row in (tbl.get("rows") or [])[:8]:
                    log("     %s" % json.dumps(row, ensure_ascii=False))

                # 也 dump 一下「店铺名称」列附近的 DOM class
                shop = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('*').forEach(e => {
                        const t = (e.innerText||'').trim();
                        if (!/精选|优选|严选|专柜|旗舰/.test(t)) return;
                        if (t.length > 24) return;
                        const r = e.getBoundingClientRect();
                        if (r.width < 20 || r.width > 300 || r.height < 12) return;
                        out.push({t:t, cls:(e.className||'').toString().slice(0,90),
                                  x:Math.round(r.x), y:Math.round(r.y)});
                    });
                    return out.slice(0, 40);
                }""")
                log("  店铺名元素样本 %d 个:" % len(shop))
                for v in shop[:20]:
                    log("     x=%-5d y=%-5d %-22r %s" % (v["x"], v["y"], v["t"][:20], v["cls"][:50]))

        log("=" * 66)
        log("探测完成，截图在 %s" % OUT)
        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
