# -*- coding: utf-8 -*-
"""探针 v2：把「取达人抖音号」做成可复用的稳定流程（用户 2026-09-17）

v1 结论（out/probe_douyin/）：
  · `homePage/author/profile` 里**没有** account_douyin 了（返回 None）→ 只能走抖音主页
  · 点「达人抖音主页」会**新开一个标签页** douyin.com/user/<sec_uid>
    页面上能读到 `抖音号：89435391431`
  · 但点击有抖动：2 个达人里 1 个没开出新页 → 必须**加重试**

v2 要确认两件事：
  1. 「达人抖音主页」元素的 **href** 是不是 douyin.com 链接
     → 若是：拿 href 直接 `goto`，彻底绕开点击抖动（更稳更快）
  2. 点击 + 重试 3 次的成功率

产出：out/probe_douyin2/<nick>.json
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "probe_douyin2")
os.makedirs(OUT, exist_ok=True)
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
PROFILE_URL = ("https://buyin.jinritemai.com/dashboard/servicehall/"
               "daren-profile?uid=%s&enter_from=1&scene=1&author_type=1")
DOUYIN_NO_RE = re.compile(r"抖音号[：:]\s*([A-Za-z0-9_.\-]{2,32})")

# 找「达人抖音主页」，优先返回 A 标签（带 href）
FIND_BTN_JS = """() => {
    const out = [];
    document.querySelectorAll('a,div,span,button').forEach(e => {
        const t = (e.innerText||'').trim();
        if (t !== '达人抖音主页') return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 80) return;
        out.push({tag: e.tagName, href: e.getAttribute('href') || '',
                  x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height),
                  cls: (e.className||'').toString().slice(0, 80)});
    });
    // A 优先，其次体积大一点的
    out.sort((a, b) => (a.tag === 'A' ? -1 : 0) - (b.tag === 'A' ? -1 : 0)
                       || (b.w * b.h) - (a.w * a.h));
    return out;
}"""


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def read_douyin_no(pg):
    """从抖音主页读「抖音号」；取不到返回 ''。"""
    try:
        txt = pg.evaluate("() => document.body.innerText || ''")
    except Exception:
        return ""
    m = DOUYIN_NO_RE.search(txt or "")
    return m.group(1) if m else ""


def main():
    from playwright.sync_api import sync_playwright

    ds = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"),
                        encoding="utf-8"))
    cands = [r for r in ds if r.get("contact")][:4]
    log("待探达人 %d 个：%s" % (len(cands), " / ".join(r.get("nickname", "") for r in cands)))

    stats = {"href_ok": 0, "click_ok": 0, "fail": 0}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for r in cands:
            uid, nick = r.get("uid"), r.get("nickname", "")
            log("=" * 66)
            log("达人 %s" % nick)
            rec = {"nickname": nick, "uid": uid}
            try:
                page.goto(PROFILE_URL % uid, wait_until="domcontentloaded", timeout=90_000)
                time.sleep(6)
                btns = page.evaluate(FIND_BTN_JS)
                log("  「达人抖音主页」候选 %d: %s" % (
                    len(btns), json.dumps(btns[:2], ensure_ascii=False)))
                rec["btn"] = btns[:2]
                if not btns:
                    stats["fail"] += 1
                    rec["douyin_no"] = ""
                    json.dump(rec, open(os.path.join(OUT, "%s.json" % nick), "w",
                                        encoding="utf-8"), ensure_ascii=False, indent=1)
                    continue

                b = btns[0]
                href = (b.get("href") or "").strip()
                got = ""

                # ---- 路线1：href 直接跳（最稳） ----
                if href.startswith("http") and "douyin.com" in href:
                    log("  路线1 href=%s" % href[:110])
                    stats["href_ok"] += 1
                    page.goto(href, wait_until="domcontentloaded", timeout=90_000)
                    time.sleep(6)
                    got = read_douyin_no(page)
                    log("     -> 抖音号=%r" % got)

                # ---- 路线2：点击新开标签页（重试 3 次） ----
                if not got:
                    if href:
                        log("  路线1 未成（href=%r），改走点击" % href[:60])
                    for k in range(3):
                        before = len(ctx.pages)
                        page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
                        time.sleep(6)
                        newp = [x for x in ctx.pages
                                if "douyin.com" in (x.url or "") and x is not page]
                        if newp:
                            tgt = newp[-1]
                            tgt.bring_to_front()
                            time.sleep(4)
                            got = read_douyin_no(tgt)
                            log("     第%d次点击 -> %s  抖音号=%r" % (
                                k + 1, (tgt.url or "")[:90], got))
                            tgt.close()
                            page.bring_to_front()
                            time.sleep(1.5)
                            if got:
                                break
                        else:
                            log("     第%d次点击：没开出抖音页" % (k + 1))
                            time.sleep(2)

                if got:
                    stats["click_ok"] += 1
                else:
                    stats["fail"] += 1
                rec["douyin_no"] = got
                log("  ==> 抖音号 = %r" % got)
            except Exception as e:
                stats["fail"] += 1
                log("  ! 异常: %s" % str(e)[:180])
            json.dump(rec, open(os.path.join(OUT, "%s.json" % nick), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

        log("=" * 66)
        log("统计: href路线=%d / 最终取到=%d / 失败=%d" % (
            stats["href_ok"], stats["click_ok"], stats["fail"]))
        log("探测完成 -> %s" % OUT)
        time.sleep(3)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
