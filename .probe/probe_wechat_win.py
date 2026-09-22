# -*- coding: utf-8 -*-
"""诊断：B 阶段 OCR 读不到「添加朋友」窗口文字时，到底卡在哪一步。

排查顺序（对应不同的失败原因）：
  ① 屏幕级截图（BitBlt 桌面 DC）—— 失败/全黑 = **会话锁屏或没接显示器**；
  ② 窗口级截图（PrintWindow，不需要窗口在最前）—— 能出内容 ≠ 可用！见下面警告；
  ③ 两种都空 = 窗口真的没渲染（微信未登录/窗口是空壳）。

🔴🔴 重要（2026-09-22 21:13 翻车教训）：
  **① 全黑、② 却有内容 —— 这个组合意味着「锁屏冻帧」**：PrintWindow 返回的是最后缓存的
  那一帧，画面**不会随操作更新**。当时据此以为"修好了"，实际让 B 把 10 个达人全误判成
  not_found 并写进台账（10 张结果图 8 张 md5 完全相同）。**看了有字 ≠ 画面是活的。**
  ⇒ 正确处置：**解锁屏幕，别绕**。`wechat_add.py run` 已内置 `precheck_desktop()` 硬阻断 +
  `freeze_step()` 冻帧守卫。要判定冻帧，请看 `ls -lat out/wechat/steps/ | head` 的文件大小是否一致。

跑法：source tools/env.sh && "$PY" .probe/probe_wechat_win.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".probe"))

import win_io as W          # noqa: E402
import ocr as O             # noqa: E402


def log(m):
    print(m, flush=True)


wins = W.list_windows("添加朋友", visible_only=False)
log("匹配「添加朋友」的窗口 %d 个" % len(wins))
for w in wins:
    log("   %s" % (w,))
if not wins:
    log("!! 没有「添加朋友」窗口 -> 先在微信里打开它")
    sys.exit(1)

hwnd = wins[0]["hwnd"] if isinstance(wins[0], dict) else (
    wins[0][0] if isinstance(wins[0], (list, tuple)) else wins[0])
rect = W.window_rect(hwnd)
log("hwnd=%s rect=%s" % (hwnd, rect))

outdir = os.path.join(BASE, "out")
os.makedirs(outdir, exist_ok=True)

# ---- ① 屏幕级 ----
log("")
log("① 屏幕级截图（BitBlt 桌面）…")
try:
    im = W.screenshot_region(*rect)
    p1 = os.path.join(outdir, "_wx_screen_grab.png")
    im.save(p1)
    items = O.ocr(im) or []
    log("   成功：%s  像素均值=%.1f  OCR %d 段" % (p1, im.convert("L").resize((1, 1)).getpixel((0, 0)), len(items)))
    O.dump(items, "屏幕级")
except Exception as e:
    log("   !! 失败：%s" % e)
    log("   -> 结论：会话可能**已锁屏 / 无桌面可截**，B 的 read_result() 一定读不到结果")

# ---- ② 窗口级 ----
log("")
log("② 窗口级截图（PrintWindow PW_RENDERFULLCONTENT，不要求在最前）…")
try:
    im2, ok = W.print_window(hwnd, 2)
    p2 = os.path.join(outdir, "_wx_printwindow.png")
    im2.save(p2)
    items2 = O.ocr(im2) or []
    log("   ok=%s  %s  像素均值=%.1f  OCR %d 段" % (
        ok, p2, im2.convert("L").resize((1, 1)).getpixel((0, 0)), len(items2)))
    O.dump(items2, "窗口级")
    if items2:
        log("   -> 若 ① 也是黑屏：**极可能是锁屏冻帧**（画面不更新）→ 结论是「解锁屏幕」而不是「用 PrintWindow 绕」")
        log("   -> 若 ① 正常：窗口内容在，只是**被别的窗口盖住**；把它置前（或让 B 的置前生效）即可")
    else:
        log("   -> 结论：窗口自己也没渲染出文字")
except Exception as e:
    log("   !! 失败：%s" % e)
