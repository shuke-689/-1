# -*- coding: utf-8 -*-
"""阶段 7：直接调接口拿筛选结果 + 进达人主页 + 点眼睛复制微信号，摸清联系方式接口。

产出 out/stage7/，日志 out/stage7.log
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage7")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage7.log")
os.makedirs(OUT, exist_ok=True)
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


PAYLOAD = {
    "page": 1, "refresh": True, "type": 1, "query": "", "search_id": "",
    "filters": {
        "main_cate_new": ["5"],
        "content_type": [],
        "common_range_selection_author_sale_gmv_30d_settle": [],
        "common_range_selection_live_sales_30d_settle": [],
        "common_range_selection_video_sales_30d_settle": ["2"],
        "common_range_selection_picture_sales_30d_settle": [],
        "common_range_selection_window_sales_30d_settle": [],
        "common_range_selection_author_square_average_gmv_settle": [],
        "live_watching_times": [],
        "common_range_selection_author_single_video_gmv_settle": [],
        "video_play_time": [],
        "common_range_selection_video_nature_rate": [],
        "common_range_selection_gmv_per_picture_30d_settle": [],
        "image_text_play_time": [],
        "window_order_cnt": [],
        "window_product_cnt": [],
        "author_level_new": [],
        "fans_num": ["1"],
        "author_portrait": [],
        "fan_portrait": [],
        "fans_profile": [],
        "common_selection_cooperation_level": [],
        "has_contact": True,
    },
}


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.join(BASE, ".probe"))
    import win_io as w

    api_all = []

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
                api_all.append({"url": u, "method": resp.request.method, "body": b})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)
        log("URL: %s" % page.url)

        # ---- 1) 直接调接口 ----
        log("=" * 62)
        log("直接调用 search_feed_author 接口")
        try:
            res = page.evaluate("""async (payload) => {
                const r = await fetch('/square_pc_api/square/search_feed_author', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                    credentials: 'include'
                });
                return {status: r.status, text: await r.text()};
            }""", PAYLOAD)
            log("  HTTP %s, 长度 %d" % (res["status"], len(res["text"])))
            with open(os.path.join(OUT, "api_direct.json"), "w", encoding="utf-8") as f:
                f.write(res["text"])
            try:
                d = json.loads(res["text"])
                lst = (d.get("data") or {}).get("list") or []
                log("  返回 %d 条, has_more=%s" % (len(lst), (d.get("data") or {}).get("has_more")))
                for a in lst[:10]:
                    ab = a["author_base"]
                    si = (a.get("sale_info") or {}).get("video_total_sales_settle") or {}
                    log("   · %-24s 粉丝=%-7s 性别=%s %-14s 视频结算=%s-%s" % (
                        ab.get("nickname"), ab.get("fans_num"), ab.get("gender"),
                        ab.get("city"), si.get("sale_low"), si.get("sale_high")))
                log("  >>> 直连接口可用!")
            except Exception as e:
                log("  解析失败: %r  前缀=%r" % (e, res["text"][:200]))
        except Exception as e:
            log("  直连失败: %r" % e)

        # ---- 2) 从表格取达人名并打开主页 ----
        log("=" * 62)
        log("从表格取达人名")
        names = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('[class*="table"] [class*="cell"], [class*="table"] td').forEach(td => {
                const t = (td.innerText||'').trim();
                if (!t || t.length > 20 || t.includes('\\n')) return;
                const r = td.getBoundingClientRect();
                if (r.x > 800) return;   // 只要最左侧达人信息列
                out.push({text:t, x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)});
            });
            return out;
        }""")
        log("  候选 %d 个" % len(names))
        for n in names[:12]:
            log("     %r @(%s,%s) %sx%s" % (n["text"], n["x"], n["y"], n["w"], n["h"]))

        target = names[0]["text"] if names else None
        log("  目标达人: %r" % target)

        detail_ok = False
        if target:
            before = set(ctx.pages)
            try:
                page.mouse.click(names[0]["x"] + 20, names[0]["y"] + names[0]["h"] / 2)
                detail_ok = True
                log("  已点击达人信息列")
            except Exception as e:
                log("  鼠标点击失败: %s" % str(e)[:80])
            time.sleep(7)
            new = [x for x in ctx.pages if x not in before]
            if new:
                page = new[-1]
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                log("  新标签页: %s" % page.url)
            log("  当前 URL: %s | %s" % (page.url, page.title()))
            with open(os.path.join(OUT, "detail.html"), "w", encoding="utf-8") as f:
                f.write(page.content())

        # ---- 3) 达人主页结构 + 眼睛图标 ----
        log("=" * 62)
        log("解析达人主页结构")
        info = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const labels = [];
            document.querySelectorAll('*').forEach(e => {
                const t = (e.innerText||'').trim();
                if (!t || t.length > 30 || t.includes('\\n')) return;
                if (!/微信|手机|联系方式|达人手|达人微|电话/.test(t)) return;
                const r = e.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) return;
                labels.push({tag:e.TagName||e.tagName, cls:(e.className||'').toString().slice(0,90), text:t, rect:rect(e)});
            });
            const icons = [];
            document.querySelectorAll('img, svg, i, [class*="icon"], [class*="Icon"], [class*="eye"], [class*="Eye"], [class*="copy"], [class*="Copy"]').forEach(e => {
                const r = e.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) return;
                icons.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,90),
                            rect:rect(e), src:(e.getAttribute&&e.getAttribute('src')||'').slice(0,100),
                            title:(e.getAttribute&&(e.getAttribute('title')||e.getAttribute('aria-label'))||'')});
            });
            return {url:location.href, title:document.title, labels, icons,
                    body:(document.body.innerText||'').slice(0,1800)};
        }""")
        with open(os.path.join(OUT, "detail_probe.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        log("  含微信类标签 %d 个:" % len(info["labels"]))
        for l in info["labels"][:20]:
            log("     <%s> %r @%s cls=%s" % (l["tag"], l["text"], (l["rect"]["x"], l["rect"]["y"]), l["cls"][:60]))
        log("  图标 %d 个 (前 25):" % len(info["icons"]))
        for i in info["icons"][:25]:
            log("     <%s> @%s %sx%s cls=%s src=%s title=%s" % (
                i["tag"], (i["rect"]["x"], i["rect"]["y"]), i["rect"]["w"], i["rect"]["h"],
                i["cls"][:50], i["src"][:50], i["title"]))

        # ---- 4) 点眼睛 ----
        log("=" * 62)
        log("尝试点击眼睛图标")
        before_apis = len(api_all)
        clicked_eye = False
        # 优先点含 eye 类的图标
        for i in info["icons"]:
            if re.search(r"eye|Eye|look|Look|contact|Contact|show|Show", i["cls"] + i["title"]):
                try:
                    page.mouse.click(i["rect"]["x"] + i["rect"]["w"] / 2,
                                     i["rect"]["y"] + i["rect"]["h"] / 2)
                    log("  点击 eye 类图标 @%s cls=%s" % ((i["rect"]["x"], i["rect"]["y"]), i["cls"][:50]))
                    clicked_eye = True
                    break
                except Exception as e:
                    log("  点击失败: %s" % str(e)[:70])
        if not clicked_eye:
            log("  没找到 eye 类图标，尝试点微信号标签右侧的图标")
            for l in info["labels"]:
                if "微信" in l["text"]:
                    # 标签右侧 40px 内的图标
                    cand = [i for i in info["icons"]
                            if abs(i["rect"]["y"] - l["rect"]["y"]) < 30
                            and 0 < i["rect"]["x"] - l["rect"]["x"] < 400]
                    log("    微信标签 @%s 右侧候选图标 %d 个" % ((l["rect"]["x"], l["rect"]["y"]), len(cand)))
                    for c in cand[:6]:
                        log("      cand @%s %sx%s cls=%s src=%s" % (
                            (c["rect"]["x"], c["rect"]["y"]), c["rect"]["w"], c["rect"]["h"],
                            c["cls"][:60], c["src"][:60]))
                    if cand:
                        c = cand[0]
                        page.mouse.click(c["rect"]["x"] + c["rect"]["w"] / 2,
                                         c["rect"]["y"] + c["rect"]["h"] / 2)
                        clicked_eye = True
                        log("      -> 已点击第一个候选")
                    break
        time.sleep(4)

        # 点后页面内容 + 新接口
        after = page.evaluate("""() => (document.body.innerText||'').slice(0, 2200)""")
        with open(os.path.join(OUT, "after_eye.txt"), "w", encoding="utf-8") as f:
            f.write(after)
        log("  点击后页面文本 (找微信/复制):")
        for line in after.splitlines():
            if any(k in line for k in ("微信", "复制", "手机", "联系人", "wxid", "微信号")):
                log("     | %s" % line.strip()[:120])

        log("  新增接口 %d 条:" % (len(api_all) - before_apis))
        for r in api_all[before_apis:]:
            log("     API %s %s" % (r["method"], r["url"][:150]))
            with open(os.path.join(OUT, "eye_api.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        with open(os.path.join(OUT, "all_api.jsonl"), "w", encoding="utf-8") as f:
            for r in api_all:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # ---- 5) 尝试点复制 ----
        log("=" * 62)
        log("尝试点「复制」并读剪贴板")
        for t in ("复制", "复制微信号", "复 制"):
            try:
                page.locator("text=%s" % t).first.click(timeout=3000)
                log("  点击 %r OK" % t)
                time.sleep(1.5)
                break
            except Exception as e:
                log("  点击 %r 失败: %s" % (t, str(e)[:60].replace("\n", " ")))
        log("  剪贴板: %r" % w.get_clipboard())

        log("阶段 7 完成，浏览器保持 120 秒")
        time.sleep(120)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
