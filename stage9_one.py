# -*- coding: utf-8 -*-
"""阶段 9：跑通单个达人的完整链路（修正版）。

修正点：
  1. 两个闭眼图标时，按「达人微信号」标签的 y 坐标就近匹配（取下方那个），不取第一个
  2. 揭开微信号后，重新扫描并点击该行右侧的「复制」图标
  3. 打开达人主页用已知 URL 规律：/dashboard/servicehall/daren-profile?uid=<uid>
  4. 筛选项点击之间先按 Esc 关闭浮层，避免互相遮挡

产出 out/stage9/，日志 out/stage9.log
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "stage9")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
LOG = os.path.join(BASE, "out", "stage9.log")
os.makedirs(OUT, exist_ok=True)
DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
PROFILE_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=%s&enter_from=1&scene=1&author_type=1"


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# 读取达人主页上「联系方式」行的结构
SCAN_JS = """() => {
    const rect = e => { const r = e.getBoundingClientRect();
        return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
    const out = {rows: [], icons: []};
    document.querySelectorAll('*').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 60 || t.includes('\\n')) return;
        if (!/达人微信号|达人手机号|微信|复制/.test(t)) return;
        const r = e.getBoundingClientRect();
        if (r.width < 5 || r.height < 5) return;
        out.rows.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,110),
                       text:t, rect:rect(e)});
    });
    document.querySelectorAll('span, i, div, svg, img, button').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 6 || r.height < 6 || r.width > 70 || r.height > 70) return;
        const cls = (e.className||'').toString();
        if (!/contact-item-btn|icon|Icon|copy|Copy|eye|Eye|look|Look/.test(cls)) return;
        out.icons.push({tag:e.tagName, cls:cls.slice(0,110), rect:rect(e),
                        title:(e.getAttribute&&(e.getAttribute('title')||e.getAttribute('aria-label'))||''),
                        src:(e.getAttribute&&e.getAttribute('src')||'').slice(0,110)});
    });
    out.body = (document.body.innerText||'').slice(0,3000);
    return out;
}"""


def pick_wechat_eye(scan):
    """在「达人微信号」行右侧选图标：y 就近匹配，两个时取下方那个"""
    label = None
    for r in scan["rows"]:
        if "达人微信号" in r["text"]:
            label = r
            break
    if not label:
        return None, "未找到达人微信号行"
    ly = label["rect"]["y"]
    lx = label["rect"]["x"]
    cand = [i for i in scan["icons"]
            if i["rect"]["x"] > lx
            and abs(i["rect"]["y"] - ly) <= 25]
    if not cand:
        return None, "微信号行右侧没有候选图标"
    # 按与标签 y 的距离排序；距离相同(如两个都在附近)则取 y 更大的（下方那个）
    cand.sort(key=lambda c: (abs(c["rect"]["y"] - ly), -c["rect"]["y"]))
    return cand[0], "候选 %d 个: %s" % (len(cand), [(c["rect"]["x"], c["rect"]["y"]) for c in cand])


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
                if b and len(b) < 2_000_000:
                    apis.append({"url": u, "method": resp.request.method, "body": b})
            except Exception:
                pass

        page.on("response", on_response)

        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)

        # ---- 筛选 ----
        def chip(text, tag, opt=None):
            try:
                page.locator("text=%s" % text).first.click(timeout=6000)
                time.sleep(1.5)
                if opt:
                    try:
                        page.locator("text=%s" % opt).first.click(timeout=5000)
                        log("  [%s] %r -> %r OK" % (tag, text, opt))
                    except Exception as e:
                        log("  [%s] 选 %r 失败: %s" % (tag, opt, str(e)[:60].replace("\n", " ")))
                        return False
                else:
                    log("  [%s] %r OK" % (tag, text))
                time.sleep(1.2)
                page.keyboard.press("Escape")
                time.sleep(0.6)
                return True
            except Exception as e:
                log("  [%s] %r 失败: %s" % (tag, text, str(e)[:70].replace("\n", " ")))
                page.keyboard.press("Escape")
                time.sleep(0.5)
                return False

        log("应用筛选")
        chip("个护家清", "cat")
        chip("视频结算总额", "vid", "1w-10w")
        chip("粉丝量", "fans", "10w以下")
        chip("有联系方式", "contact")
        time.sleep(6)

        # ---- 取达人 uid ----
        target = None
        for a in reversed(apis):
            if "search_feed_author" in a["url"]:
                try:
                    d = json.loads(a["body"])
                    lst = (d.get("data") or {}).get("list") or []
                    if lst:
                        target = lst[0]
                        break
                except Exception:
                    pass
        if not target:
            log("✗ 没拿到达人数据")
            return
        ab = target["author_base"]
        uid = ab["uid"]
        log("目标达人: %r 粉丝=%s 性别=%s %s" % (ab["nickname"], ab["fans_num"], ab["gender"], ab["city"]))
        log("uid=%s..." % uid[:60])

        # ---- 打开达人主页 ----
        url = PROFILE_URL % uid
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)
        log("达人主页 URL: %s | %s" % (page.url[:90], page.title()))

        scan = page.evaluate(SCAN_JS)
        log("=" * 62)
        log("STEP1 初始状态")
        for r in scan["rows"]:
            log("   ROW %r @%s" % (r["text"][:60], (r["rect"]["x"], r["rect"]["y"])))
        for i in scan["icons"]:
            log("   ICON <%s> @%s %sx%s cls=%s" % (i["tag"], (i["rect"]["x"], i["rect"]["y"]),
                                                   i["rect"]["w"], i["rect"]["h"], i["cls"][:60]))

        # ---- 点微信号的眼睛（下方那个） ----
        log("=" * 62)
        log("STEP2 点击「达人微信号」行的眼睛（就近匹配，两个取下方）")
        eye, why = pick_wechat_eye(scan)
        log("  %s" % why)
        if not eye:
            log("  ✗ 未定位到眼睛")
        else:
            log("  选中图标 @%s cls=%s" % ((eye["rect"]["x"], eye["rect"]["y"]), eye["cls"][:60]))
            page.mouse.click(eye["rect"]["x"] + eye["rect"]["w"] / 2,
                             eye["rect"]["y"] + eye["rect"]["h"] / 2)
            time.sleep(2.5)

        scan2 = page.evaluate(SCAN_JS)
        log("  揭开后含联系方式的行:")
        for r in scan2["rows"]:
            log("     %r" % r["text"][:70])
        log("  当前图标:")
        for i in scan2["icons"]:
            log("     <%s> @%s %sx%s cls=%s" % (i["tag"], (i["rect"]["x"], i["rect"]["y"]),
                                                i["rect"]["w"], i["rect"]["h"], i["cls"][:60]))

        # ---- 点复制 ----
        log("=" * 62)
        log("STEP3 点击复制")
        before_clip = w.get_clipboard()
        log("  点击前剪贴板: %r" % before_clip)
        copied = False
        # 优先点「达人微信号」行右侧的图标（现在应该变成复制图标）
        eye2, why2 = pick_wechat_eye(scan2)
        if eye2:
            log("  复制候选: %s" % why2)
            page.mouse.click(eye2["rect"]["x"] + eye2["rect"]["w"] / 2,
                             eye2["rect"]["y"] + eye2["rect"]["h"] / 2)
            time.sleep(2)
            clip = w.get_clipboard()
            log("  点击后剪贴板: %r" % clip)
            copied = bool(clip and clip != before_clip)
        if not copied:
            for t in ("复制", "复制微信号", "复 制"):
                try:
                    page.locator("text=%s" % t).first.click(timeout=2500)
                    log("  文本点击 %r OK" % t)
                    time.sleep(2)
                    break
                except Exception:
                    pass
            clip = w.get_clipboard()
            log("  最终剪贴板: %r" % clip)

        with open(os.path.join(OUT, "scan.json"), "w", encoding="utf-8") as f:
            json.dump({"initial": scan, "after_eye": scan2}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(OUT, "detail.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
        with open(os.path.join(OUT, "api.jsonl"), "w", encoding="utf-8") as f:
            for r in apis:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        log("阶段 9 完成，浏览器保持 150 秒")
        time.sleep(150)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
