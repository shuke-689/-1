# -*- coding: utf-8 -*-
"""阶段 8：用 UI 驱动筛选 → 从接口拿达人名单 → 在 DOM 里点到该达人 → 打开达人主页
→ 定位微信号眼睛图标 → 点击 → 捕获联系方式接口 → 点复制 → 读剪贴板。

产出 out/stage8/，日志 out/stage8.log
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage8")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage8.log")
os.makedirs(OUT, exist_ok=True)
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.join(BASE, ".probe"))
    import win_io as w

    apis = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                u = resp.url
                ct = (resp.headers or {}).get("content-type", "") or ""
                if "json" not in ct.lower():
                    return
                b = resp.text()
                if not b or len(b) > 2_000_000:
                    return
                apis.append({"url": u, "method": resp.request.method, "body": b,
                             "req": (resp.request.post_data or "")[:4000]})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)
        log("URL: %s" % page.url)

        # ---- 应用筛选（点 chip） ----
        def chip(text, tag, opt=None):
            try:
                page.locator("text=%s" % text).first.click(timeout=6000)
                log("  [%s] 点开 %r" % (tag, text))
                time.sleep(1.5)
                if opt:
                    page.locator("text=%s" % opt).first.click(timeout=5000)
                    log("  [%s] 选中 %r" % (tag, opt))
                    time.sleep(1)
                return True
            except Exception as e:
                log("  [%s] %r 失败: %s" % (tag, text, str(e)[:70].replace("\n", " ")))
                return False

        log("应用筛选")
        chip("个护家清", "cat")
        chip("视频结算总额", "vid", "1w-10w")
        chip("粉丝量", "fans", "10w以下")
        chip("有联系方式", "contact")
        time.sleep(6)

        # ---- 从接口拿名单 ----
        log("=" * 62)
        last_list = None
        for a in reversed(apis):
            if "search_feed_author" in a["url"]:
                try:
                    d = json.loads(a["body"])
                    if (d.get("data") or {}).get("list"):
                        last_list = d
                        break
                except Exception:
                    pass
        names = []
        if last_list:
            names = [x["author_base"]["nickname"] for x in last_list["data"]["list"]]
            log("接口返回 %d 个达人: %s" % (len(names), names[:6]))
            with open(os.path.join(OUT, "list.json"), "w", encoding="utf-8") as f:
                json.dump(last_list, f, ensure_ascii=False, indent=2)

        # 找出 DOM 里真实存在的那个
        target = None
        for n in names:
            try:
                if page.locator("text=%s" % n).count() > 0:
                    target = n
                    break
            except Exception:
                continue
        log("DOM 中可点击的达人: %r" % target)

        # ---- 点开达人 ----
        log("=" * 62)
        detail_reached = False
        if target:
            before = set(ctx.pages)
            try:
                page.locator("text=%s" % target).first.click(timeout=8000)
                log("  已点击 %r" % target)
            except Exception as e:
                log("  点击失败: %s" % str(e)[:90])
            for _ in range(20):
                time.sleep(1)
                new = [x for x in ctx.pages if x not in before]
                pg = new[-1] if new else page
                try:
                    txt = pg.inner_text("body")[:5000]
                except Exception:
                    txt = ""
                if "达人微信号" in txt or "达人手机号" in txt or "达人简介" in txt:
                    page = pg
                    detail_reached = True
                    break
            log("  达人主页到达: %s" % detail_reached)
            log("  当前 URL: %s | %s" % (page.url, page.title()))

        with open(os.path.join(OUT, "detail.html"), "w", encoding="utf-8") as f:
            f.write(page.content())

        # ---- 达人主页结构 ----
        log("=" * 62)
        log("达人主页：微信号区域 + 全部图标")
        info = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const rows = [];
            document.querySelectorAll('*').forEach(e => {
                const t = (e.innerText||'').trim();
                if (!t || t.length > 40 || t.includes('\\n')) return;
                if (!/微信|手机号|联系|简介|企业|机构|认证据|标签/.test(t)) return;
                const r = e.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) return;
                rows.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,100), text:t, rect:rect(e)});
            });
            const icons = [];
            document.querySelectorAll('img, svg, i, span, div').forEach(e => {
                const r = e.getBoundingClientRect();
                if (r.width < 6 || r.height < 6 || r.width > 60 || r.height > 60) return;
                const cls = (e.className||'').toString();
                if (!/icon|Icon|eye|Eye|copy|Copy|look|Look|view|View|contact|Contact|show|Show|mask|Mask/.test(cls)) return;
                icons.push({tag:e.tagName, cls:cls.slice(0,110), rect:rect(e),
                            src:(e.getAttribute&&e.getAttribute('src')||'').slice(0,120),
                            title:(e.getAttribute&&(e.getAttribute('title')||e.getAttribute('aria-label'))||'')});
            });
            return {url:location.href, title:document.title, rows, icons,
                    body:(document.body.innerText||'').slice(0,3000)};
        }""")
        with open(os.path.join(OUT, "detail_probe.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        log("  页面 URL: %s" % info["url"])
        log("  相关行 %d:" % len(info["rows"]))
        for r in info["rows"][:25]:
            log("     <%s> %r @%s cls=%s" % (r["tag"], r["text"], (r["rect"]["x"], r["rect"]["y"]), r["cls"][:60]))
        log("  图标 %d 个:" % len(info["icons"]))
        for i in info["icons"][:40]:
            log("     <%s> @%s %sx%s cls=%s title=%s src=%s" % (
                i["tag"], (i["rect"]["x"], i["rect"]["y"]), i["rect"]["w"], i["rect"]["h"],
                i["cls"][:55], i["title"], i["src"][:55]))
        log("  ---- 主页文本 ----")
        for line in (info["body"] or "").splitlines()[:45]:
            if line.strip():
                log("   | %s" % line.strip()[:110])

        # ---- 点眼睛 ----
        log("=" * 62)
        log("定位并点击微信号旁的眼睛图标")
        eye = None
        for r in info["rows"]:
            if "微信" in r["text"]:
                cand = [i for i in info["icons"]
                        if 0 < (i["rect"]["x"] - r["rect"]["x"]) < 500
                        and abs(i["rect"]["y"] - r["rect"]["y"]) < 40]
                log("  %r @%s 右侧候选 %d 个" % (r["text"], (r["rect"]["x"], r["rect"]["y"]), len(cand)))
                for c in cand[:8]:
                    log("     cand @%s %sx%s cls=%s title=%s src=%s" % (
                        (c["rect"]["x"], c["rect"]["y"]), c["rect"]["w"], c["rect"]["h"],
                        c["cls"][:60], c["title"], c["src"][:60]))
                if cand:
                    cand.sort(key=lambda c: c["rect"]["x"])
                    eye = cand[0]
                break

        n_before = len(apis)
        if eye:
            page.mouse.click(eye["rect"]["x"] + eye["rect"]["w"] / 2,
                             eye["rect"]["y"] + eye["rect"]["h"] / 2)
            log("  已点击 @(%s,%s)" % (eye["rect"]["x"], eye["rect"]["y"]))
        else:
            log("  ✗ 未定位到眼睛图标")
        time.sleep(3)

        after = page.evaluate("() => (document.body.innerText||'').slice(0,3000)")
        with open(os.path.join(OUT, "after_eye.txt"), "w", encoding="utf-8") as f:
            f.write(after)
        log("  点后含微信/复制的行:")
        for line in after.splitlines():
            s = line.strip()
            if any(k in s for k in ("微信", "复制", "手机", "wxid", "微信号")):
                log("     | %s" % s[:120])

        log("  新增接口:")
        for r in apis[n_before:]:
            if "zijieapi" in r["url"]:
                continue
            log("     %s %s" % (r["method"], r["url"][:160]))
            with open(os.path.join(OUT, "contact_api.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # ---- 点复制 ----
        log("=" * 62)
        log("点击复制")
        before_clip = w.get_clipboard()
        log("  点击前剪贴板: %r" % before_clip)
        for t in ("复制", "复制微信号", "复 制", "复制微信"):
            try:
                page.locator("text=%s" % t).first.click(timeout=2500)
                log("  点击 %r OK" % t)
                time.sleep(2)
                break
            except Exception:
                pass
        clip = w.get_clipboard()
        log("  点击后剪贴板: %r" % clip)

        with open(os.path.join(OUT, "all_api.jsonl"), "w", encoding="utf-8") as f:
            for r in apis:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        log("阶段 8 完成，浏览器保持 120 秒")
        time.sleep(120)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
