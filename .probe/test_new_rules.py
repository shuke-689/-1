# -*- coding: utf-8 -*-
"""规则单测（2026-09-17 新增带货规则 + 昵称排除词）：
  3b 禁忌商品关键词（含 充电宝 / 3C数码 等）
  3c 去重店铺家数 <= MIN_SHOP_CNT -> 跳过
  3d >= 90% 商品到手价 < 30 元 -> 跳过（价格以探针实测的单元格格式为准）
  3e 商品名/店铺名含「养发」且占比 > 50% -> 跳过
  规则7 昵称排除词（国际/香港/假发/…/睫毛/香水/源头）
  规则7c 纯数字昵称（如 86567278365）-> 跳过

跑法：
  set PYTHONPATH=<proj>\\.probe\\libs
  python .probe/test_new_rules.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import collect as C        # noqa: E402
import nick_rules as NR    # noqa: E402

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

# ---------------- 3e 养发占比（商品名 或 店铺名 含「养发」，占比 > 50%） ----------------
def yrows(titles=None, shops=None, n=None):
    """构造 prows；titles/shops 给几个就有几行（不足 n 的用中性值补齐）。"""
    titles = titles or []
    shops = shops or []
    n = n if n is not None else max(len(titles), len(shops))
    out = []
    for i in range(n):
        out.append({"title": titles[i] if i < len(titles) else "普通洗发水",
                    "shop": shops[i] if i < len(shops) else "某某日化店",
                    "price": "￥59.90"})
    return out


YANGFA_CASES = [
    # 15 件里 8 件商品名含「养发」(53.3% > 50%) -> 跳过
    (yrows(titles=["养发精华"] * 8, n=15), True, 8, 15),
    # 15 件里 7 件含「养发」(46.7% <= 50%) -> 不跳过
    (yrows(titles=["养发精华"] * 7, n=15), False, 7, 15),
    # 16 件里 8 件 (恰好 50.0%，**不**算「超过」) -> 不跳过
    (yrows(titles=["养发精华"] * 8, n=16), False, 8, 16),
    # 商品名都没提，但**店铺名**含「养发」8/15 -> 跳过（用户明确要求算上店铺）
    (yrows(shops=["XX养发馆"] * 8, n=15), True, 8, 15),
    # 商品 3 件 + 店铺 6 件，合计 9/15 = 60% -> 跳过（两条路径**并集**计数）
    (yrows(titles=["养发液"] * 3 + [""] * 6,
           shops=[""] * 3 + ["养发世家"] * 6, n=15), True, 9, 15),
    # 全是无关商品 -> 不跳过
    (yrows(titles=["洗发水", "护发素", "沐浴露"], n=3), False, 0, 3),
    # 没有商品行 -> 不跳过（分母为 0，不能判成命中）
    ([], False, 0, 0),
    # 「养发」出现在店铺名但只有 5/15 (33%) -> 不跳过
    (yrows(shops=["养发馆"] * 5, n=15), False, 5, 15),
]

# ---------------- 规则7c 纯数字昵称 ----------------
DIGIT_HIT = ["86567278365", "1787097519", "920302", "0012345"]
DIGIT_MISS = ["一米六的安安", "盈妹", "小美123", "3CE口红", "小宇的零食铺2",
              "123", "abc12345"]      # 长度不足 4 / 含字母 -> 都不算「纯数字」


def main():
    bad = 0

    print("=" * 60)
    print("规则7 昵称排除词（2026-09-17 追加 10 个 + 再追加 3 个）")
    NICK_HIT = [
        "香港美妆代购", "香港🇭🇰萬寧上水店", "工厂直销护肤", "找工作的小张",
        "智慧服务小店", "假发专卖店", "美甲diy工作室", "红酒好物分享",
        "染发剂优选", "男士护肤严选", "妇炎洁官方",
        # 2026-09-17 第二批追加：睫毛 / 香水 / 源头
        "睫毛增长液厂家", "香水代购小铺", "源头工厂直供护肤", "源头好货严选",
        # 原有词抽查
        "小含美妆供应链", "妃妃国际美妆护肤", "慧慧养发日记",
    ]
    NICK_MISS = [
        "一米六的安安", "盈妹", "瑜妈好物严选", "汕头谷饶珊姐富之雅",
        "居家水光～飒飒", "小晨子的日常生活",
        # 反向抽查：不能因为加了「睫毛/香水/源头」就误伤这些正常名字
        #   （注意「源头」是有意放宽的词：含「源头」二字一律排除，
        #    哪怕名字叫「源头活水」这种无辜号 —— 用户明确要求，已接受误伤）
        "小鹿的日常好物", "阿may的美妆日记", "安琪拉好物分享",
    ]
    for t in NICK_HIT:
        got = C.nick_exclude_hit(t)
        ok = bool(got)
        if not ok:
            bad += 1
        print("  %s 应排除 -> 实际 %-16r  %s" % ("OK " if ok else "!! ", got, t))
    for t in NICK_MISS:
        got = C.nick_exclude_hit(t)
        ok = not got
        if not ok:
            bad += 1
        print("  %s 应保留 -> 实际 %-16r  %s" % ("OK " if ok else "!! ", got, t))

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
    print("3e 养发占比（商品名 或 店铺名 含 %s，占比 > %.0f%%）" % (
        "/".join(C.YANGFA_KW), C.YANGFA_RATIO * 100))
    for prows, exp_skip, exp_hits, exp_all in YANGFA_CASES:
        skip, ratio, hits, n_all, sample = C.yangfa_verdict(prows)
        ok = (skip == exp_skip and hits == exp_hits and n_all == exp_all)
        if not ok:
            bad += 1
        print("  %s 命中 %d/%d (%.1f%%) -> skip=%-5s (期望 skip=%s 命中=%d/%d) %s" % (
            "OK " if ok else "!! ", hits, n_all, ratio * 100, skip,
            exp_skip, exp_hits, exp_all, ("例:" + sample) if sample else ""))

    print("=" * 60)
    print("规则7c 纯数字昵称（DIGIT_NICK_MIN=%d）" % NR.DIGIT_NICK_MIN)
    for t in DIGIT_HIT:
        got = C.nick_exclude_hit(t)
        ok = got == "纯数字"
        if not ok:
            bad += 1
        print("  %s 应排除 -> 实际 %-12r %s" % ("OK " if ok else "!! ", got, t))
    for t in DIGIT_MISS:
        got = C.nick_exclude_hit(t)
        ok = got is None
        if not ok:
            bad += 1
        print("  %s 应保留 -> 实际 %-12r %s" % ("OK " if ok else "!! ", got, t))

    print("=" * 60)
    if bad:
        print("失败 %d 项" % bad)
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
