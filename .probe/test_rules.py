# -*- coding: utf-8 -*-
"""规则单测：规则4（主推类目组合）+ 规则3b（带货禁忌商品名）+ 规则2b（结算额兜底）。

跑法：
  python .probe/test_rules.py
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

CATE_CASES = [
    # (main_cate,                期望通过, 期望原因)
    (["个护家清"],                       True,  ""),
    (["美妆"],                           True,  ""),
    (["个护家清", "美妆"],                True,  ""),
    (["美妆", "个护家清"],                True,  ""),
    (["个护家清", "服饰内衣"],            True,  ""),
    (["个护家清", "母婴宠物"],            True,  ""),
    (["个护家清", "运动户外"],            True,  ""),
    (["个护家清", "母婴宠物", "食品饮料"], True,  ""),   # 命中2个 -> 第三个不限
    (["个护家清", "美妆", "食品饮料"],     True,  ""),   # 命中2个 -> 第三个不限
    (["个护家清", "美妆", "服饰内衣", "运动户外"], True, ""),
    (["个护家清", "食品饮料"],            False, "catecombo"),
    (["美妆", "食品饮料"],                False, "catecombo"),
    (["个护家清", "智能家居"],            False, "catecombo"),
    (["个护家清", "宠物"],                False, "catecombo"),
    (["服饰内衣"],                       False, "nocate"),
    (["服饰内衣", "母婴宠物"],            False, "nocate"),   # 没有个护家清/美妆
    (["食品饮料"],                       False, "nocate"),
    ([],                                False, "nocate"),
    (None,                              False, "nocate"),
]

PRODUCT_CASES = [
    # (商品名列表, 期望命中词)
    (["蒂芙青蘭鲟鱼子酱抗皱紧致精华水[120ml*3]正装试用"], ""),
    (["2026年新款夏季POLO洋气短袖上衣坑条针织衫"], ""),
    (["【买大送小】LUCK PLUS加倍幸运持妆粉底液持久服帖控油遮瑕哑光@"], ""),
    (["女士时尚假发全头套自然逼真"], "假发"),
    (["院线级水光修护精华液"], "院线"),
    (["网红穿戴甲美甲贴片"], "美甲"),
    (["洗发水", "美甲胶"], "美甲"),
    ([], ""),
    (None, ""),
]

# 规则2b：本地结算额兜底（live_low, live_high, 期望通过）
# 默认区间 = 1w-10w = 10000~100000（由 SALE_OPTION 反推）
# 起因：平台侧「直播结算总额」筛选漏出约 10%，0-0 的会污染飞书登记表
SETTLE_CASES = [
    (10000, 25000, True),        # 区间内
    (10000, 100000, True),       # 边界：下界等值、上界等值 -> 放行
    (25000, 50000, True),        # 区间内
    (0, 0, False),               # ← 就是它：平台返回 0-0，必须拦掉
    (5000, 10000, False),        # 下界低于 1w
    (0, 10000, False),           # 下界 0
    (50000, 200000, False),      # 上界超 10w
    (200000, 500000, False),     # 整段超 10w
    (None, None, False),         # 取不到数值 -> 未判定 -> 剔除
    (None, 25000, False),        # 半个数值 -> 剔除
    ("", "", False),             # 空串 -> 剔除
    ("10000", "25000", True),    # 字符串数字 -> 按数字比
]


def main():
    bad = 0
    for mc, want_ok, want_why in CATE_CASES:
        ok, hits, why = C.cate_verdict(mc)
        good = (ok == want_ok and why == want_why)
        if not good:
            bad += 1
        print("%s  cate_verdict(%-42s) -> ok=%-5s hits=%-28s why=%s" % (
            "PASS" if good else "FAIL", str(mc), ok, str(hits), why or "-"))
    print("-" * 78)
    for titles, want in PRODUCT_CASES:
        got = C.product_exclude_hit(titles)
        good = (got == want)
        if not good:
            bad += 1
        print("%s  product_exclude_hit(%-46s) -> %r" % (
            "PASS" if good else "FAIL", str(titles)[:44], got))
    print("-" * 78)
    for lo, hi, want_ok in SETTLE_CASES:
        ok, note = C.settle_ok(lo, hi)
        good = (ok == want_ok)
        if not good:
            bad += 1
        print("%s  settle_ok(%-8s, %-8s) -> ok=%-5s note=%s   [区间 %s-%s]" % (
            "PASS" if good else "FAIL", lo, hi, ok, note,
            C.SETTLE_MIN, C.SETTLE_MAX))
    print("-" * 78)
    total = len(CATE_CASES) + len(PRODUCT_CASES) + len(SETTLE_CASES)
    print("失败 %d 项" % bad if bad else "全部通过（%d 组用例）" % total)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
