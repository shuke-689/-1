# -*- coding: utf-8 -*-
"""验证探针：把 collect.py 里**真实的** JS 常量 + apply_agg 点击序列跑一遍，
最后读接口 payload 里的 filters，确认

    达人画像 -> 达人性别 = 女        -> author_gender == ["2"]
    粉丝画像 -> 粉丝性别 = 女性居多   -> fans_gender   == ["2"]

⚠️ 本探针**不复制** JS 字符串，而是用 ast 从 collect.py 里抠出来 —— 保证测的就是
   真实代码路径（踩过的坑：探针自己抄一份，抄错了会得出假结论）。
⚠️ 不能用 `import collect`（它会替换 sys.stdout，另加一层会 I/O on closed file）。

跑法：source tools/env.sh && "$PY" .probe/probe_agg.py
"""
import ast
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
SHOT = os.path.join(BASE, "out", "probe_agg.png")
WANT = ("FIND_FORMITEM_JS", "FIND_AGG_SUBSELECT_JS", "FIND_SELECT_OPTION_JS",
        "FIND_AGG_BTN_JS", "DUMP_AGG_JS", "DUMP_POPOVERS_JS", "FORMITEM_TEXT_JS",
        "ALL_DROPDOWNS_JS", "CLOSE_DROPDOWN_JS")


def log(m):
    print(m, flush=True)


def load_js():
    """从 collect.py 里抠出 JS 常量（只取字面量，不执行模块）。"""
    src = io.open(os.path.join(BASE, "collect.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    found = {}
    for node in tree.body:
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
    reqs = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            viewport={"width": 2552, "height": 1262},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req):
            try:
                if "search_feed_author" in req.url and req.method == "POST":
                    reqs.append(req.post_data or "")
            except Exception:
                pass

        page.on("request", on_request)
        log("打开达人广场 …")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        txt = page.evaluate("() => document.body.innerText.slice(0, 400)")
        if not any(m in txt for m in ("主推类目", "找达人", "按商品找达人")):
            log("!! 未登录，先手动登录再重跑")
            ctx.close()
            return
        log("登录态: 已登录")

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

        def dump_agg(tag):
            try:
                ds = page.evaluate(J["DUMP_AGG_JS"]) or []
            except Exception as e:
                log("  [%s] dump 失败: %s" % (tag, str(e)[:70]))
                return
            if not ds:
                log("  [%s] （没有可见 agg 面板）" % tag)
            for d in ds[:4]:
                log("  [%s] 面板 box=%s rows=%s text=%r"
                    % (tag, d["box"], d["rows"], d["text"][:110]))

        def apply_agg(label, sub, option, tag):
            """与 collect.py 的 apply_agg 同序列。"""
            for attempt in range(3):
                close_dropdowns()
                box = page.evaluate(J["FIND_FORMITEM_JS"], label)
                if not box:
                    log("  [%s] 未找到筛选项 %s（第%d/3次）" % (tag, label, attempt + 1))
                    time.sleep(1.2)
                    continue
                click_box(box, 1.6)                       # ① 打开面板
                sel = page.evaluate(J["FIND_AGG_SUBSELECT_JS"], sub)
                if not sel:
                    log("  [%s] 面板里没找到子项 %s（第%d/3次）" % (tag, sub, attempt + 1))
                    dump_agg(tag)
                    close_dropdowns()
                    time.sleep(1.5)
                    continue
                log("  [%s] 子项 %s 的「请选择」@(%s,%s) %s"
                    % (tag, sub, sel["x"], sel["y"], sel["cls"]))
                click_box(sel, 1.4)                       # ② 展开下拉
                opt = page.evaluate(J["FIND_SELECT_OPTION_JS"], option)
                if not opt:
                    log("  [%s] 下拉里没有选项 %s（第%d/3次）；浮层=%s"
                        % (tag, option, attempt + 1,
                           [d["text"][:50] for d in
                            (page.evaluate(J["DUMP_POPOVERS_JS"]) or [])[:4]]))
                    dump_agg(tag)
                    close_dropdowns()
                    time.sleep(1.5)
                    continue
                log("  [%s] 选项 %s @(%s,%s)" % (tag, option, opt["x"], opt["y"]))
                click_box(opt, 1.0)                       # ②b 选中
                btn = page.evaluate(J["FIND_AGG_BTN_JS"], "确认")
                if not btn:
                    log("  [%s] 没找到「确认」（第%d/3次）" % (tag, attempt + 1))
                    dump_agg(tag)
                    close_dropdowns()
                    time.sleep(1.5)
                    continue
                log("  [%s] 点「确认」@(%s,%s)" % (tag, btn["x"], btn["y"]))
                click_box(btn, 1.5)                       # ③ 确认
                shown = page.evaluate(J["FORMITEM_TEXT_JS"], label)
                log("  [%s] ✅ %s -> %s 已确认（回显: %r）" % (tag, sub, option, shown))
                return True
            return False

        ok1 = apply_agg("达人画像", "达人性别", "女", "portrait")
        ok2 = apply_agg("粉丝画像", "粉丝性别", "女性居多", "fansg")
        time.sleep(4)

        log("\n点击结果: 达人画像=%s  粉丝画像=%s" % (ok1, ok2))

        # ---- 读真实 payload ----
        log("\n已捕获 %d 条 search_feed_author 请求" % len(reqs))
        best = None
        for q in reversed(reqs):
            try:
                f = json.loads(q).get("filters")
            except Exception:
                continue
            if isinstance(f, dict) and f:
                best = f
                break
        if best is None:
            log("!! 一条带 filters 的请求都没抓到")
        else:
            log("最近一次 filters = %s"
                % json.dumps({k: v for k, v in best.items() if v}, ensure_ascii=False))
            log("\n=== 判定 ===")
            ag = [str(x) for x in (best.get("author_gender") or [])]
            fg = [str(x) for x in (best.get("fans_gender") or [])]
            log("author_gender = %s  -> %s" % (ag, "✅ 命中 2(女)" if "2" in ag else "❌ 不含 2"))
            log("fans_gender   = %s  -> %s" % (fg, "✅ 命中 2(女性居多)" if "2" in fg else "❌ 不含 2"))

        page.screenshot(path=SHOT)
        log("\n截图: %s" % SHOT)
        time.sleep(2)
        ctx.close()


if __name__ == "__main__":
    main()
