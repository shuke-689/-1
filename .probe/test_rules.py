# -*- coding: utf-8 -*-
"""规则单测：规则4（主推类目）+ 规则3b（带货禁忌商品名）+ 规则2b（结算额兜底）
+ 规则2d（粉丝量兜底）+ settle_pair 取值链。

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
    # 2026-09-22 用户口径：规则4 只保留「主推类目必须命中 个护家清/美妆 其一」，
    # 分支Z 与 CATE_TARGETS/CATE_EXCLUDE_PARTNER 的 "catecombo" 判定**全部删除**。
    (["个护家清"],                       True,  ""),
    (["美妆"],                           True,  ""),
    (["个护家清", "美妆"],                True,  ""),
    (["美妆", "个护家清"],                True,  ""),
    (["个护家清", "服饰内衣"],            True,  ""),
    (["个护家清", "母婴宠物"],            True,  ""),
    (["个护家清", "运动户外"],            True,  ""),
    (["个护家清", "母婴宠物", "食品饮料"], True,  ""),
    (["个护家清", "美妆", "食品饮料"],     True,  ""),
    (["个护家清", "美妆", "服饰内衣", "运动户外"], True, ""),
    # ↓ 这 4 例以前判 "catecombo"（不合格），简化后**一律合格**（第三条及以后不再限制）
    (["个护家清", "食品饮料"],            True,  ""),
    (["美妆", "食品饮料"],                True,  ""),
    (["个护家清", "智能家居"],            True,  ""),
    (["个护家清", "宠物"],                True,  ""),
    # ↓ 没命中个护家清/美妆 的一律 nocate
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

# 规则2d：本地兜底过滤「粉丝量 = 10w以下」（2026-09-22 新增）
# 起因：① 平台把「粉丝量」这个筛选项**改名成了「粉丝指数」**（选项一字未变）；
#      ② 本地过滤此前**完全没有**粉丝量这一关（bad_fans() 只是抽样统计、不拦数据），
#         平台侧一旦没生效就会收进大号。
# 口径：fans > FANS_MAX(默认 100000) 剔除；取不到数值 = 未判定 = 剔除。
FANS_CASES = [
    (99999, True),        # 区间内
    (100000, True),       # 边界：等值 -> 放行（与 settle_ok 的闭区间口径一致）
    (100001, False),      # 刚超一点
    (1500000, False),     # 百万级大号
    (25000, True),
    (0, True),            # 0 粉也算 <= 上限
    (None, False),        # 取不到数值 -> 未判定 -> 剔除
    ("abc", False),       # 非数字
    ("25000", True),      # 字符串数字
]

# rules 2b 取区间用的 settle_pair(rec) —— 2026-09-22 新增：
#   复核/回收/救急三个脚本都靠它从「名单记录」里取 (low, high)。
#   归档里的存档形态不统一（341 条里 251 条是扁平 live_low/high、64 条只有
#   settle_live={low,high}、26 条两者都没有），不兼容就会把 64 条误判成「无数据」。
SETTLE_PAIR_CASES = [
    # (记录, 期望 (low, high))
    ({"live_low": 10000, "live_high": 25000}, (10000, 25000)),          # 扁平字段优先
    ({"settle_live": {"low": 10000, "high": 25000}}, (10000, 25000)),   # 回退 settle_live
    ({"live_low": None, "live_high": None,
      "settle_live": {"low": 25000, "high": 50000}}, (25000, 50000)),   # 扁平是 None -> 回退
    ({"live_low": 10000, "live_high": None}, (10000, None)),            # 半个扁平 -> 原样传出
    ({"settle_live": {"low": None, "high": None}}, (None, None)),
    ({}, (None, None)),                                                 # 09-15 那批（只有 video_*）
]

# settle_pair 的取值还要能直接喂给 settle_ok（端到端：复核脚本的判定链）
SETTLE_PAIR_FLOW = [
    ({"settle_live": {"low": 25000, "high": 50000}}, True),    # 只有 settle_live，且合规
    ({"settle_live": {"low": 0, "high": 0}}, False),           # 只有 settle_live，0-0 要拦
    ({"live_low": 5000, "live_high": 10000}, False),           # 扁平，越界
    ({}, False),                                               # 两者都没有 -> 未判定 -> 剔除
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
    for fans, want_ok in FANS_CASES:
        ok, note = C.fans_ok(fans)
        good = (ok == want_ok)
        if not good:
            bad += 1
        print("%s  fans_ok(%-8s) -> ok=%-5s note=%s   [上限 %s]" % (
            "PASS" if good else "FAIL", fans, ok, note, C.FANS_MAX))
    print("-" * 78)
    for rec, want in SETTLE_PAIR_CASES:
        got = C.settle_pair(rec)
        good = (got == want)
        if not good:
            bad += 1
        print("%s  settle_pair(%-52s) -> %s" % (
            "PASS" if good else "FAIL", str(rec)[:50], got))
    print("-" * 78)
    for rec, want_ok in SETTLE_PAIR_FLOW:
        lo, hi = C.settle_pair(rec)
        ok, note = C.settle_ok(lo, hi)
        good = (ok == want_ok)
        if not good:
            bad += 1
        print("%s  settle_pair -> settle_ok(%-40s) -> ok=%-5s note=%s" % (
            "PASS" if good else "FAIL", str(rec)[:38], ok, note))
    print("-" * 78)
    total = (len(CATE_CASES) + len(PRODUCT_CASES) + len(SETTLE_CASES)
             + len(FANS_CASES) + len(SETTLE_PAIR_CASES) + len(SETTLE_PAIR_FLOW))
    print("失败 %d 项" % bad if bad else "全部通过（%d 组用例）" % total)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
