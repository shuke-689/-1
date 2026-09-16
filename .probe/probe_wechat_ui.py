# -*- coding: utf-8 -*-
"""微信 UI 标定：截图 + OCR，输出「添加朋友」窗口里每段文字的位置。
用 PrintWindow（不抢焦点）与屏幕 BitBlt 两种方式各抓一张，对比哪种能抓到内容。
"""
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
import ocr  # noqa: E402


def brightness(img):
    from PIL import ImageStat
    st = ImageStat.Stat(img.convert("L"))
    return round(st.mean[0], 1)


def main():
    print("=" * 74)
    wins = w.list_windows()
    targets = []
    for it in wins:
        t = (it["title"] or "")
        if t in ("微信", "WeChat") or t.startswith("添加") or t.startswith("WeChat"):
            if it["visible"]:
                targets.append(it)
                print("  hwnd=%-10d title=%-12r rect=%s" % (it["hwnd"], t, w.window_rect(it["hwnd"])))

    for it in targets:
        hwnd, title = it["hwnd"], it["title"]
        x, y, ww, hh = w.window_rect(hwnd)
        print()
        print("=" * 74)
        print("窗口 %r hwnd=%d rect=(%d,%d,%d,%d)" % (title, hwnd, x, y, ww, hh))

        # (1) PrintWindow
        try:
            img_pw, ok = w.print_window(hwnd, 2)
            f1 = os.path.join(OUT, "probe_pw_%s.png" % title[:6])
            img_pw.save(f1)
            print("  PrintWindow ok=%s 亮度=%s -> %s" % (ok, brightness(img_pw), f1))
        except Exception as e:
            print("  PrintWindow 失败: %s" % str(e)[:100])
            img_pw = None

        # (2) 屏幕 BitBlt
        try:
            img_sc = w.screenshot_region(x, y, ww, hh)
            f2 = os.path.join(OUT, "probe_sc_%s.png" % title[:6])
            img_sc.save(f2)
            print("  屏幕 BitBlt 亮度=%s -> %s" % (brightness(img_sc), f2))
        except Exception as e:
            print("  屏幕 BitBlt 失败: %s" % str(e)[:100])
            img_sc = None

        # 选信息量大的那张做 OCR
        best, tag = None, ""
        for im, nm in ((img_pw, "PrintWindow"), (img_sc, "屏幕")):
            if im is None:
                continue
            if best is None or brightness(im) > brightness(best):
                best, tag = im, nm
        if best is None:
            print("  无可用截图")
            continue
        print("  用【%s】做 OCR" % tag)
        try:
            items = ocr.ocr(best)
            print(ocr.dump(items, title))
        except Exception as e:
            print("  OCR 失败: %s" % str(e)[:140])


if __name__ == "__main__":
    main()
