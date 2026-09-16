# -*- coding: utf-8 -*-
"""阶段 4：抓出「精选联盟」下拉菜单的真实链接 + 试探候选 URL，定位达人广场。

产出 out/stage4/
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage4")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage4.log")
os.makedirs(OUT, exist_ok=True)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        log("打开后台首页")
        page.goto("https://fxg.jinritemai.com/ffa/mshop/homepage/index?from=buyin",
                  wait_until="domcontentloaded", timeout=90_000)
        time.sleep(6)

        # ---- 悬停/点击「精选联盟」，抓菜单 DOM ----
        log("悬停「精选联盟」抓菜单结构")
        try:
            page.locator("text=精选联盟").first.hover(timeout=8000)
        except Exception as e:
            log("  hover 失败: %s" % str(e)[:80])
        time.sleep(2)
        try:
            page.locator("text=精选联盟").first.click(timeout=8000)
        except Exception as e:
            log("  click 失败: %s" % str(e)[:80])
        time.sleep(2)

        menu = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                const t = (a.innerText||'').trim();
                if (!t) return;
                out.push({text: t.slice(0,40), href: a.getAttribute('href') || '',
                          cls:(a.className||'').toString().slice(0,90)});
            });
            const items = [];
            document.querySelectorAll('li, [class*="menu"], [class*="Menu"], [class*="popup"], [class*="Popup"], [class*="dropdown"], [class*="Dropdown"]').forEach(e => {
                const t = (e.innerText||'').trim();
                if (!t || t.length > 200) return;
                if (!/找合作|去推广|管合作|看数据/.test(t)) return;
                items.push({tag:e.tagName, text: t.slice(0,120),
                            cls:(e.className||'').toString().slice(0,120),
                            html: e.outerHTML.slice(0, 900)});
            });
            return {links: out, menuItems: items.slice(0, 20)};
        }""")
        with open(os.path.join(OUT, "menu.json"), "w", encoding="utf-8") as f:
            json.dump(menu, f, ensure_ascii=False, indent=2)
        log("菜单里含目标的 DOM 片段 %d 个" % len(menu.get("menuItems", [])))
        for it in menu.get("menuItems", [])[:8]:
            log("   <%s class=%s> %r" % (it["tag"], it["cls"][:60], it["text"][:80]))
            log("      html: %s" % it["html"][:300].replace("\n", " "))

        # 找含 buyin / daren 的链接
        cand_links = [l for l in menu.get("links", [])
                      if any(k in (l["href"] or "") for k in ("buyin", "daren", "talent", "square"))]
        log("含 buyin/daren 的链接: %s" % json.dumps(cand_links, ensure_ascii=False)[:600])

        # ---- 试探候选 URL ----
        log("=" * 62)
        candidates = [
            "https://buyin.jinritemai.com/",
            "https://buyin.jinritemai.com/dashboard/merchant/home",
            "https://buyin.jinritemai.com/dashboard/merchant/daren-square",
            "https://buyin.jinritemai.com/dashboard/merchant/talent-square",
            "https://fxg.jinritemai.com/ffa/buyin/home",
        ] + [l["href"] for l in cand_links if l["href"].startswith("http")]

        results = []
        for url in candidates:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                time.sleep(6)
                info = page.evaluate("""() => ({
                    url: location.href, title: document.title,
                    head: (document.body.innerText||'').slice(0, 700)
                })""")
                log("--- %s" % url)
                log("    -> %s | %s" % (info["url"][:120], info["title"][:60]))
                log("    文本: %s" % " / ".join(
                    [x for x in info["head"].splitlines() if x.strip()][:18]))
                results.append(info)
                safe = url.replace("https://", "").replace("/", "_")[:70]
                with open(os.path.join(OUT, "probe_%s.html" % safe), "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception as e:
                log("--- %s 失败: %s" % (url, str(e)[:100]))
                results.append({"url": url, "error": str(e)[:200]})

        with open(os.path.join(OUT, "url_probe.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        log("阶段 4 完成，浏览器保持 60 秒")
        time.sleep(60)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
