# -*- coding: utf-8 -*-
"""探针：为两条新规则取数据格式（用户 2026-09-17 追加）

规则A) 达人所带商品「店铺数 <= 2 家」-> 跳过
       需要「去重后的店铺数」。现有 r["shop_rows"] 只是**商品行数**，
       且 r["shops"] 被截断到 12 条 -> 必须新增字段，本次探针复核口径。

规则B) 所带商品「>= 90% 价格 < 30 元」-> 跳过
       需要带货分析表的「到手价」列原文。SHOP_ROWS_JS 目前只取 商品名/店铺名，
       本次探针把**整行所有 td** 原样 dump 出来，确认到手价的真实文本格式
       （形如 "¥9.9" / "9.9-19.9" / "9.9元" ？），并顺带抓接口看是否有数值源。

规则C) 商品含「充电宝 / 3C数码」-> 跳过（走关键词，不需要探针）

产出：out/probe_price/dump_<uid前8>.json  + 控制台摘要
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "probe_price")
os.makedirs(OUT, exist_ok=True)
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
PROFILE_URL = ("https://buyin.jinritemai.com/dashboard/servicehall/"
               "daren-profile?uid=%s&enter_from=1&scene=1&author_type=1")

# 找「带货分析」tab（与 collect.py 的 FIND_TAB_JS 同源）
FIND_TAB_JS = """(name) => {
    const out = [];
    const push = e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 90) return;
        if (r.y < 0 || r.y > 1200) return;
        out.push({x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height)});
    };
    document.querySelectorAll('div.auxo-tabs-tab-btn, div.auxo-tabs-tab').forEach(e => {
        if ((e.innerText||'').trim() === name) push(e);
    });
    if (out.length) return out;
    document.querySelectorAll('div,span,a,li').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        if (e.children.length > 1) return;
        push(e);
    });
    return out;
}"""

# 整行原样 dump：表头 + 每行的每个 td 文本（不截断列，只截断单元格长度）
DUMP_TABLE_JS = """() => {
    const res = {tables: []};
    document.querySelectorAll('table').forEach((tb, ti) => {
        const r = tb.getBoundingClientRect();
        if (r.width < 200 || r.height < 50) return;
        const heads = Array.from(tb.querySelectorAll('th')).map(e => (e.innerText||'').trim());
        const rows = [];
        Array.from(tb.querySelectorAll('tbody tr')).forEach(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(e =>
                (e.innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 120));
            if (tds.length) rows.push(tds);
        });
        res.tables.push({i: ti, w: Math.round(r.width), h: Math.round(r.height),
                         cls: (tb.className||'').toString().slice(0, 80),
                         heads: heads, nrows: rows.length, rows: rows.slice(0, 40)});
    });
    return res;
}"""


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def main():
    from playwright.sync_api import sync_playwright

    ds = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"),
                        encoding="utf-8"))
    # 挑前 2 个「有带货数据证据」的达人（titles 非空）
    cands = [r for r in ds if (r.get("titles") or [])][:2]
    if not cands:
        cands = ds[:2]
    log("待探达人 %d 个：%s" % (len(cands), " / ".join(x.get("nickname", "") for x in cands)))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 抓所有 square_pc_api 的 json 响应，找有没有带价格的商品接口
        hits = []

        def on_response(resp):
            try:
                u = resp.url
                if "square" not in u and "author" not in u:
                    return
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                body = resp.json()
                blob = json.dumps(body, ensure_ascii=False)
                if ("价格" in blob or "price" in blob.lower()) and len(blob) > 500:
                    hits.append({"url": u, "keys": list(body.keys()) if isinstance(body, dict) else None,
                                 "sample": blob[:6000]})
            except Exception:
                pass

        page.on("response", on_response)

        for r in cands:
            uid = r.get("uid")
            nick = r.get("nickname", "")
            log("=" * 60)
            log("达人 %s  现有 shop_rows(商品行数)=%s  现有shops(截断12)=%s" % (
                nick, r.get("shop_rows"), len(r.get("shops") or [])))
            try:
                page.goto(PROFILE_URL % uid, wait_until="domcontentloaded", timeout=90_000)
                time.sleep(7)

                tab = None
                for k in range(3):
                    tab = page.evaluate(FIND_TAB_JS, "带货分析")
                    if tab:
                        break
                    time.sleep(2.5)
                if not tab:
                    log("  ! 未找到「带货分析」tab")
                    continue
                t0 = tab[0]
                page.mouse.click(t0["x"] + t0["w"] / 2.0, t0["y"] + t0["h"] / 2.0)
                time.sleep(6)

                dump = page.evaluate(DUMP_TABLE_JS)
                tag = (uid or "x")[:8]
                path = os.path.join(OUT, "dump_%s.json" % tag)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(dump, f, ensure_ascii=False, indent=1)
                log("  已存 %s" % path)

                for tb in dump.get("tables", []):
                    if tb["nrows"] == 0 and not tb["heads"]:
                        continue
                    log("  表#%d %dx%d 行数=%d" % (tb["i"], tb["w"], tb["h"], tb["nrows"]))
                    log("    表头: %s" % json.dumps(tb["heads"], ensure_ascii=False))
                    for row in tb["rows"][:6]:
                        log("    行: %s" % json.dumps(row, ensure_ascii=False))
                    break
                page.screenshot(path=os.path.join(OUT, "shot_%s.png" % tag))
            except Exception as e:
                log("  ! 异常: %s" % str(e)[:200])

        log("=" * 60)
        log("接口命中 %d 条" % len(hits))
        for h in hits[:3]:
            log("  URL: %s" % h["url"][:160])
            log("  keys: %s" % h["keys"])
            log("  sample: %s" % h["sample"][:900])
        if hits:
            with open(os.path.join(OUT, "api_hits.json"), "w", encoding="utf-8") as f:
                json.dump(hits, f, ensure_ascii=False, indent=1)
            log("  已存 out/probe_price/api_hits.json")

        log("探测完成 -> %s" % OUT)
        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
