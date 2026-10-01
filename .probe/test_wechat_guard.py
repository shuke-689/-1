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
print("multi_frame_frozen() 单测（2026-09-23 新增：2 帧交替绕过 freeze_step）：")

# 7) 复现 09-23 真实场景：10 个不同微信号，结果图只有 2 种指纹
mf = [None] * 11
for idx in range(1, 11):
    seen = {"A"} if idx in (1, 3, 4, 7, 8, 10) else {"A", "B"}
    mf[idx] = W.multi_frame_frozen(idx, seen)
check("2 帧交替 -> 第 5 个起拦住", mf[5], True)
check("2 帧交替 -> 前 4 个不拦", [mf[1], mf[2], mf[3], mf[4]], [False] * 4)

# 8) 单帧（全部相同）也拦
check("单一指纹 -> 拦住", W.multi_frame_frozen(5, {"A"}), True)

# 9) 正常轮次（每种不同）绝不误伤
check("10 种指纹 -> 不拦", W.multi_frame_frozen(10, {"m%d" % i for i in range(10)}), False)
check("3 种指纹 -> 不拦", W.multi_frame_frozen(10, {"A", "B", "C"}), False)
check("只跑到第 4 个 -> 不拦", W.multi_frame_frozen(4, {"A"}), False)

print()
print("搜索框定位 / 新状态 单测：")

# 10) norm_text：OCR 会丢下划线/点，比对前先归一化
check("norm_text 基本", W.norm_text("gaoyan6665"), "gaoyan6665")
check("norm_text 去符号", W.norm_text("wxid_9okb86cj3e9r12"), "wxid9okb86cj3e9r12")
check("norm_text 不同号不误判", W.norm_text("LYW00736") in W.norm_text("18"), False)

# 11) 搜索结果页里「搜不到」不能吃掉「账号状态异常」
check("ABNORMAL_KW 非空", bool(W.ABNORMAL_KW), True)
check("abnormal 计入已完成(跳过)",
      "abnormal" in W.DONE_STATUS, True)
check("abnormal 有中文标签", W.STATUS_LABEL.get("abnormal"), "账号状态异常(跳过)")
check("标题不会被当成搜索框", "添加朋友" in W.WeChat.BOX_LABELS, True)

# 12) 搜索框写入校验：OCR 误读不能把「其实写进去了」判成失败（2026-10-01 修）
#     —— 14:02 轮 10 个里 4 个被这条误判成 unknown，白占当天 30 个额度。
check("写入校验·放大镜读成Q+l读成I", W.id_similar("lmg1223221", "Q Img1223221"), True)
check("写入校验·j读成i", W.id_similar("xjj606060", "xij606060"), True)
check("写入校验·l/o读成I/0", W.id_similar("ll-7oo", "Q I1-700"), True)
check("写入校验·严格命中", W.id_similar("dan47277288", "dan47277288"), True)
check("写入校验·空框仍判失败", W.id_similar("lmg1223221", ""), False)
check("写入校验·别的号不误判", W.id_similar("lmg1223221", "xjj606060"), False)
check("写入校验·真乱码仍判失败", W.id_similar("nwx99999", "66666xMu"), False)

print()
if FAIL:
    print("!! 失败 %d 项：%s" % (len(FAIL), " / ".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % 33)
