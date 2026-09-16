# -*- coding: utf-8 -*-
"""登录助手：打开独立 Edge 配置，让用户扫一次码，登录后自动确认。

为什么需要：`.edge-auto/profile` 的登录态会过期（或被站点踢下线），
过期后 `collect.py` 打开达人广场只会跳到抖音电商公开落地页，
表现为「未找到类目按钮」（很容易误判成选择器坏了）。

用法：
  python login.py            # 打开登录页、自动点「登录」调出二维码，然后等待扫码
  python login.py --check    # 只检查当前登录态
环境变量：
  WAIT_SEC   最长等待秒数（默认 900）
  POLL_SEC   轮询间隔秒（默认 5）
"""
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

import collect as C  # noqa: E402

# ⚠️ collect.py import 时会把 sys.stdout 换成新的 TextIOWrapper；
#    必须在 import 之后再 reconfigure，否则旧 wrapper 被 GC 时会关掉底层 buffer
#    （踩过：ValueError: I/O operation on closed file）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WAIT_SEC = int(os.environ.get("WAIT_SEC", "900"))
POLL_SEC = int(os.environ.get("POLL_SEC", "5"))

# 只有登录后的达人广场才会出现这些字样
LOGGED_IN_MARK = ("主推类目", "找达人", "按商品找达人")

# 巨量百应登录页（比在 marketing 落地页上找「登录」按钮更可靠）
LOGIN_URL = os.environ.get("LOGIN_URL", "https://buyin.jinritemai.com/login")

CLICK_LOGIN_JS = """() => {
    let hit = null;
    document.querySelectorAll('button, a, div, span').forEach(e => {
        if (hit) return;
        const t = (e.innerText || '').trim();
        if (t !== '登录' && t !== '立即登录') return;
        if (e.children.length > 1) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        hit = {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
    });
    return hit;
}"""

# 是否出现二维码（img/canvas + 扫码字样）
QR_JS = """() => {
    const txt = document.body ? (document.body.innerText || '') : '';
    const hasScanWord = /扫码|二维码|抖音App|抖音 App|扫一扫/.test(txt);
    const imgs = Array.from(document.querySelectorAll('img, canvas')).filter(e => {
        const r = e.getBoundingClientRect();
        return r.width >= 120 && r.height >= 120;
    });
    return {hasScanWord: hasScanWord, bigImg: imgs.length};
}"""


def read_body(page, tries=4):
    """读 body 文本。页面可能正在跳转，evaluate 会抛异常 -> 重试。"""
    body, err = "", ""
    for _ in range(tries):
        try:
            body = page.evaluate("() => (document.body.innerText || '').slice(0, 4000)")
            err = ""
            if body.strip():
                break
        except Exception as e:
            err = str(e)[:60]
        time.sleep(2.0)
    return body, err


def judge(body, err):
    """根据正文判断登录态，返回 (是否登录, 诊断串)。"""
    hit = [m for m in LOGGED_IN_MARK if m in body]
    if hit:
        return True, "已登录（命中 %s）" % "/".join(hit)
    if not body.strip():
        return False, "页面不可读/正在跳转: %s" % err
    if "登录" in body:
        return False, "未登录（页面含「登录」按钮）"
    return False, "未登录（未见达人广场内容）"


def alive_pages(ctx):
    out = []
    try:
        for pg in ctx.pages:
            try:
                if not pg.is_closed():
                    out.append(pg)
            except Exception:
                pass
    except Exception:
        pass
    return out


def check_any(ctx):
    """遍历**所有标签页**（登录常在新标签页里完成）。返回 (是否登录, 诊断, 命中的页)。"""
    pages = alive_pages(ctx)
    if not pages:
        return False, "没有可用标签页", None
    why_main = ""
    for i, pg in enumerate(pages):
        body, err = read_body(pg, tries=2)
        ok, why = judge(body, err)
        if ok:
            return True, "[标签%d] %s" % (i + 1, why), pg
        if i == 0:
            why_main = why
    return False, why_main or "未登录", None


