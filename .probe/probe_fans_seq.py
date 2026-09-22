# -*- coding: utf-8 -*-
"""探针：平台改版排查（2026-09-22）。

背景：2026-09-22 试采 10 个时退出码 2，日志：
    [sale] 直播结算总额 -> 1w-10w OK
    [fans] 未找到筛选项 粉丝量   x3          <- 新问题
    [contact] 有联系方式 -> 直接切换 OK
    [portrait] 面板里没找到子项 达人性别 x3   <- 旧功能变坏了
    [fansg]    面板里没找到子项 粉丝性别 x3
而单独跑 .probe/probe_agg.py 时两条 agg 都能成功（payload 里 author_gender/fans_gender 都是 ["2"]）
-> 说明 agg 面板本身没坏，是**序列里的状态串扰**。

本探针只做只读侦察，回答两件事：
  A. 「粉丝量」还在不在？不在的话替代项「粉丝指数」有哪些选项？
  B. 达人画像 agg 面板在什么条件下点不开？
     ① 干净页面上直接点（基线，应当成功）
     ② 先应用「直播结算总额 = 1w-10w」再点（复现 collect.py 的顺序）
     ③ 再叠一个「有联系方式」开关后点

⚠️ 不复制 JS 字符串，用 ast 从 collect.py 抠真实常量（踩过的坑：探针自己抄一份会得出假结论）。
⚠️ 不能 import collect（它会替换 sys.stdout，另加一层会 I/O on closed file）。

跑法：source tools/env.sh && "$PY" .probe/probe_fans_seq.py
"""
import ast
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
SHOT = os.path.join(BASE, "out", "probe_fans_seq.png")

WANT = ("FIND_FORMITEM_JS", "CLICK_FORMITEM_JS", "ALL_DROPDOWNS_JS", "CLOSE_DROPDOWN_JS",
        "DUMP_AGG_JS", "FIND_AGG_SUBSELECT_JS", "FORMITEM_TEXT_JS", "DUMP_POPOVERS_JS")

# 候选标签：老口径 vs 疑似新口径
CANDIDATE_LABELS = ("粉丝量", "粉丝指数", "达人等级", "达人画像", "粉丝画像",
                    "粉丝偏好", "有联系方式")


def log(m):
    print(m, flush=True)


