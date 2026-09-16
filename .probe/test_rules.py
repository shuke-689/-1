# -*- coding: utf-8 -*-
"""规则单测：规则4（主推类目组合）+ 规则3b（带货禁忌商品名）。

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
    print("失败 %d 项" % bad if bad else "全部通过（%d 组用例）"
          % (len(CATE_CASES) + len(PRODUCT_CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
