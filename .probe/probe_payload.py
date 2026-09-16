# -*- coding: utf-8 -*-
"""探针：抓 search_feed_author 请求体，看站点实际发出去的筛选参数。

对比「无筛选」/「+美妆类目」两态的 POST payload，即可确定：
  · 类目筛选到底有没有生效、发的是什么 id
  · 结算总额 / 粉丝量 / 有联系方式 分别对应哪个字段
用法：
  python .probe/probe_payload.py [类目名]
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

import collect as C  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PARENT = sys.argv[1] if len(sys.argv) > 1 else "美妆"


def main():
    from playwright.sync_api import sync_playwright
    reqs = []      # [(url, post_data, n_items)]
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                if "search_feed_author" not in resp.url:
                    return
                pd = resp.request.post_data
                try:
                    n = len((json.loads(resp.text() or "{}").get("data") or {}).get("list") or [])
                except Exception:
                    n = -1
                reqs.append((resp.url.split("?")[0], pd, n))
            except Exception:
                pass

        page.on("response", on_response)

        def click_box(b):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(1.4)

        def to_top():
            try:
                page.evaluate("""() => { window.scrollTo(0,0);
                    document.querySelectorAll('*').forEach(e => {
                        if (e.scrollHeight - e.clientHeight > 50) e.scrollTop = 0; }); }""")
            except Exception:
                pass
            time.sleep(1.2)

        def spin(label, max_show=4):
            to_top()
            reqs.clear()
            for _ in range(3):
                try:
                    info = page.evaluate(C.SCROLL_LIST_JS, 3600)
                    if info:
                        page.mouse.move(info["cx"], info["cy"])
                        time.sleep(0.15)
                        page.mouse.wheel(0, 3600)
                except Exception:
                    pass
                time.sleep(2.6)
            print("\n===== %s =====" % label)
            if not reqs:
                print("  (没有 search_feed_author 请求)")
            for url, pd, n in reqs[:max_show]:
                print("  %s  -> list=%d" % (url, n))
                if pd:
                    try:
                        obj = json.loads(pd)
                        print("  payload:", json.dumps(obj, ensure_ascii=False)[:1500])
                    except Exception:
                        print("  payload(raw):", str(pd)[:1500])

        print("打开达人广场…")
        page.goto(C.DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        # 关键：**先应用筛选，再滚动**。滚过之后筛选栏坐标会漂，
        # 再去找类目按钮就会「未找到」（这个坑探针踩过两次）。
        hits = page.evaluate(C.FIND_CATE_JS, PARENT)
        print("找到类目按钮 %s: %s" % (PARENT, hits))
        if hits:
            click_box(hits[0])
            time.sleep(2.4)
            sub = page.evaluate(C.FIND_CASCADER_JS, "不限")
            print("  级联面板「不限」:", sub)
            if sub:
                click_box(sub)
                time.sleep(2.6)
            page.keyboard.press("Escape")
            time.sleep(1.5)
            shown = page.evaluate("""() => {const o=[];document.querySelectorAll('*').forEach(e=>{
                const t=(e.innerText||'').trim();
                if(/^已选/.test(t)&&t.length<400)o.push(t);});return o.slice(0,1);}""")
            print("  已选:", (shown[0].replace("\n", " ") if shown else "(未捕获)")[:300])
        spin("① +类目 %s/不限" % PARENT)

        json.dump([{"url": u, "payload": d, "list": n} for u, d, n in reqs],
                  open(os.path.join(BASE, "out", "probe_payload.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=2)
        print("\n已存 out/probe_payload.json")
        time.sleep(1.5)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