def shot(page, name):
    try:
        page.screenshot(path=os.path.join(BASE, "out", "collect", name))
    except Exception:
        pass


def shot_all(ctx, prefix):
    for i, pg in enumerate(alive_pages(ctx)):
        try:
            pg.screenshot(path=os.path.join(
                BASE, "out", "collect", "%s_%d.png" % (prefix, i + 1)))
        except Exception:
            pass


def main():
    check_only = "--check" in sys.argv
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(C.DAREN, wait_until="domcontentloaded", timeout=90_000)
        except Exception as e:
            print("goto 异常:", str(e)[:120])
        time.sleep(8)

        ok, why, _ = check_any(ctx)
        print("当前状态：%s" % why)
        if ok:
            print("无需重新登录。")
        elif check_only:
            print("需要重新登录。请运行：  python login.py")
        else:
            print("=" * 66)
            print("请在刚打开的 Edge 窗口里用**抖音 App 扫码登录**（精选联盟 / 巨量百应账号）。")
            print("登录成功后本脚本会自动检测到，无需其他操作。最长等 %d 秒。" % WAIT_SEC)
            print("=" * 66)

            # ① 先在当前页找「登录」按钮点一下（调出二维码）
            clicked = False
            try:
                hit = page.evaluate(CLICK_LOGIN_JS)
                if hit:
                    page.mouse.click(hit["x"], hit["y"])
                    time.sleep(5)
                    clicked = True
                    print("已点击页面上的「登录」按钮。")
            except Exception as e:
                print("点「登录」失败（可手动点）：%s" % str(e)[:80])

            # ② 当前页没有二维码 -> 直接新开标签页到官方登录地址（更可靠）
            qr = None
            try:
                qr = page.evaluate(QR_JS)
            except Exception:
                pass
            need_fallback = (not clicked) or (not qr) or \
                            (qr and not qr.get("hasScanWord") and qr.get("bigImg", 0) == 0)
            if need_fallback:
                print("当前页未出现二维码 -> 打开官方登录地址：%s" % LOGIN_URL)
                try:
                    lp = ctx.new_page()
                    lp.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
                    time.sleep(6)
                    try:
                        lp.bring_to_front()
                    except Exception:
                        pass
                except Exception as e:
                    print("打开登录地址失败：%s" % str(e)[:100])
            else:
                print("二维码应已出现，请直接扫码。")

            shot_all(ctx, "login_qr")

            t0 = time.time()
            last = ""
            while time.time() - t0 < WAIT_SEC:
                time.sleep(POLL_SEC)
                ok, why, hit_pg = check_any(ctx)
                if why != last:
                    print("[%s] %s" % (time.strftime("%H:%M:%S"), why))
                    last = why
                if ok:
                    # 登录页不是达人广场页 -> 回到达人广场并确认
                    try:
                        page.goto(C.DAREN, wait_until="domcontentloaded",
                                  timeout=90_000)
                        time.sleep(8)
                    except Exception:
                        pass
                    ok2, why2, _ = check_any(ctx)
                    shot(page, "login_ok.png")
                    print("=" * 66)
                    if ok2:
                        print("✅ 登录成功：%s" % why2)
                    else:
                        print("⚠️ 检测到登录动作，但达人广场复核未通过：%s" % why2)
                        print("   可再跑一次 python login.py --check 确认。")
                    print("现在可以跑采集：")
                    print("   export MAX_SCROLL=60 MAX_CANDIDATE=300 BATCH_COOLDOWN=300")
                    print("   python collect_30.py")
                    print("=" * 66)
                    break
            else:
                print("等待超时（%d 秒），仍未检测到登录。可重跑  python login.py" % WAIT_SEC)
                shot_all(ctx, "login_timeout")
        time.sleep(2)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
