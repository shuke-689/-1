# -*- coding: utf-8 -*-
"""阶段 5：进「找达人」，侦察筛选器 / 列表卡片 / 达人主页联系方式区，并抓列表接口。

产出 out/stage5/
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage5")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage5.log")
os.makedirs(OUT, exist_ok=True)
HOME = "https://buyin.jinritemai.com/dashboard/merchant/home"


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save(page, name):
    with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8") as f:
        f.write(page.content())
    with open(os.path.join(OUT, name + "_url.txt"), "w", encoding="utf-8") as f:
        f.write(page.url)


CARD_JS = """() => {
    const rect = e => { const r = e.getBoundingClientRect();
        return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
    const t = e => (e.innerText || '').trim();
    // 找看起来像达人卡片的容器
    const all = Array.from(document.querySelectorAll('div, li, section'));
    const cards = all.filter(e => {
        const s = t(e);
        if (s.length < 40 || s.length > 1500) return false;
        if (!/粉丝|结算|带货|达人|合作/.test(s)) return false;
        const r = e.getBoundingClientRect();
        if (r.width < 200 || r.height < 60) return false;
        // 尽量取最内层
        const inner = Array.from(e.children).some(c => {
            const cs = (c.innerText||'').trim();
            return cs.length >= 40 && /粉丝|结算|带货/.test(cs);
        });
        return !inner;
    }).slice(0, 6);
    return cards.map(e => {
        const kids = Array.from(e.querySelectorAll('*')).slice(0, 120).map(k => {
            const kt = t(k);
            if (!kt || kt.length > 60) return null;
            return {tag:k.tagName, cls:(k.className||'').toString().slice(0,80),
                    text:kt, rect:rect(k)};
        }).filter(Boolean);
        return {cls:(e.className||'').toString().slice(0,140), text:t(e).slice(0,600),
                rect:rect(e), kids:kids.slice(0, 60)};
    });
}"""


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright

    api = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        KEY = re.compile(r"daren|author|talent|expert|kol|square|contact|"
                         r"wechat|weixin|talent_square|search", re.I)

        def on_response(resp):
            try:
                u = resp.url
                ct = (resp.headers or {}).get("content-type", "") or ""
                if "json" in ct.lower() and KEY.search(u):
                    b = resp.text()
                    if b and len(b) < 3_000_000:
                        api.append({"url": u, "method": resp.request.method, "body": b})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开精选联盟商家版首页")
        page.goto(HOME, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(6)
        log("URL: %s | %s" % (page.url, page.title()))

        # ---- 点「找达人」 ----
        log("点击「找达人」页签")
        before = set(ctx.pages)
        clicked = False
        for sel in ["text=找达人", "a:has-text('找达人')", "[class*=tab]:has-text('找达人')"]:
            try:
                page.locator(sel).first.click(timeout=7000)
                clicked = True
                log("  用 %s 点击成功" % sel)
                break
            except Exception as e:
                log("  %s 失败: %s" % (sel, str(e)[:70].replace("\n", " ")))
        time.sleep(8)
        new = [x for x in ctx.pages if x not in before]
        if new:
            page = new[-1]
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            log("  切到新标签页")
        log("找达人 URL: %s | %s" % (page.url, page.title()))
        save(page, "daren_page")

        # ---- 筛选器 / 列表 ----
        log("=" * 62)
        probe = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const t = e => (e.innerText || '').trim();
            const all = Array.from(document.querySelectorAll('*'));
            const picks = (re, max, maxlen) => all.filter(e => re.test((e.className||'').toString())
                    && e.children.length < 16 && t(e) && t(e).length < maxlen)
                .slice(0, max).map(e => ({tag:e.tagName, cls:(e.className||'').toString().slice(0,110),
                                          text:t(e).slice(0,90), rect:rect(e)}));
            return {
                url: location.href, title: document.title,
                filters: picks(/filter|Filter|condition|Condition|screen|Screen|tab|Tab|select|Select|radio|Radio|checkbox|Checkbox/, 90, 120),
                inputs: Array.from(document.querySelectorAll('input, textarea'))
                    .slice(0,50).map(e => ({tag:e.tagName, ph:e.getAttribute('placeholder')||'',
                                            cls:(e.className||'').toString().slice(0,90), rect:rect(e)})),
                buttons: Array.from(document.querySelectorAll('button, [class*="btn"], [class*="Button"]'))
                    .slice(0,60).map(e => ({text:t(e).slice(0,40), cls:(e.className||'').toString().slice(0,90), rect:rect(e)}))
                    .filter(x => x.text),
                bodyHead: (document.body.innerText||'').slice(0, 6000),
            };
        }""")
        with open(os.path.join(OUT, "daren_probe.json"), "w", encoding="utf-8") as f:
            json.dump(probe, f, ensure_ascii=False, indent=2)
        log("probe 保存. 筛选相关 %d / 输入 %d / 按钮 %d" % (
            len(probe["filters"]), len(probe["inputs"]), len(probe["buttons"])))
        log("  ---- 页面文本 ----")
        for line in (probe["bodyHead"] or "").splitlines()[:70]:
            if line.strip():
                log("   | %s" % line.strip()[:120])
        log("  ---- 筛选相关元素 ----")
        for f in probe["filters"][:45]:
            log("   · <%s> %r cls=%s @%s" % (f["tag"], f["text"][:40], f["cls"][:70], (f["rect"]["x"], f["rect"]["y"])))

        # ---- 卡片结构 ----
        try:
            cards = page.evaluate(CARD_JS)
            with open(os.path.join(OUT, "cards.json"), "w", encoding="utf-8") as f:
                json.dump(cards, f, ensure_ascii=False, indent=2)
            log("卡片样本 %d 个" % len(cards))
            for c in cards[:2]:
                log("  === 卡片 cls=%s" % c["cls"][:90])
                log("      text=%r" % c["text"][:300].replace("\n", " / "))
                for k in c["kids"][:40]:
                    log("        <%s> %r @%s cls=%s" % (k["tag"], k["text"], (k["rect"]["x"], k["rect"]["y"]), k["cls"][:60]))
        except Exception as e:
            log("卡片解析失败: %r" % e)

        # ---- 接口 ----
        with open(os.path.join(OUT, "daren_api.jsonl"), "w", encoding="utf-8") as f:
            for r in api:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        uniq = {}
        for r in api:
            uniq.setdefault(r["url"].split("?")[0], r)
        log("接口响应 %d 条 / 去重 %d 个:" % (len(api), len(uniq)))
        for u, r in uniq.items():
            log("   API %s %s" % (r["method"], u[:170]))

        log("阶段 5 完成，浏览器保持 120 秒")
        time.sleep(120)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
