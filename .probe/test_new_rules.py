# -*- coding: utf-8 -*-
"""规则单测（2026-09-17 新增三条带货规则）：
  3b 禁忌商品关键词（含 充电宝 / 3C数码 等）
  3c 去重店铺家数 <= MIN_SHOP_CNT -> 跳过
  3d >= 90% 商品到手价 < 30 元 -> 跳过（价格以探针实测的单元格格式为准）

跑法：
  set PYTHONPATH=<proj>\\.probe\\libs
  python .probe/test_new_rules.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import collect as C  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 3b 禁忌商品关键词 ----------------
# 名称里带这些词 -> 跳过
KW_HIT = [
    "假发接发一片式",
    "院线专用面膜",
    "美甲贴片",
    "20000mAh充电宝大容量",
    "便携移动电源10000毫安",
    "3C数码配件收纳包",
    "数码高清摄像头",
    "Type-C数据线快充",
    "65W氮化镓充电器",
    "充电头多口快充",
    "蓝牙耳机降噪",
]
# 不能误伤（尤其 3CE 这类美妆品牌）
KW_MISS = [
    "3CE口红丝绒雾面",
    "3CE眼影盘",
    "美妆蛋粉扑",
    "补水面膜",
    "美妆仪",                                  # 含「美妆」不含「美甲」
    "精华水面霜套装",
]

# ---------------- 3d 到手价解析 ----------------
# (单元格原文, 期望到手价)
PRICE_CASES = [
    ("￥59.90", 59.9),
    ("￥29.90 ￥69.90", 29.9),          # 第一个数才是到手价
    ("￥1,299.00", 1299.0),
    ("¥35.00", 35.0),
    ("￥7.80", 7.8),
    ("", None),
    ("-", None),
    ("暂无", None),
    (None, None),
]

# ---------------- 3c 店铺家数 ----------------
SHOP_CASES = [
    # (店铺名列表, 期望跳过, 期望家数)
    (["嬉笑闫开护肤"], True, 1),               # 实测样本：15 件商品只来自 1 家店
    (["A店", "A店"], True, 1),
    (["A店", "B店"], True, 2),
    (["A店", "B店", "C店"], False, 3),
    ([], True, 0),
]

# ---------------- 3d 低价铺货判定 ----------------
# 构造 prows：price 用实测格式
def rows(prices):
    return [{"title": "t", "shop": "s", "price": p} for p in prices]


CHEAP_CASES = [
    # 15 件全 < 30 元 -> 跳过
    (rows(["￥%d.90" % p for p in [9, 12, 19, 25, 29, 9, 15, 21, 27, 8, 11, 13, 17, 23, 26]]),
     True, "cheap"),
    # 15 件里 14 件 < 30（93.3%）-> 跳过
    (rows(["￥%d.90" % p for p in [9, 12, 19, 25, 29, 9, 15, 21, 27, 8, 11, 13, 17, 23, 99]]),
     True, "cheap"),
    # 15 件里 13 件 < 30（86.7%）-> 不跳过
    (rows(["￥%d.90" % p for p in [9, 12, 19, 25, 29, 9, 15, 21, 27, 8, 11, 13, 99, 88, 77]]),
     False, ""),
    # 高价为主 -> 不跳过
    (rows(["￥%d.90" % p for p in [59, 69, 79, 99, 129, 199, 39, 45, 89, 35]]),
     False, ""),
    # 价格全解析不出来 -> 未判定 -> 跳过
    (rows(["-", "", "暂无"]), False, "fewprice"),
    # 15 件只有 10 件可解析（66.7% < 80%）-> 未判定 -> 跳过
    (rows(["￥9.90"] * 10 + ["-", "", "-", "暂无", "-"]), False, "fewprice"),
]


def main():
    bad = 0

    print("=" * 60)
    print("3b 禁忌商品关键词")
    for t in KW_HIT:
        got = C.product_exclude_hit([t])
        flag = "OK " if got else "!! "
        if not got:
            bad += 1
        print("  %s 应命中 -> 实际 %-10r  %s" % (flag, got, t))
    for t in KW_MISS:
        got = C.product_exclude_hit([t])
        flag = "OK " if not got else "!! "
        if got:
            bad += 1
        print("  %s 不应命中 -> 实际 %-10r  %s" % (flag, got, t))

    print("=" * 60)
    print("3d 到手价解析")
    for text, exp in PRICE_CASES:
        got = C.parse_price(text)
        ok = (got == exp)
        if not ok:
            bad += 1
        print("  %s %-20r -> %-10s (期望 %s)" % ("OK " if ok else "!! ", text, got, exp))

    print("=" * 60)
    print("3c 店铺家数（MIN_SHOP_CNT=%d）" % C.MIN_SHOP_CNT)
    for shops, exp_skip, exp_cnt in SHOP_CASES:
        skip, cnt, _ = C.shopcnt_verdict(shops)
        ok = (skip == exp_skip and cnt == exp_cnt)
        if not ok:
            bad += 1
        print("  %s %-34s -> skip=%-5s cnt=%d (期望 skip=%s cnt=%d)" % (
            "OK " if ok else "!! ", str(shops)[:34], skip, cnt, exp_skip, exp_cnt))

    print("=" * 60)
    print("3d 低价铺货（<%.0f元 占比 >= %.0f%%）" % (C.CHEAP_PRICE, C.CHEAP_RATIO * 100))
    for prows, exp_skip, exp_why in CHEAP_CASES:
        skip, ratio, n_ok, n_all, why = C.cheap_verdict(prows)
        ok = (skip == exp_skip and why == exp_why)
        if not ok:
            bad += 1
        print("  %s %d 件(可解析 %d) 占比 %.1f%% -> skip=%-5s why=%-9s (期望 skip=%s why=%s)" % (
            "OK " if ok else "!! ", n_all, n_ok, ratio * 100, skip, why, exp_skip, exp_why))

    print("=" * 60)
    if bad:
        print("失败 %d 项" % bad)
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
