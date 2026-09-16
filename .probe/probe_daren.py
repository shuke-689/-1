# -*- coding: utf-8 -*-
"""探针：打开一个达人主页 -> 点「带货分析」->  dump 表格表头 + 前几行。

用途：确认「带货分析」表格的列名（商品名 / 店铺名在哪一列），
以便实现「商品名含 假发/院线/美甲 则排除」的新规则。

用法：
  python .probe/probe_daren.py [uid]
不传 uid 时取 out/collect/darens_ghq.json 里带货件数最多的那个（用 --pick 自动挑）。
"""
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

import collect as C  # noqa: E402

# 注意：collect.py 在 import 时会把 sys.stdout 换成新的 TextIOWrapper。
# 必须在 import 之后再 reconfigure，否则旧 wrapper 被 GC 时会关掉底层 buffer
# （踩过：ValueError: I/O operation on closed file）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUTJ = os.path.join(BASE, "out", "probe_daren.json")

DUMP_JS = """() => {
    const out = [];
    document.querySelectorAll('table').forEach((tb, ti) => {
        const r = tb.getBoundingClientRect();
        const heads = Array.from(tb.querySelectorAll('th')).map(e => (e.innerText||'').trim());
        const rows = [];
        tb.querySelectorAll('tbody tr').forEach(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(e =>
                (e.innerText||'').trim().replace(/\\n+/g, ' ').slice(0, 60));
            if (tds.length) rows.push(tds);
        });
        if (!heads.length && !rows.length) return;
        out.push({idx: ti, w: Math.round(r.width), h: Math.round(r.height),
                  heads: heads, rows: rows.slice(0, 6), nrows: rows.length});
    });
    return out;
}"""


def pick_uid():
    jp = os.path.join(BASE, "out", "collect", "darens_ghq.json")
    if not os.path.exists(jp):
        return None
    data = json.load(open(jp, encoding="utf-8"))
    data = [d for d in data if d.get("shop_rows")]
    data.sort(key=lambda d: -(d.get("shop_rows") or 0))
    return data[0]["uid"] if data else (json.load(open(jp, encoding="utf-8")) or [{}])[0].get("uid")


def main():
    uid = sys.argv[1] if len(sys.argv) > 1 else pick_uid()
    if not uid:
        print("没有 uid")
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("打开达人主页:", uid[:24])
        page.goto(C.PROFILE_URL % uid, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(5)
        tab = None
        for k in range(4):
            tab = page.evaluate(C.FIND_TAB_JS, "带货分析")
            if tab:
                break
            print("  等 tab…", k + 1)
            page.evaluate("() => window.scrollTo(0,0)")
            time.sleep(2.5)
        if not tab:
            print("!! 没找到「带货分析」tab")
        else:
            t0 = tab[0]
            page.mouse.click(t0["x"] + t0["w"] / 2.0, t0["y"] + t0["h"] / 2.0)
            time.sleep(5)
        dump = page.evaluate(DUMP_JS)
        json.dump(dump, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        for t in dump:
            print("--- table #%d  %dx%d  rows=%d" % (t["idx"], t["w"], t["h"], t["nrows"]))
            print("    heads:", t["heads"])
            for r in t["rows"][:3]:
                print("    row  :", r)
        print("已存", OUTJ)
        time.sleep(2)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
