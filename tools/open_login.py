# -*- coding: utf-8 -*-
"""打开抖店/精选联盟登录页并**一直开着**，等使用者重新登录（2026-09-19 新增）。

和 `login.py` 的区别：
  - `login.py` 会先判断登录态：**已登录就直接退出并关掉浏览器**，
    登录成功也会自动关窗口 —— 使用者常常「刚看到登录页就没了」。
  - 本脚本**不做早退**：无论当前是否已登录，都打开登录页并保持窗口开着，
    直到使用者自己关掉那个 Edge 窗口（或等满 WAIT_SEC）。

⚠️ cookie 落盘：Chromium 的会话 cookie 需要**浏览器被干净关闭**才写盘，
   所以请让使用者在自动化那个 Edge 窗口里登录完，然后**自己关掉窗口**。

用法：
  python tools/open_login.py                 # 打开登录页并保持（默认 3600 秒）
  python tools/open_login.py --seconds 1800
环境变量：
  LOGIN_URL   覆盖登录地址（会排到候选列表最前）
"""
import argparse
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import collect as C  # noqa: E402  （复用 PROFILE / DAREN / 登录判定）

# ⚠️ collect.py 在 import 时会把 sys.stdout 换成新的 TextIOWrapper。
#    这里**必须**用 reconfigure（不能再包一层 TextIOWrapper）——
#    再包一层会让旧 wrapper 被 GC 时关掉底层 buffer，
#    后续 print 直接 `ValueError: I/O operation on closed file`（踩过）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOGGED_IN_MARK = ("主推类目", "找达人", "按商品找达人")
LOGIN_URLS = tuple(u for u in (
    os.environ.get("LOGIN_URL", ""),
    "https://fxg.jinritemai.com/login/common?from=buyin",
    "https://buyin.jinritemai.com/login",
) if u)
LOGIN_PAGE_GOOD = ("验证码", "扫码", "二维码", "账号登录", "密码登录")
LOGIN_PAGE_BAD = ("404 Not Found", "not found", "nginx")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


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


def body_of(pg, tries=2):
    for _ in range(tries):
        try:
            return pg.evaluate("() => (document.body.innerText || '').slice(0, 4000)")
        except Exception:
            time.sleep(1.0)
    return ""


def open_login_page(ctx):
    """在**新标签页**里按候选列表挑一个真登录页打开，返回该页。"""
    lp = ctx.new_page()
    picked = ""
    for u in LOGIN_URLS:
        try:
            lp.goto(u, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            log("  打开 %s 失败：%s" % (u, str(e)[:80]))
            continue
        time.sleep(4)
        b = body_of(lp)
        bad = any(m in b for m in LOGIN_PAGE_BAD)
        good = any(m in b for m in LOGIN_PAGE_GOOD)
        log("  %s -> %s" % (u, "可用" if (good and not bad) else
                            ("404/错误页" if bad else "未见登录表单，继续试")))
        if good and not bad:
            picked = u
            break
    if picked:
        log("✅ 登录页已打开：%s" % picked)
    else:
        log("⚠️ 候选地址都不可用，请在地址栏手动打开登录页")
    try:
        lp.bring_to_front()
    except Exception:
        pass
    return lp, picked


def is_logged_in(ctx):
    """开一个临时标签页到达人广场，看有没有登录后标记；查完立刻关掉。"""
    tmp = None
    try:
        tmp = ctx.new_page()
        tmp.goto(C.DAREN, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(6)
        b = body_of(tmp, tries=3)
        hit = [m for m in LOGGED_IN_MARK if m in b]
        return bool(hit), ("/".join(hit) if hit else "")
    except Exception:
        return False, ""
    finally:
        try:
            if tmp and not tmp.is_closed():
                tmp.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int,
                    default=int(os.environ.get("WAIT_SEC", "3600")))
    ap.add_argument("--check-every", type=int, default=20)
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=C.PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        log("已打开自动化 Edge（profile: %s）" % C.PROFILE)
        lp, picked = open_login_page(ctx)
        log("=" * 66)
        log("请在**刚打开的这个 Edge 窗口**里登录精选联盟账号：")
        log("  · 扫码登录：用抖音 App 扫页面上的二维码")
        log("  · 或切到「手机号/验证码」「邮箱」方式登录")
        log("登录完成后，请**自己把这个 Edge 窗口关掉**（让 cookie 落盘），")
        log("本脚本会自动发现窗口关闭并结束。最长等待 %d 秒。" % a.seconds)
        log("=" * 66)

        t0 = time.time()
        last = ""
        while time.time() - t0 < a.seconds:
            time.sleep(a.check_every)
            pages = alive_pages(ctx)
            if not pages:
                log("检测到 Edge 窗口已被关闭 -> 结束（cookie 应已落盘）")
                return
            ok, why = is_logged_in(ctx)
            msg = "已登录" if ok else "尚未登录"
            if msg != last:
                log("%s%s" % (msg, ("（%s）" % why) if why else ""))
                last = msg
            if ok:
                log("=" * 66)
                log("✅ 已检测到登录成功。可以关掉窗口，然后继续跑采集了。")
                log("=" * 66)
                # 不主动关窗口：交给使用者关，保证 cookie 落盘
                last = "已登录"
        log("等待超时（%d 秒）-> 结束" % a.seconds)


if __name__ == "__main__":
    main()
