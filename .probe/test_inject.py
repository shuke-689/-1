# -*- coding: utf-8 -*-
"""无干扰可行性测试：进程能否脱离父 shell 存活 + 能否向桌面程序注入键鼠。
用记事本作靶子，不碰用户的 Edge / 微信。
"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win_io as w  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
os.makedirs(OUT, exist_ok=True)

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

print("=" * 70)
print("测试 1：分离进程能否独立存活")
print("=" * 70)
proc = subprocess.Popen(["notepad.exe"], creationflags=DETACHED, close_fds=True)
print("已启动 notepad PID=%s（分离模式）" % proc.pid)
time.sleep(2.5)

time.sleep(0.5)
hwnd = None
for _ in range(20):
    cands = [x for x in w.list_windows("记事本") + w.list_windows("Notepad") if x["visible"]]
    if cands:
        hwnd = cands[0]["hwnd"]
        break
    time.sleep(0.5)

if not hwnd:
    print("✗ 未找到记事本窗口")
    sys.exit(1)

print("找到记事本窗口 HWND=%s title=%r" % (hwnd, w.list_windows("记事本")[0]["title"] if w.list_windows("记事本") else "?"))

print()
print("=" * 70)
print("测试 2：规范化窗口位置")
print("=" * 70)
r = w.move_window(hwnd, 100, 100, 900, 600)
print("移动后窗口位置: %s" % (r,))

print()
print("=" * 70)
print("测试 3：置前 + 注入键鼠（点击编辑区后粘贴中文）")
print("=" * 70)
ok = w.set_foreground(hwnd)
print("置前结果: %s, 当前前台窗口: %s" % (ok, w.user32.GetForegroundWindow()))
time.sleep(0.4)

w.click_in_window(hwnd, 400, 300)
time.sleep(0.3)

TEST_TEXT = "自动化注入测试 OK 2026-09-15 中文正常"
w.paste_text(TEST_TEXT)
time.sleep(0.5)

print("剪贴板回读: %r" % w.get_clipboard())
print("期望文本  : %r" % TEST_TEXT)

print()
print("=" * 70)
print("测试 4：截图校验（能否读到窗口画面）")
print("=" * 70)
img = w.screenshot_window(hwnd)
path = os.path.abspath(os.path.join(OUT, "inject-test.png"))
img.save(path)
print("截图已保存: %s  尺寸=%s" % (path, img.size))

print()
print("=" * 70)
print("测试 5：残留清理前的状态确认")
print("=" * 70)
print("记事本仍在运行: %s" % bool(w.user32.IsWindow(hwnd)))
