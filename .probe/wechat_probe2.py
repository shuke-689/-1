# -*- coding: utf-8 -*-
"""只读侦察：列出微信相关窗口并截图，供后续定位坐标。不移动鼠标、不点击。"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".probe"))
OUT = os.path.join(BASE, "out", "wechat")
os.makedirs(OUT, exist_ok=True)

import win_io as w  # noqa: E402


def main():
    print("=" * 74)
    print("A. 所有可见顶层窗口（含 wechat/微信/WeChat 关键字）")
    wins = w.list_windows(visible_only=True)
    for it in wins:
        t = it["title"] or ""
        c = it["cls"] or ""
        if any(k in t for k in ("微信", "WeChat", "添加", "Weixin")) or \
           any(k in c for k in ("WeChat", "Weixin", "MMUI", "Qt")):
            print("  hwnd=%-10d pid=%-7d cls=%-26s title=%r  rect=%s" % (
                it["hwnd"], it["pid"], c[:26], t[:40], w.window_rect(it["hwnd"])))

    print()
    print("B. 全部窗口总数 %d，按 pid 归组找微信进程" % len(wins))
    from collections import defaultdict
    g = defaultdict(list)
    for it in wins:
        g[it["pid"]].append(it)
    for pid, items in g.items():
        titles = " / ".join((i["title"] or "")[:18] for i in items[:4])
        cls = items[0]["cls"] or ""
        if any(k in cls for k in ("WeChat", "Weixin", "MMUI", "Qt")) or \
           any(k in titles for k in ("微信", "WeChat")):
            print("  pid=%-7d 窗口数=%-3d cls=%-24s | %s" % (pid, len(items), cls[:24], titles))

    print()
    print("C. 微信类窗口全量（含隐藏），用于确认主窗口/子窗口")
    allw = w.list_windows()
    for it in allw:
        t = it["title"] or ""
        c = it["cls"] or ""
        if t in ("微信", "WeChat") or t.startswith("添加") or "WeChat" in c or "Weixin" in c:
            print("  hwnd=%-10d vis=%-5s cls=%-26s title=%-22r rect=%s" % (
                it["hwnd"], it["visible"], c[:26], t[:22], w.window_rect(it["hwnd"])))

    print()
    print("D. 截图各微信窗口")
    for it in allw:
        t = (it["title"] or "")
        if not it["visible"]:
            continue
        if t in ("微信", "WeChat") or t.startswith("添加") or t.startswith("WeChat"):
            try:
                img = w.screenshot_window(it["hwnd"])
                fn = os.path.join(OUT, "win_%s_%d.png" % (t[:6].replace(" ", "_"), it["hwnd"]))
                img.save(fn)
                print("  %s -> %s  size=%s" % (t[:14], fn, img.size))
            except Exception as e:
                print("  截图失败 %s: %s" % (t[:14], str(e)[:80]))

    print()
    print("E. 桌面整屏截图（用于核对微信实际位置）")
    try:
        img = w.screenshot_desktop()
        fn = os.path.join(OUT, "desktop.png")
        img.save(fn)
        print("  %s size=%s" % (fn, img.size))
    except Exception as e:
        print("  失败: %s" % str(e)[:80])

    print()
    print("F. 剪贴板当前内容: %r" % (w.get_clipboard(),))


if __name__ == "__main__":
    main()
