# -*- coding: utf-8 -*-
"""阶段 1：启动独立 Edge（专用配置）→ 等待扫码登录精选联盟 → 侦察「找达人」页面结构。

产出到 out/stage1/：
  - nav_links.json      导航链接清单
  - list_page.html      找达人页面完整 HTML
  - api_capture.jsonl   页面 XHR 接口响应（JSON），用于判断能否直接拿结构化数据
  - probe.json          综合结论

登录态会持久化在 .edge-auto/profile，后续阶段直接复用，无需再扫码。
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage1")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage1.log")

os.makedirs(OUT, exist_ok=True)
os.makedirs(PROFILE, exist_ok=True)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    open(LOG, "w", encoding="utf-8").close()

    from playwright.sync_api import sync_playwright

    api_records = []

    with sync_playwright() as p:
        log("启动 Edge（独立配置）...")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            channel="msedge",
            headless=False,
            no_viewport=True,
            args=[
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                url = resp.url
                if "json" in ct.lower() and any(k in url for k in (
                        "daren", "author", "talent", "expert", "kol", "search",
                        "square", "list", "material", "buyin")):
                    body = resp.text()
                    if body and len(body) < 3_000_000:
                        api_records.append({"url": url, "status": resp.status,
                                            "method": resp.request.method, "body": body})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开精选联盟登录页...")
        page.goto("https://fxg.jinritemai.com/login/common?from=buyin",
                  wait_until="domcontentloaded", timeout=90_000)
        time.sleep(4)
        log("当前 URL: %s" % page.url)

        # ---- 等待登录 ----
        log("等待登录（最多 30 分钟）...")
        deadline = time.time() + 30 * 60
        logged_in = False
        LOGIN_BLOCKERS = ("扫码登录", "立即登录", "请先登录", "登录后查看",
                          "手机扫码", "验证码登录", "登录/注册",
                          "手机登录", "邮箱登录", "验证码")
        tick = 0
        while time.time() < deadline:
            try:
                txt = page.inner_text("body")[:6000]
            except Exception:
                txt = ""
            has_nav = ("找达人" in txt) or ("达人广场" in txt) or ("推商品" in txt)
            blocked = any(b in txt for b in LOGIN_BLOCKERS)
            if has_nav and not blocked:
                logged_in = True
                break
            tick += 1
            if tick % 5 == 0:
                log("  ...仍在等待登录（已等 %d 分 %d 秒）URL=%s" % (
                    int((time.time() - (deadline - 30 * 60)) // 60),
                    int((time.time() - (deadline - 30 * 60)) % 60),
                    page.url[:80]))
            time.sleep(4)

        log("登录状态: %s" % ("已登录" if logged_in else "超时未检测到登录"))
        if not logged_in:
            log("仍继续侦察，保存现状供排查")

        # 登录后回到精选联盟首页，拿到真实后台入口
        log("登录后回到精选联盟首页")
        try:
            page.goto("https://buyin.jinritemai.com/", wait_until="domcontentloaded", timeout=90_000)
        except Exception as e:
            log("回首页失败: %r" % e)
        time.sleep(6)
        log("首页 URL: %s" % page.url)

        # ---- 侦察导航 ----
        nav = page.eval_on_selector_all(
            "a, [role='tab'], [class*='tab'], [class*='menu'] li, [class*='nav'] li",
            """els => els.map(e => ({
                 tag: e.tagName,
                 text: (e.innerText || '').trim().slice(0, 30),
                 href: e.getAttribute('href') || '',
                 cls: (e.className || '').toString().slice(0, 120)
               })).filter(x => x.text)""")
        with open(os.path.join(OUT, "nav_links.json"), "w", encoding="utf-8") as f:
            json.dump(nav, f, ensure_ascii=False, indent=2)
        log("导航项 %d 条，已保存 nav_links.json" % len(nav))

        # ---- 尝试进入找达人 ----
        target_url = None
        for item in nav:
            if "找达人" in (item.get("text") or "") or "达人广场" in (item.get("text") or ""):
                if item.get("href"):
                    target_url = item["href"]
                    break

        if target_url:
            if target_url.startswith("/"):
                target_url = "https://buyin.jinritemai.com" + target_url
            log("找到入口链接: %s" % target_url)
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=90_000)
            except Exception as e:
                log("直接跳转失败: %r" % e)
        else:
            log("导航里没找到 href，尝试点击「找达人」")
            try:
                page.click("text=找达人", timeout=15_000)
            except Exception as e:
                log("点击失败: %r" % e)

        time.sleep(8)
        log("找达人页 URL: %s" % page.url)

        # ---- 保存页面结构 ----
        html = page.content()
        with open(os.path.join(OUT, "list_page.html"), "w", encoding="utf-8") as f:
            f.write(html)
        log("HTML 已保存（%d 字节）" % len(html))

        # 提炼可交互元素：筛选器 / 表格表头 / 按钮
        summary = page.evaluate("""() => {
            const pick = (sel) => Array.from(document.querySelectorAll(sel)).map(e => ({
                text: (e.innerText || '').trim().slice(0, 40),
                cls: (e.className || '').toString().slice(0, 100),
                placeholder: e.getAttribute('placeholder') || '',
            })).filter(x => x.text || x.placeholder);
            return {
                url: location.href,
                title: document.title,
                buttons: pick("button, [class*='btn']").slice(0, 120),
                inputs: pick("input").slice(0, 60),
                labels: pick("label, [class*='label'], [class*='filter']").slice(0, 120),
                ths: pick("th, [class*='header'] [class*='cell'], [class*='table'] [class*='row']:first-child [class*='cell']").slice(0, 60),
            };
        }""")
        with open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log("可交互元素摘要已保存 probe.json")

        with open(os.path.join(OUT, "api_capture.jsonl"), "w", encoding="utf-8") as f:
            for r in api_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log("捕获到接口响应 %d 条，已保存 api_capture.jsonl" % len(api_records))
        for r in api_records[:25]:
            log("   API %s %s" % (r["method"], r["url"][:150]))

        log("阶段 1 完成。浏览器保持打开 60 秒供你确认，随后自动关闭。")
        time.sleep(60)
        try:
            ctx.close()
        except Exception:
            pass

    log("结束")


if __name__ == "__main__":
    main()