def load_js():
    src = io.open(os.path.join(BASE, "collect.py"), encoding="utf-8").read()
    found = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in WANT:
                try:
                    found[t.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    missing = [w for w in WANT if w not in found]
    if missing:
        log("!! 没抠到常量: %s" % missing)
        sys.exit(1)
    log("已从 collect.py 抠到 %d 个 JS 常量" % len(found))
    return found


def main():
    J = load_js()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            viewport={"width": 2552, "height": 1262},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def click_box(b, pause=1.4):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(pause)

        def close_dropdowns(max_round=3):
            for _ in range(max_round):
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    if not (page.evaluate(J["ALL_DROPDOWNS_JS"]) or []):
                        return True
                    if not page.evaluate(J["CLOSE_DROPDOWN_JS"]):
                        return True
                except Exception:
                    pass
                time.sleep(0.3)
            return True

        def open_dds():
            try:
                return page.evaluate(J["ALL_DROPDOWNS_JS"]) or []
            except Exception:
                return []

        def agg_panels():
            try:
                return page.evaluate(J["DUMP_AGG_JS"]) or []
            except Exception:
                return []

        def agg_report(tag):
            ds = agg_panels()
            if not ds:
                log("  [%s] agg 面板: **0 个**（点不开）" % tag)
                return
            for d in ds[:2]:
                log("  [%s] agg 面板: box=%s rows=%s text=%r"
                    % (tag, d.get("box"), d.get("rows"), (d.get("text") or "")[:100]))

        def try_open_portrait(tag):
            """点「达人画像」看面板开不开。"""
            close_dropdowns()
            b = page.evaluate(J["FIND_FORMITEM_JS"], "达人画像")
            if not b:
                log("  [%s] 找不到「达人画像」form-item" % tag)
                return None
            log("  [%s] 「达人画像」box=%s -> 点击" % (tag, b))
            click_box(b, 1.8)
            agg_report(tag)
            sub = page.evaluate(J["FIND_AGG_SUBSELECT_JS"], "达人性别")
            log("  [%s] 面板子项「达人性别」: %s"
                % (tag, ("@%s,%s %s" % (sub["x"], sub["y"], sub.get("cls"))) if sub else "**没找到**"))
            return sub

        def apply_sale(option="1w-10w"):
            """复刻 collect.py 的 apply_formitem(SALE_LABEL, option, 'sale')。"""
            close_dropdowns()
            b = page.evaluate(J["FIND_FORMITEM_JS"], "直播结算总额")
            if not b:
                log("  [sale] 找不到「直播结算总额」")
                return False
            click_box(b)
            dds = open_dds()
            hit = None
            for d in dds:
                for it in d.get("items", []):
                    if it["t"] == option:
                        hit = it
            if not hit:
                log("  [sale] 下拉里没有 %s；可见=%s"
                    % (option, [[i["t"] for i in d.get("items", [])] for d in dds]))
                close_dropdowns()
                return False
            click_box(hit)
            # 与 collect.py 一致：点完**尝试**关浮层，并记录是否真关上了
            closed = close_dropdowns()
            left = len(open_dds())
            log("  [sale] %s -> %s 已点；close_dropdowns()=%s，仍有可见浮层 %d 个 %s"
                % ("直播结算总额", option, closed, left,
                   [d["box"] for d in open_dds()][:3]))
            return True

        log("打开达人广场 …")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)
        txt = page.evaluate("() => document.body.innerText.slice(0, 400)")
        if not any(m in txt for m in ("主推类目", "找达人", "按商品找达人")):
            log("!! 未登录，先手动登录再重跑")
            ctx.close()
            return
        log("登录态: 已登录")

        # ---------- A. 「粉丝」系列筛选项还在不在 ----------
        log("")
        log("=" * 74)
        log("A. form-item 探测（FIND_FORMITEM_JS 精确/前缀匹配）")
        log("=" * 74)
        for lb in CANDIDATE_LABELS:
            b = page.evaluate(J["FIND_FORMITEM_JS"], lb)
            cur = page.evaluate(J["FORMITEM_TEXT_JS"], lb)
            log("  %-12s -> %s   回显=%r" % (lb, b if b else "**不存在**", cur))

        # 直接扫一遍所有 auxo-form-item 的真实文本，避免漏掉改名后的项
        allitems = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('div.auxo-form-item').forEach(e => {
                const t = (e.innerText || '').trim().replace(/\\s+/g, ' ');
                const r = e.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) return;
                out.push({t: t.slice(0, 40), x: Math.round(r.x), y: Math.round(r.y),
                          w: Math.round(r.width), h: Math.round(r.height)});
            });
            out.sort((a, b) => (a.y - b.y) || (a.x - b.x));
            return out;
        }""") or []
        log("  -- 页面全部 auxo-form-item（y>=380 的「达人信息」行才是关键）--")
        for it in allitems:
            if it["y"] >= 380:
                log("     y=%-5s x=%-5s w=%-5s %r" % (it["y"], it["x"], it["w"], it["t"]))

        # 「粉丝指数」的下拉选项（若存在）
        log("")
        log("=" * 74)
        log("A2. 「粉丝指数」下拉选项（老「粉丝量」的疑似替代品）")
        log("=" * 74)
        close_dropdowns()
        b = page.evaluate(J["FIND_FORMITEM_JS"], "粉丝指数")
        if not b:
            log("  页面里没有「粉丝指数」")
        else:
            click_box(b, 1.6)
            dds = open_dds()
            if not dds:
                log("  点了「粉丝指数」但没弹出下拉（或是开关型）")
            for i, d in enumerate(dds):
                log("  下拉[%d] box=%s" % (i, d["box"]))
                for it in d.get("items", []):
                    log("     - %r @(%s,%s)" % (it["t"], it["x"], it["y"]))
            close_dropdowns()

        # ---------- B. agg 面板在什么条件下点不开 ----------
        log("")
        log("=" * 74)
        log("B. agg 面板「达人画像」复现实验")
        log("=" * 74)
        log("  ① 干净页面基线：")
        try_open_portrait("基线")
        close_dropdowns()

        log("")
        log("  ② 先应用「直播结算总额 = 1w-10w」（collect.py 的顺序），再点：")
        apply_sale("1w-10w")
        try_open_portrait("sale之后")
        close_dropdowns()

        log("")
        log("  ③ 再叠「有联系方式」开关（collect.py 在 agg 之前做的就是它），再点：")
        close_dropdowns()
        b = page.evaluate(J["FIND_FORMITEM_JS"], "有联系方式")
        if b:
            log("  「有联系方式」box=%s -> 点击" % b)
            click_box(b, 1.6)
            log("  点击后可见浮层: %s" % [d["box"] for d in open_dds()][:3])
        else:
            log("  找不到「有联系方式」")
        try_open_portrait("contact之后")
        close_dropdowns()

        try:
            page.screenshot(path=SHOT)
            log("")
            log("截图: %s" % SHOT)
        except Exception as e:
            log("截图失败: %s" % e)

        ctx.close()


if __name__ == "__main__":
    main()
