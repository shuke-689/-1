# -*- coding: utf-8 -*-
"""紧急撤销：把我误插入到用户记事本里的测试文字 Ctrl+Z 回退，并且绝不保存。"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win_io as w  # noqa: E402

TARGET = 4065176  # 被误写入的记事本窗口

if w.user32.IsWindow(TARGET):
    print("窗口仍存在，执行撤销...")
    w.set_foreground(TARGET)
    time.sleep(0.4)
    for i in range(3):
        w.send_keys(["CTRL", "Z"])
        time.sleep(0.35)
        print("  已发送 Ctrl+Z #%d" % (i + 1))
    time.sleep(0.5)
    img = w.screenshot_window(TARGET)
    out = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "..", "out", "undo-verify.png"))
    img.save(out)
    print("撤销后截图: %s" % out)
else:
    print("窗口已不存在，跳过")

print()
print("当前所有记事本窗口:")
for x in w.list_windows(""):
    if "notepad" in x["cls"].lower() or "记事本" in x["title"]:
        print("  HWND=%s vis=%s title=%r cls=%s" % (x["hwnd"], x["visible"], x["title"], x["cls"]))
