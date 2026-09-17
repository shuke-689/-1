# -*- coding: utf-8 -*-
"""探针：确认「直播结算总额」区间筛选能否多选，以及多选后接口 payload 的取值格式。

背景
----
用户 2026-09-16 要求把筛选从「结算总额 = 1w-10w」改成「直播结算总额 = 5000-10w」。
但平台下拉只有 6 档（1w以下 / 1w-10w / 10w-100w / 100w-500w / 500w-1000w / 1000w以上），
**没有 5000 这一档**。而达人记录里的 `live_total_sales_settle` 是数值区间
（如 {'low':5000,'high':10000}），粒度足够。

所以「5000-10w」只能这样实现：
  平台侧勾选【1w以下】+【1w-10w】 -> 得到一个 [0,10w] 的超集
  本地再按数值剔掉 <5000 的
但前提是**下拉支持多选**。本探针就是来验证这一点：
  1. 点开「直播结算总额」，看下拉容器是否带 multiple 特征；
  2. 依次点【1w以下】【1w-10w】，看第一次点击后下拉是否仍开着、是否出现两个 selected；
  3. 抓 search_feed_author 请求 payload，看该字段到底传了什么数组。

不做任何写入，只读探查。用完把 Edge 关掉。
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
OUTP = os.path.join(BASE, "out", "probe_sale_ms.json")

from playwright.sync_api import sync_playwright  # noqa: E402

LOGGED_IN_MARK = ("主推类目", "找达人", "按商品找达人")
TARGET = os.environ.get("PROBE_LABEL", "直播结算总额")


def extract_js(name):
    """从 collect.py 里抠出指定的 JS 常量（避免 import collect 触发它模块级的 stdout 改写）。"""
    src = open(os.path.join(BASE, "collect.py"), encoding="utf-8").read()
    m = re.search(name + r'\s*=\s*"""(.*?)"""', src, re.S)
    if not m:
        raise RuntimeError("collect.py 里没找到 %s" % name)
    return m.group(1)


FIND_FORMITEM_JS = extract_js("FIND_FORMITEM_JS")
DROPDOWN_JS = extract_js("DROPDOWN_JS")

# 额外的：看下拉容器自身带不带多选特征
DD_META_JS = """() => {
    const dds = Array.from(document.querySelectorAll('.auxo-select-dropdown'))
        .filter(e => e.getBoundingClientRect().height > 10);
    if (!dds.length) return null;
    const dd = dds[dds.length - 1];
    // 往上找这个下拉对应的 select 容器
    let holder = dd.closest('.auxo-select-dropdown') ;
    const sels = Array.from(document.querySelectorAll('.auxo-select')).map(e => ({
        cls: (e.className||'').toString().slice(0,200),
        text: (e.innerText||'').trim().slice(0,60)
    }));
    return {
        dd_cls: (dd.className||'').toString(),
        dd_html_len: (dd.innerHTML||'').length,
        multi_dd: /multiple/i.test((dd.className||'').toString()),
        multi_selects: sels.filter(s => /-multiple/.test(s.cls)),
        all_selects_cls: Array.from(new Set(sels.map(s => s.cls))).slice(0, 10),
    };
}"""


def main():
    rec = {"label": TARGET, "steps": []}

    def note(msg, **kw):
        line = {"msg": msg}
        line.update(kw)
        rec["steps"].append(line)
        print("[probe] " + msg, flush=True)

    reqs = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req):
            if "search_feed_author" in req.url:
                try:
                    reqs.append(req.post_data or "")
                except Exception:
                    pass

        page.on("request", on_request)

        page.goto(DAREN, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        time.sleep(3)

        body = ""
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        except Exception as e:
            note("读 body 失败: %s" % e)
        hit = [m for m in LOGGED_IN_MARK if m in body]
        if not hit:
            note("!! 未登录精选联盟（body 里没有 %s）-> 中止，不自动登录" % (LOGGED_IN_MARK,),
                 body_head=body[:300])
            rec["ok"] = False
            json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            ctx.close()
            return
        note("登录态 OK（命中 %s）" % "/".join(hit))

        # --- 1. 找到目标 form-item ---
        box = page.evaluate(FIND_FORMITEM_JS, TARGET)
        if not box:
            note("!! 没找到筛选项「%s」" % TARGET)
            rec["ok"] = False
            json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            ctx.close()
            return
        note("找到「%s」@(%s,%s) %s" % (TARGET, box.get("x"), box.get("y"), box.get("cls", "")[:60]),
             box=box)

        def dd_now(tag):
            d = page.evaluate(DROPDOWN_JS)
            meta = page.evaluate(DD_META_JS)
            if d:
                note("%s 下拉 items=%s" % (tag, [(i["t"], i["selected"]) for i in d["items"]]))
            else:
                note("%s 没有可见下拉（可能已关闭）" % tag)
            if meta:
                note("%s 下拉元信息" % tag, **meta)
            return d, meta

        # --- 2. 点开下拉 ---
        page.mouse.click(box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0)
        time.sleep(2)
        d1, m1 = dd_now("首次点开")
        if not d1:
            note("!! 点开后没出现下拉，无法继续")
            rec["ok"] = False
            json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            ctx.close()
            return

        def click_opt(text, d):
            it = next((i for i in d["items"] if i["t"] == text), None)
            if not it:
                note("!! 下拉里没有「%s」" % text)
                return False
            page.mouse.click(it["x"] + it["w"] / 2.0, it["y"] + it["h"] / 2.0)
            time.sleep(2)
            return True

        # --- 3. 选第一个（1w以下） ---
        if click_opt("1w以下", d1):
            note("已点击「1w以下」")
            d2, m2 = dd_now("选完 1w以下")
        else:
            d2 = None

        # --- 4. 不按 Esc，直接再选 1w-10w，看能不能叠加 ---
        if d2:
            if click_opt("1w-10w", d2):
                note("已点击「1w-10w」（未按 Esc，测试能否叠加）")
                d3, m3 = dd_now("选完 1w-10w（第二轮）")
            else:
                d3 = None
        else:
            d3 = None

        # 关掉下拉
        page.keyboard.press("Escape")
        time.sleep(1.5)

        # --- 5. 看 form-item 现在的回显 ---
        after = page.evaluate(FIND_FORMITEM_JS, TARGET)
        note("筛选后「%s」按钮回显 = %r" % (TARGET, (after or {}).get("text") or (after or {}).get("t")),
             after=after)

        # 再点一次空白处触发请求
        try:
            page.mouse.click(30, 400)
            time.sleep(3)
        except Exception:
            pass

        rec["requests"] = reqs
        note("抓到 search_feed_author 请求 %d 条" % len(reqs))
        for i, q in enumerate(reqs):
            try:
                j = json.loads(q)
                filt = (j.get("filters") or {})
                keys = {k: v for k, v in filt.items()
                        if "settle" in k and v}
                note("请求#%d filters 里非空的 settle 字段 = %s" % (i, keys))
            except Exception as e:
                note("请求#%d 解析失败: %s" % (i, e))

        rec["ok"] = True
        json.dump(rec, open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("[probe] 结果已写入 %s" % OUTP, flush=True)
        ctx.close()


if __name__ == "__main__":
    main()
