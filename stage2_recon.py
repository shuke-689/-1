# -*- coding: utf-8 -*-
"""阶段 2：已登录，从抖店后台一路进到「精选联盟 → 找达人」，侦察筛选器与列表结构。

产出到 out/stage2/：step{N}_*.html / step{N}_url.txt / nav_all.json / probe.json / api_capture.jsonl
日志：out/stage2.log
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage2")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage2.log")
os.makedirs(OUT, exist_ok=True)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save(page, name):
    try:
        with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8") as f:
            f.write(page.content())
        with open(os.path.join(OUT, name + "_url.txt"), "w", encoding="utf-8") as f:
            f.write(page.url)
    except Exception as e:
        log("保存 %s 失败: %r" % (name, e))


def dump_nav(page, tag):
    """输出页面上所有可点的导航/标签项"""
    try:
        items = page.evaluate("""() => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll("a, li, span, div, button").forEach(e => {
                const t = (e.innerText || '').trim();
                if (!t || t.length > 14 || t.includes('\\n')) return;
                const cls = (e.className || '').toString();
                if (cls.length > 200) return;
                const r = e.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) return;
                const key = t;
                if (seen.has(key)) return;
                seen.add(key);
                out.push({text: t, cls: cls.slice(0, 90),
                          x: Math.round(r.x), y: Math.round(r.y),
                          w: Math.round(r.width), h: Math.round(r.height)});
            });
            return out;
        }""")
        with open(os.path.join(OUT, "nav_%s.json" % tag), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        nav_words = [i["text"] for i in items if len(i["text"]) <= 6]
        log("  [%s] 候选导航文本: %s" % (tag, " | ".join(nav_words[:60])))
        return items
    except Exception as e:
        log("  [%s] dump_nav 失败: %r" % (tag, e))
        return []


def click_text(page, text, tag):
    """尝试点击包含指定文本的最小可点元素"""
    try:
        loc = page.locator("text=%s" % text).first
        loc.click(timeout=8000)
        log("  [%s] 点击 %r 成功" % (tag, text))
        return True
    except Exception as e:
        log("  [%s] 点击 %r 失败: %s" % (tag, text, str(e)[:120]))
        return False


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright

    api_records = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run",
                  "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "") or ""
                u = resp.url
                if "json" in ct.lower():
                    body = resp.text()
                    if body and len(body) < 2_000_000:
                        api_records.append({"url": u, "status": resp.status,
                                            "method": resp.request.method, "body": body})
            except Exception:
                pass

        page.on("response", on_response)

        # 新标签页兜底
        new_pages = []
        ctx.on("page", lambda pg: new_pages.append(pg))

        log("打开抖店后台首页（应为已登录状态）...")
        page.goto("https://fxg.jinritemai.com/ffa/mshop/homepage/index?from=buyin",
                  wait_until="domcontentloaded", timeout=90_000)
        time.sleep(6)
        log("URL: %s  title: %s" % (page.url, page.title()))
        save(page, "step1_dashboard")
        dump_nav(page, "step1")

        # --- 进精选联盟 ---
        log("=" * 60)
        log("尝试进入「精选联盟」")
        before = page.url
        ok = click_text(page, "精选联盟", "step2")
        time.sleep(7)
        if len(ctx.pages) > 1:
            page = ctx.pages[-1]
            log("  切换到新标签页: %s" % page.url)
        log("URL: %s" % page.url)
        save(page, "step2_buyin")
        dump_nav(page, "step2")
        if page.url == before and not ok:
            log("  提示：精选联盟可能不是这个入口名")

        # --- 进找达人 ---
        log("=" * 60)
        log("尝试进入「找达人」")
        for name in ("找达人", "达人广场", "达人库", "找主播"):
            if click_text(page, name, "step3"):
                time.sleep(7)
                if len(ctx.pages) > 1 and ctx.pages[-1] != page:
                    page = ctx.pages[-1]
                    log("  切换到新标签页: %s" % page.url)
                break
        log("URL: %s" % page.url)
        save(page, "step3_daren")
        dump_nav(page, "step3")

        # --- 侦察筛选器与列表 ---
        log("=" * 60)
        log("侦察筛选器 / 表头 / 列表项结构")
        probe = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const txt = e => (e.innerText || '').trim().slice(0, 60);
            const all = Array.from(document.querySelectorAll('*'));
            const filterish = all.filter(e => {
                const c = (e.className||'').toString();
                return /filter|Filter|condition|Condition|screen|Screen/.test(c)
                    && e.children.length < 14 && txt(e).length > 0
                    && txt(e).length < 120;
            }).slice(0, 40).map(e => ({tag:e.tagName, cls:(e.className||'').toString().slice(0,100),
                                       text:txt(e), rect:rect(e)}));
            const headers = Array.from(document.querySelectorAll('th, [class*="thead"] [class*="cell"], [class*="header-row"] > *'))
                .slice(0,40).map(e => ({tag:e.tagName, text:txt(e), cls:(e.className||'').toString().slice(0,80)}));
            const cards = all.filter(e => /card|Card|item|Item/.test((e.className||'').toString())
                && e.children.length >= 2 && e.children.length <= 12
                && txt(e).length > 10).slice(0,15)
                .map(e => ({cls:(e.className||'').toString().slice(0,100), text:txt(e), rect:rect(e)}));
            const inputs = Array.from(document.querySelectorAll('input, textarea'))
                .slice(0,40).map(e => ({tag:e.tagName, ph:e.getAttribute('placeholder')||'',
                                        cls:(e.className||'').toString().slice(0,80), rect:rect(e)}));
            const btns = Array.from(document.querySelectorAll('button, [class*="btn"], [class*="Button"]'))
                .slice(0,50).map(e => ({text:txt(e), cls:(e.className||'').toString().slice(0,80), rect:rect(e)}))
                .filter(x => x.text);
            return {url: location.href, title: document.title,
                    filters: filterish, headers, cards, inputs, buttons: btns,
                    bodyHead: (document.body.innerText||'').slice(0, 3000)};
        }""")
        with open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8") as f:
            json.dump(probe, f, ensure_ascii=False, indent=2)
        log("probe.json 已保存")
        log("  页面标题: %s" % probe.get("title"))
        log("  筛选器 %d 个 / 输入框 %d 个 / 按钮 %d 个 / 卡片 %d 个" % (
            len(probe.get("filters", [])), len(probe.get("inputs", [])),
            len(probe.get("buttons", [])), len(probe.get("cards", []))))
        for b in probe.get("buttons", [])[:30]:
            log("     Btn %r @%s" % (b["text"][:24], (b["rect"]["x"], b["rect"]["y"])))

        with open(os.path.join(OUT, "api_capture.jsonl"), "w", encoding="utf-8") as f:
            for r in api_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log("接口响应 %d 条" % len(api_records))
        for r in api_records[:40]:
            log("   API %s %s" % (r["method"], r["url"][:160]))

        log("阶段 2 完成，浏览器保持 90 秒")
        time.sleep(90)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
