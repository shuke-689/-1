# -*- coding: utf-8 -*-
"""探针：逐个累加筛选条件，看每一步的达人结果数。

目的：查清「美妆 + 结算总额1w-10w + 粉丝量10w以下 + 有联系方式」为什么是 0 个，
      而「个护家清 + 同样条件」有 292 个。

做法：一次浏览器会话内，按顺序累加筛选条件，每加一个就滚一次并统计列表接口返回的达人数。
用法：
  python .probe/probe_filters.py 美妆
  python .probe/probe_filters.py 个护家清
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
    apis = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                if "search_feed_author" in resp.url:
                    b = resp.text()
                    if b:
                        apis.append(json.loads(b))
            except Exception:
                pass

        page.on("response", on_response)

        def click_box(b):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(1.4)

        def to_top():
            """回到顶部：筛选栏的坐标是相对视口的，滚过之后 y 会偏，
            不先复位就会出现「未找到类目按钮」这种假失败。"""
            try:
                page.evaluate("""() => {
                    window.scrollTo(0, 0);
                    document.querySelectorAll('*').forEach(e => {
                        if (e.scrollHeight - e.clientHeight > 50) e.scrollTop = 0;
                    });
                }""")
            except Exception:
                pass
            time.sleep(1.3)

        def dropdown():
            return page.evaluate(C.DROPDOWN_JS)

        def apply_formitem(name, option):
            for _ in range(3):
                to_top()
                page.keyboard.press("Escape")
                time.sleep(0.5)
                box = page.evaluate(C.FIND_FORMITEM_JS, name)
                if not box:
                    print("    未找到筛选项", name)
                    time.sleep(1.0)
                    continue
                click_box(box)
                dd = dropdown()
                if not dd or not dd["items"]:
                    print("    %s -> 开关型，已切换" % name)
                    return True
                if option is None:
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
                    return True
                hit = next((i for i in dd["items"] if i["t"] == option), None)
                if not hit:
                    page.keyboard.press("Escape")
                    time.sleep(0.8)
                    continue
                click_box(hit)
                page.keyboard.press("Escape")
                time.sleep(0.8)
                print("    %s -> %s OK" % (name, option))
                return True
            return False

        def apply_cate(parent, child="不限"):
            for _ in range(3):
                to_top()
                page.keyboard.press("Escape")
                time.sleep(0.6)
                hits = page.evaluate(C.FIND_CATE_JS, parent)
                if not hits:
                    print("    未找到类目按钮", parent)
                    time.sleep(1.2)
                    continue
                click_box(hits[0])
                time.sleep(2.4)
                sub = page.evaluate(C.FIND_CASCADER_JS, child)
                if not sub:
                    page.keyboard.press("Escape")
                    time.sleep(1.2)
                    continue
                click_box(sub)
                time.sleep(2.6)
                page.keyboard.press("Escape")
                time.sleep(0.8)
                print("    类目 %s/%s 已选" % (parent, child))
                return True
            return False

        def probe(label):
            """滚几屏，统计接口回来的达人数 + 页面空态文案。"""
            apis.clear()
            time.sleep(2.5)
            seen = 0
            for _ in range(4):
                try:
                    info = page.evaluate(C.SCROLL_LIST_JS, 3600)
                    if info:
                        page.mouse.move(info["cx"], info["cy"])
                        time.sleep(0.15)
                        page.mouse.wheel(0, 3600)
                except Exception:
                    pass
                time.sleep(2.6)
                n = sum(len((d.get("data") or {}).get("list") or []) for d in apis)
                if n and n == seen:
                    break
                seen = n
            try:
                empty_hint = page.evaluate(
                    "() => /未找到相关达人|暂无数据/.test(document.body.innerText)")
                chip = page.evaluate(
                    "() => {const o=[];document.querySelectorAll('*').forEach(e=>{"
                    "const t=(e.innerText||'').trim();"
                    "if(/^已选/.test(t)&&t.length<400)o.push(t);});return o.slice(0,1);}")
            except Exception:
                empty_hint, chip = None, []
            print("  >>> %-28s 接口响应 %-3d 条 / 达人 %-4d 篇 | 页面空态=%s"
                  % (label, len(apis), seen, empty_hint))
            if chip:
                print("      已选:", chip[0].replace("\n", " ")[:300])
            to_top()

        print("打开达人广场…")
        page.goto(C.DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        probe("① 无条件（默认列表）")
        print("应用类目:", PARENT)
        apply_cate(PARENT)
        time.sleep(3)
        probe("② +类目 %s" % PARENT)

        print("应用: 结算总额 = 1w-10w")
        apply_formitem("结算总额", "1w-10w")
        time.sleep(3)
        probe("③ +结算总额 1w-10w")

        print("应用: 粉丝量 = 10w以下")
        apply_formitem("粉丝量", "10w以下")
        time.sleep(3)
        probe("④ +粉丝量 10w以下")

        print("应用: 有联系方式")
        apply_formitem("有联系方式", None)
        time.sleep(3)
        probe("⑤ +有联系方式")

        json.dump(apis, open(os.path.join(BASE, "out", "probe_filters.json"), "w",
                             encoding="utf-8"), ensure_ascii=False)
        print("原始接口响应已存 out/probe_filters.json")
        time.sleep(2)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
