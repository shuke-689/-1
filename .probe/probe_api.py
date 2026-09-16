# -*- coding: utf-8 -*-
"""探针：从页面加载起抓全部 search_feed_author 请求体 + 响应概况。

用途：拿到站点真实的 filters 结构（类目 id / 结算总额区间 / 粉丝量 / 有联系方式），
      并对比「类目=个护家清」与「类目=美妆」两条路径的返回差异。

用法：
  python .probe/probe_api.py 个护家清
  python .probe/probe_api.py 美妆
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

PARENT = sys.argv[1] if len(sys.argv) > 1 else "个护家清"
LOGJ = os.path.join(BASE, "out", "probe_api_%s.json" % PARENT)


def main():
    from playwright.sync_api import sync_playwright
    recs = []
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
                body = resp.text() or "{}"
                obj = json.loads(body)
                lst = (obj.get("data") or {}).get("list") or []
                cates = []
                for a in lst[:6]:
                    at = (a.get("author_tag") or {}).get("main_cate") or []
                    cates.append("/".join(at))
                recs.append({
                    "url": resp.url.split("?")[0],
                    "payload": pd,
                    "status": resp.status,
                    "code": obj.get("code"),
                    "msg": (obj.get("msg") or obj.get("message") or "")[:120],
                    "n": len(lst),
                    "sample_cates": cates,
                })
            except Exception as e:
                recs.append({"url": resp.url.split("?")[0], "error": str(e)[:120]})

        page.on("response", on_response)

        def show(tag):
            print("\n===== %s =====" % tag)
            for r in recs:
                if r.get("error"):
                    print("  [ERR]", r["error"])
                    continue
                print("  page=%s n=%d code=%s msg=%s"
                      % ((json.loads(r["payload"] or "{}") or {}).get("page"), r["n"],
                         r.get("code"), r.get("msg")))
                print("     cates:", r.get("sample_cates"))
                if r.get("payload"):
                    print("     filters:", json.dumps(
                        (json.loads(r["payload"]) or {}).get("filters"),
                        ensure_ascii=False)[:900])

        print("打开达人广场…")
        page.goto(C.DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(11)
        show("① 页面加载完成（默认）")

        recs.clear()
        hits = page.evaluate(C.FIND_CATE_JS, PARENT)
        print("\n类目按钮 %s: %s" % (PARENT, bool(hits)))
        if hits:
            page.mouse.click(hits[0]["x"] + hits[0]["w"] / 2.0,
                             hits[0]["y"] + hits[0]["h"] / 2.0)
            time.sleep(2.4)
            sub = page.evaluate(C.FIND_CASCADER_JS, "不限")
            print("  级联「不限」:", sub)
            if sub:
                page.mouse.click(sub["x"] + sub["w"] / 2.0, sub["y"] + sub["h"] / 2.0)
                time.sleep(4.0)
            page.keyboard.press("Escape")
            time.sleep(2.0)
        show("② 选完类目 %s/不限 之后" % PARENT)

        json.dump(recs, open(LOGJ, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("\n已存", LOGJ)
        time.sleep(1.5)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
