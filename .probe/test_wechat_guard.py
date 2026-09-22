# -*- coding: utf-8 -*-
"""B 阶段「冻结帧守卫」单测。

背景（2026-09-22 21:13 实测翻车）：会话锁屏时桌面截图全黑，当时加的
「全黑就自动改用 PrintWindow」兜底，结果 PrintWindow 返回**冻结帧** ——
该轮 10 张搜索截图 **8 张逐像素完全相同**（md5 一致），10 个达人全被误判
not_found 并写进台账（含 6 个本该能搜到的微信号）。

现在两道防线：
  1. `precheck_desktop()`：桌面截图全黑 ⇒ 直接不跑（锁屏/息屏）。
  2. `freeze_step()`：连续 3 张结果图逐像素相同 ⇒ 判定冻结，本轮作废不写台账。

本测试覆盖 2 的纯函数逻辑（1 依赖真实桌面，只能线上验）。

跑法：
  source tools/env.sh && "$PY" .probe/test_wechat_guard.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))

# ⚠️ wechat_add 在 import 时会把 sys.stdout 换成 TextIOWrapper（它自己的模块级副作用），
#    所以**不要**在 import 后再去"恢复" sys.stdout —— 恢复会让 wrapper 被 GC 回收，
#    连带关闭底层 buffer（经典的 I/O operation on closed file）。这里直接在包装后的
#    stdout 上打印即可。
import wechat_add as W  # noqa: E402

FAIL = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAIL.append(name)
    print("  %s %-46s got=%s want=%s" % ("OK " if ok else "FAIL", name, got, want))


def run_seq(md5s):
    """跑一串 md5，返回 (结果 streak 列表, 首次冻结的下标或 None)。"""
    streak, last, frozen_at = 0, "", None
    out = []
    for i, m in enumerate(md5s):
        streak, fr = W.freeze_step(m, last, streak)
        if m:
            last = m
        out.append(streak)
        if fr and frozen_at is None:
            frozen_at = i
    return out, frozen_at


print("freeze_step() 单测：")

# 1) 三张完全相同 -> 第 3 张（下标 2）判定冻结
st, at = run_seq(["A", "A", "A"])
check("连续 3 张相同 -> streak", st, [0, 1, 2])
check("连续 3 张相同 -> 冻结于第 3 张", at, 2)

# 2) 只有两张相同 -> 不冻结
st, at = run_seq(["A", "A"])
check("仅 2 张相同 -> 不冻结", at, None)

# 3) 交错变化 -> 永不冻结
st, at = run_seq(["A", "B", "C", "D"])
check("全部不同 -> streak 恒 0", st, [0, 0, 0, 0])
check("全部不同 -> 不冻结", at, None)

# 4) 相同被打破后重新计数
st, at = run_seq(["A", "A", "B", "B", "B"])
check("打断后重新计数(1)", st, [0, 1, 0, 1, 2])
check("打断后重新触发(2)", at, 4)

# 5) 空 md5（截图取像素失败）自己不进判定，但保留上一次的 md5，
#    所以"链条"并未被打断 —— 后续 A,A 会接着前一次 A 继续累加。
st, at = run_seq(["A", "A", "", "A", "A"])
check("空 md5 也把 streak 归零", st, [0, 1, 0, 1, 2])
check("空 md5 后续仍能触发冻结", at, 4)

# 5b) 空 md5 且前后都是新值 -> 不会被当作相同
st, at = run_seq(["A", "", "B"])
check("空 md5 不制造假冻结", at, None)

# 6) 复现 09-22 真实场景：8 张同 md5
st, at = run_seq(["FROZEN"] * 8)
check("复现冻结帧场景 -> 第 3 张就拦住", at, 2)

print()
if FAIL:
    print("!! 失败 %d 项：%s" % (len(FAIL), " / ".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % 11)
