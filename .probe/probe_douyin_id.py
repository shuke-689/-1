# -*- coding: utf-8 -*-
"""探针：确认「达人抖音号」到底从哪取（用户 2026-09-17 要求登记飞书时要用）

用户给的取法（图 2）：在达人主页点「达人抖音主页」→ 跳到抖音主页 → 上方读「抖音号：xxx」

但前几次探针里发现 `/square_pc_api/homePage/author/profile` 的响应带
    "account_douyin": "64015570945"
疑似就是抖音号。本探针**两条路都走一遍并对比**：
  A) 抓 profile 接口的 account_douyin
  B) 点「达人抖音主页」→ 读抖音页面上的「抖音号」
若两者一致 -> 以后直接用接口字段（快、稳、不用跳转、不用登抖音）

产出：out/probe_douyin/<nick>.json + 控制台对比
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "probe_douyin")
os.makedirs(OUT, exist_ok=True)
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
PROFILE_URL = ("https://buyin.jinritemai.com/dashboard/servicehall/"
               "daren-profile?uid=%s&enter_from=1&scene=1&author_type=1")

# 找「达人抖音主页」按钮（左栏，文案精确匹配 + 尺寸合理）
FIND_DOUYIN_BTN_JS = """() => {
    const out = [];
    document.querySelectorAll('button,a,div,span').forEach(e => {
        const t = (e.innerText||'').trim();
        if (t !== '达人抖音主页') return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 80) return;
        out.push({tag:e.tagName, x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height),
                  cls:(e.className||'').toString().slice(0,80)});
    });
    return out;
}"""

# 在页面里找「抖音号」附近的文本（抖音主页顶部）
FIND_DOUYIN_NO_JS = """() => {
    const out = [];
    const re = /抖音号[：:\\s]*([A-Za-z0-9_.\\-]{2,32})/;
    document.querySelectorAll('div,span,p,td,li').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 200 || t.indexOf('抖音号') < 0) return;
        if (e.children.length > 2) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 8) return;
        const m = t.match(re);
        out.push({text: t.slice(0,80), hit: m ? m[1] : '',
                  x:Math.round(r.x), y:Math.round(r.y),
                  cls:(e.className||'').toString().slice(0,70)});
    });
    // 兜底：整页文本正则
    const whole = (document.body.innerText || '');
    const m2 = whole.match(re);
    out.push({text:'<body>', hit: m2 ? m2[1] : '', x:0, y:0, cls:'BODY'});
    return out;
}"""


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def main():
    from playwright.sync_api import sync_playwright

    ds = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"),
                        encoding="utf-8"))
    cands = [r for r in ds if r.get("contact")][:2]
    log("待探达人 %d 个：%s" % (len(cands), " / ".join(r.get("nickname", "") for r in cands)))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        prof = {}

        def on_response(resp):
            try:
                if "homePage/author/profile" not in resp.url:
                    return
                body = resp.json()
                d = (body or {}).get("data") or {}
                prof["account_douyin"] = d.get("account_douyin")
                prof["nickname"] = d.get("nickname")
                prof["fans_sum"] = d.get("fans_sum")
                prof["share_url_douyin"] = d.get("share_url_douyin")
                prof["keys"] = sorted(d.keys())
            except Exception:
                pass

        page.on("response", on_response)

        for r in cands:
            uid = r.get("uid")
            nick = r.get("nickname", "")
            prof.clear()
            log("=" * 66)
            log("达人 %s (有效期联系人: %s)" % (nick, r.get("contact")))
            rec = {"nickname": nick, "uid": uid}
            try:
                page.goto(PROFILE_URL % uid, wait_until="domcontentloaded", timeout=90_000)
                time.sleep(7)
                log("  A) 接口 account_douyin = %r" % prof.get("account_douyin"))
                log("     profile 字段: %s" % prof.get("keys"))
                rec["account_douyin"] = prof.get("account_douyin")
                rec["profile_keys"] = prof.get("keys")
                rec["share_url_douyin"] = prof.get("share_url_douyin")

                btns = page.evaluate(FIND_DOUYIN_BTN_JS)
                log("  B) 「达人抖音主页」按钮候选 %d 个: %s" % (
                    len(btns), json.dumps(btns[:2], ensure_ascii=False)))
                rec["btn"] = btns[:2]
                if not btns:
                    rec["douyin_no_page"] = None
                    json.dump(rec, open(os.path.join(OUT, "%s.json" % nick), "w",
                                        encoding="utf-8"), ensure_ascii=False, indent=1)
                    continue

                before = set(id(x) for x in ctx.pages)
                b = btns[0]
                page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
                time.sleep(6)
                newpages = [x for x in ctx.pages if id(x) not in before]
                log("  点击后新增标签页 %d 个；当前全部标签 URL：" % len(newpages))
                for x in ctx.pages:
                    try:
                        log("     %s" % x.url[:130])
                    except Exception:
                        log("     <取不到 url>")
                rec["pages_after"] = []
                for x in ctx.pages:
                    try:
                        rec["pages_after"].append(x.url)
                    except Exception:
                        pass

                target = None
                for x in (newpages or ctx.pages):
                    try:
                        if "douyin.com" in (x.url or ""):
                            target = x
                            break
                    except Exception:
                        pass
                if target is None and newpages:
                    target = newpages[0]
                if target is not None:
                    target.bring_to_front()
                    time.sleep(4)
                    hits = target.evaluate(FIND_DOUYIN_NO_JS)
                    log("  抖音页 URL: %s" % (target.url or "")[:130])
                    for h in hits:
                        log("     抖音号候选 hit=%-14r  <- %r" % (h["hit"], h["text"][:60]))
                    rec["douyin_page_url"] = target.url
                    rec["douyin_no_page"] = next(
                        (h["hit"] for h in hits if h["hit"]), "")
                    target.screenshot(path=os.path.join(OUT, "%s_douyin.png" % nick))
                    if target is not page:
                        target.close()
                    page.bring_to_front()
                    time.sleep(1.5)
                else:
                    rec["douyin_no_page"] = None

                log("  ==> A=%-16r  B=%-16r  一致=%s" % (
                    rec.get("account_douyin"), rec.get("douyin_no_page"),
                    str(rec.get("account_douyin")) == str(rec.get("douyin_no_page"))))
            except Exception as e:
                log("  ! 异常: %s" % str(e)[:180])
            json.dump(rec, open(os.path.join(OUT, "%s.json" % nick), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

        page.screenshot(path=os.path.join(OUT, "final.png"))
        log("探测完成 -> %s" % OUT)
        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
