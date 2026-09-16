# -*- coding: utf-8 -*-
"""阶段 6：应用筛选 → 抓列表数据 → 进达人主页 → 点眼睛复制微信号 → 读剪贴板。

产出 out/stage6/，日志 out/stage6.log
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage6")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage6.log")
os.makedirs(OUT, exist_ok=True)
Daren = ("https://buyin.jinritemai.com/dashboard/servicehall/daren-square")


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dump_popup(page, tag):
    """把当前所有浮层(popup/dropdown)的 DOM 结构导出来"""
    try:
        info = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const out = [];
            document.querySelectorAll('[class*="popup"], [class*="Popup"], [class*="dropdown"], [class*="Dropdown"], [class*="overlay"], [class*="Overlay"], [class*="popper"], [role="tooltip"]').forEach(e => {
                const r = e.getBoundingClientRect();
                if (r.width < 60 || r.height < 30) return;
                const items = Array.from(e.querySelectorAll('*')).slice(0,120).map(k => {
                    const kt = (k.innerText||'').trim();
                    if (!kt || kt.length > 40) return null;
                    return {tag:k.tagName, cls:(k.className||'').toString().slice(0,70),
                            text:kt, rect:rect(k), checked: k.getAttribute('aria-checked') || ''};
                }).filter(Boolean);
                out.push({cls:(e.className||'').toString().slice(0,130), rect:rect(e),
                          text:(e.innerText||'').trim().slice(0,300), items:items.slice(0,70)});
            });
            return out;
        }""")
        with open(os.path.join(OUT, "popup_%s.json" % tag), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        log("  [%s] 浮层 %d 个" % (tag, len(info)))
        for p in info[:3]:
            log("    popup cls=%s rect=%s" % (p["cls"][:90], p["rect"]))
            log("      text=%r" % p["text"][:160].replace("\n", " / "))
            for it in p["items"][:35]:
                log("        <%s> %r @%s cls=%s" % (it["tag"], it["text"], (it["rect"]["x"], it["rect"]["y"]), it["cls"][:55]))
        return info
    except Exception as e:
        log("  [%s] dump_popup 失败: %r" % (tag, e))
        return []


def find_clickable(page, text, timeout=6000):
    """返回能点的元素定位（优先最小元素）"""
    for sel in ["text=%s" % text]:
        try:
            loc = page.locator(sel)
            n = loc.count()
            if n:
                return loc.nth(0)
        except Exception:
            pass
    return None


def click(page, text, tag, timeout=7000):
    try:
        page.locator("text=%s" % text).first.click(timeout=timeout)
        log("  [%s] 点击 %r OK" % (tag, text))
        return True
    except Exception as e:
        log("  [%s] 点击 %r 失败: %s" % (tag, text, str(e)[:80].replace("\n", " ")))
        return False


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.join(BASE, ".probe"))
    import win_io as w

    lists = []          # search_feed_author 响应
    contact_api = []    # 联系方式相关响应

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
                if not b or len(b) > 3_000_000:
                    return
                if "search_feed_author" in u:
                    req = ""
                    try:
                        req = resp.request.post_data or ""
                    except Exception:
                        pass
                    lists.append({"url": u, "req": req, "body": b})
                elif re.search(r"contact|wechat|weixin|phone|author_detail|"
                               r"author_info|profile", u, re.I):
                    contact_api.append({"url": u, "method": resp.request.method, "body": b})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开达人广场")
        page.goto(Daren, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)
        log("URL: %s | %s" % (page.url, page.title()))

        # ---- 1) 类目：个护家清 ----
        log("=" * 62)
        log("步骤: 主推类目 = 个护家清")
        if click(page, "个护家清", "cat"):
            time.sleep(2)
            dump_popup(page, "cat")
            # 弹层里可能直接就是选项列表；尝试点「不限」
            for cand in ("不限", "确定", "查询"):
                if click(page, cand, "cat-ok", timeout=4000):
                    break
            time.sleep(4)

        # ---- 2) 视频结算总额 1w-10w ----
        log("=" * 62)
        log("步骤: 视频结算总额 = 1w-10w")
        if click(page, "视频结算总额", "vid"):
            time.sleep(2)
            dump_popup(page, "vid")
            if click(page, "1w-10w", "vid-opt"):
                time.sleep(1)
                for cand in ("确定", "查询", "搜索"):
                    if click(page, cand, "vid-ok", timeout=3000):
                        break
            time.sleep(4)

        # ---- 3) 粉丝量 10w以下 ----
        log("=" * 62)
        log("步骤: 粉丝量 = 10w以下")
        for chip in ("粉丝量", "达人信息"):
            if click(page, chip, "fans"):
                time.sleep(2)
                dump_popup(page, "fans")
                if click(page, "10w以下", "fans-opt"):
                    time.sleep(1)
                    for cand in ("确定", "查询"):
                        if click(page, cand, "fans-ok", timeout=3000):
                            break
                    break
        time.sleep(4)

        # ---- 4) 有联系方式 ----
        log("=" * 62)
        log("步骤: 勾选「有联系方式」")
        if click(page, "有联系方式", "contact"):
            time.sleep(4)

        # ---- 5) 列表数据 ----
        log("=" * 62)
        log("列表接口响应 %d 条" % len(lists))
        if lists:
            first = json.loads(lists[-1]["body"])
            lst = first.get("data", {}).get("list", [])
            log("  当前页 %d 条" % len(lst))
            with open(os.path.join(OUT, "list_sample.json"), "w", encoding="utf-8") as f:
                json.dump(lst[:5], f, ensure_ascii=False, indent=2)
            for a in lst[:8]:
                ab = a.get("author_base", {})
                log("   · %-26s 粉丝=%-8s 性别=%s 等级=LV%s %s" % (
                    ab.get("nickname"), ab.get("fans_num"), ab.get("gender"),
                    ab.get("author_level"), ab.get("city")))

        # 表格里读
        rows = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('tr, [class*="table-row"], [class*="row"]').forEach(tr => {
                const t = (tr.innerText||'').trim();
                if (!t || t.length < 8) return;
                const r = tr.getBoundingClientRect();
                if (r.height < 20) return;
                out.push({text: t.replace(/\\n/g, ' | ').slice(0, 220),
                          cls: (tr.className||'').toString().slice(0,80),
                          x: Math.round(r.x), y: Math.round(r.y), h: Math.round(r.height)});
            });
            return out.slice(0, 40);
        }""")
        log("表格行 %d 条:" % len(rows))
        for r in rows[:14]:
            log("   ROW @y=%-5d %s" % (r["y"], r["text"][:170]))

        # ---- 6) 打开第一个达人主页 ----
        log("=" * 62)
        log("打开第一个达人主页")
        before = set(ctx.pages)
        first_name = None
        if lists:
            first_name = json.loads(lists[-1]["body"])["data"]["list"][0]["author_base"]["nickname"]
        log("  目标达人: %r" % first_name)
        opened = False
        if first_name:
            try:
                page.locator("text=%s" % first_name[:8]).first.click(timeout=8000)
                opened = True
                log("  点击达人名 OK")
            except Exception as e:
                log("  点击达人名失败: %s" % str(e)[:90])
        time.sleep(6)
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

        # 达人主页上的微信号区域
        detail = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const out = [];
            document.querySelectorAll('*').forEach(e => {
                const t = (e.innerText||'').trim();
                if (!t || t.length > 40) return;
                if (!/微信|手机|联系|粉丝|约定|结算|合作|简介/.test(t)) return;
                const r = e.getBoundingClientRect();
                if (r.width < 10 || r.height < 8) return;
                out.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,90),
                          text:t, rect:rect(e)});
            });
            // 也找眼睛/复制类图标
            const icons = [];
            document.querySelectorAll('img, svg, [class*="icon"], [class*="Icon"]').forEach(e => {
                const r = e.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) return;
                icons.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,90),
                            rect:rect(e), src:(e.getAttribute && e.getAttribute('src')||'').slice(0,80)});
            });
            return {labels: out.slice(0,60), icons: icons.slice(0,80),
                    bodyHead:(document.body.innerText||'').slice(0,2500)};
        }""")
        with open(os.path.join(OUT, "detail_probe.json"), "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, indent=2)
        log("  联系方式相关元素 %d / 图标 %d" % (len(detail["labels"]), len(detail["icons"])))
        for l in detail["labels"][:25]:
            log("     <%s> %r @%s cls=%s" % (l["tag"], l["text"], (l["rect"]["x"], l["rect"]["y"]), l["cls"][:60]))
        log("  ---- 主页文本 ----")
        for line in (detail["bodyHead"] or "").splitlines()[:40]:
            if line.strip():
                log("   | %s" % line.strip()[:110])

        with open(os.path.join(OUT, "list_api.jsonl"), "w", encoding="utf-8") as f:
            for r in lists:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(os.path.join(OUT, "contact_api.jsonl"), "w", encoding="utf-8") as f:
            for r in contact_api:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log("=" * 62)
        log("列表接口 %d 条 / 联系类接口 %d 条" % (len(lists), len(contact_api)))
        for c in contact_api[:25]:
            log("   API %s %s" % (c["method"], c["url"][:160]))
        log("剪贴板当前内容: %r" % w.get_clipboard())

        log("阶段 6 完成，浏览器保持 180 秒")
        time.sleep(180)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
