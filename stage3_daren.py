# -*- coding: utf-8 -*-
"""阶段 3：进「精选联盟 → 找合作(达人广场) → 找达人」，侦察筛选器、列表项、达主页与接口。

产出 out/stage3/：stepN_*.html、nav_*.json、daren_probe.json、daren_api.jsonl
日志 out/stage3.log
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage3")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage3.log")
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
        log("  保存 %s 失败: %r" % (name, e))


def wait_new_page(ctx, before, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        new = [p for p in ctx.pages if p not in before]
        if new:
            pg = new[-1]
            try:
                pg.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return pg
        time.sleep(0.5)
    return None


def click_text(page, text, tag, timeout=8000):
    try:
        page.locator("text=%s" % text).first.click(timeout=timeout)
        log("  [%s] 点击 %r OK" % (tag, text))
        return True
    except Exception as e:
        log("  [%s] 点击 %r 失败: %s" % (tag, text, str(e)[:90].replace("\n", " ")))
        return False


def dump_nav(page, tag, maxlen=12):
    try:
        items = page.evaluate("""(maxlen) => {
            const out = []; const seen = new Set();
            document.querySelectorAll('a, li, span, div, button').forEach(e => {
                const t = (e.innerText || '').trim();
                if (!t || t.length > maxlen || t.includes('\\n')) return;
                const cls = (e.className || '').toString();
                if (cls.length > 200) return;
                const r = e.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) return;
                if (seen.has(t)) return; seen.add(t);
                out.push({text: t, cls: cls.slice(0, 90),
                          x: Math.round(r.x), y: Math.round(r.y),
                          w: Math.round(r.width), h: Math.round(r.height)});
            });
            return out;
        }""", maxlen)
        with open(os.path.join(OUT, "nav_%s.json" % tag), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        log("  [%s] 导航: %s" % (tag, " | ".join(i["text"] for i in items[:70])))
        return items
    except Exception as e:
        log("  [%s] dump_nav 失败: %r" % (tag, e))
        return []


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright

    api = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run",
                  "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        KEY = re.compile(r"daren|author|talent|expert|kol|square|buyin|"
                         r"contact|wechat|weixin|talent_square", re.I)

        def on_response(resp):
            try:
                u = resp.url
                ct = (resp.headers or {}).get("content-type", "") or ""
                if "json" in ct.lower() and KEY.search(u):
                    b = resp.text()
                    if b and len(b) < 2_000_000:
                        api.append({"url": u, "status": resp.status,
                                    "method": resp.request.method, "body": b})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开抖店后台首页")
        page.goto("https://fxg.jinritemai.com/ffa/mshop/homepage/index?from=buyin",
                  wait_until="domcontentloaded", timeout=90_000)
        time.sleep(6)
        log("URL: %s" % page.url)

        # ---- 精选联盟 -> 找合作 ----
        log("=" * 62)
        log("点开「精选联盟」菜单")
        click_text(page, "精选联盟", "s1")
        time.sleep(2)
        dump_nav(page, "s1_after_menu")

        log("点「找合作」")
        before = set(ctx.pages)
        click_text(page, "找合作", "s2")
        time.sleep(5)
        newp = wait_new_page(ctx, before, 15)
        if newp:
            page = newp
            log("  已切到新标签页")
        log("URL: %s  title: %s" % (page.url, page.title()))
        save(page, "s2_zhaohezuo")
        dump_nav(page, "s2")

        # ---- 找达人 页签 ----
        log("=" * 62)
        for name in ("找达人", "达人广场", "找主播", "达人库"):
            if click_text(page, name, "s3", timeout=6000):
                time.sleep(6)
                newp2 = wait_new_page(ctx, set(list(ctx.pages)), 3)
                log("URL: %s  title: %s" % (page.url, page.title()))
                break
        save(page, "s3_daren")
        dump_nav(page, "s3")

        # ---- 深入侦察 ----
        log("=" * 62)
        log("侦察达人广场筛选器 / 列表 / 表格")
        probe = page.evaluate("""() => {
            const rect = e => { const r = e.getBoundingClientRect();
                return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
            const txt = e => (e.innerText || '').trim();
            const all = Array.from(document.querySelectorAll('*'));
            const shortTxt = e => { const t = txt(e); return t.length ? t.slice(0,80) : ''; };

            const filters = all.filter(e => /filter|Filter|condition|Condition|screen|Screen|select|Select|dropdown|Dropdown|option|Option/.test((e.className||'').toString())
                    && e.children.length < 16 && shortTxt(e))
                .slice(0, 60).map(e => ({tag:e.tagName, cls:(e.className||'').toString().slice(0,110),
                                         text:shortTxt(e), rect:rect(e)}));
            const headers = Array.from(document.querySelectorAll('th, [class*="thead"] *, [class*="headerRow"] *, [role="columnheader"]'))
                .slice(0, 60).map(e => ({tag:e.tagName, text:shortTxt(e), cls:(e.className||'').toString().slice(0,90)}));
            const cards = all.filter(e => {
                    const c = (e.className||'').toString();
                    return /card|Card|daren|author|talent|item|Item/.test(c)
                        && e.children.length >= 2 && e.children.length <= 14
                        && txt(e).length > 20 && txt(e).length < 900;
                }).slice(0, 20)
                .map(e => ({cls:(e.className||'').toString().slice(0,120), text:shortTxt(e),
                            nchild:e.children.length, rect:rect(e)}));
            const inputs = Array.from(document.querySelectorAll('input, textarea, [class*="Select"] [class*="value"]'))
                .slice(0, 50).map(e => ({tag:e.tagName, ph:e.getAttribute('placeholder')||'',
                                         cls:(e.className||'').toString().slice(0,90), rect:rect(e)}));
            const btns = Array.from(document.querySelectorAll('button, [class*="btn"], [class*="Button"]'))
                .slice(0, 60).map(e => ({text:shortTxt(e), cls:(e.className||'').toString().slice(0,90), rect:rect(e)}))
                .filter(x => x.text);
            return {url: location.href, title: document.title,
                    filters, headers, cards, inputs, buttons: btns,
                    bodyHead: (document.body.innerText||'').slice(0, 5000)};
        }""")
        with open(os.path.join(OUT, "daren_probe.json"), "w", encoding="utf-8") as f:
            json.dump(probe, f, ensure_ascii=False, indent=2)
        log("daren_probe.json 已保存")
        log("  标题: %s" % probe.get("title"))
        log("  筛选器 %d / 表头 %d / 卡片 %d / 输入 %d / 按钮 %d" % (
            len(probe.get("filters", [])), len(probe.get("headers", [])),
            len(probe.get("cards", [])), len(probe.get("inputs", [])),
            len(probe.get("buttons", []))))
        log("  ---- body 开头 ----")
        for line in (probe.get("bodyHead", "") or "").splitlines()[:45]:
            if line.strip():
                log("    | %s" % line.strip()[:110])

        with open(os.path.join(OUT, "daren_api.jsonl"), "w", encoding="utf-8") as f:
            for r in api:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log("接口响应 %d 条:" % len(api))
        seen = set()
        for r in api:
            k = r["url"].split("?")[0]
            if k in seen:
                continue
            seen.add(k)
            log("   API %s %s" % (r["method"], r["url"][:170]))

        log("阶段 3 完成，浏览器保持 120 秒")
        time.sleep(120)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
