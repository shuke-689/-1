# -*- coding: utf-8 -*-
"""测试 collect.py 的带货品牌判定（规则3：同一品牌占比 >= 50% 且严格过半 -> 跳过）。"""
import sys

sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\抖音")
import collect                     # collect 会把 sys.stdout 换成 wrapper

_keep = sys.stdout                 # 留引用，否则 wrapper 被 GC 会关掉底层 buffer
sys.stdout = sys.__stdout__

P = collect.SAME_BRAND_RATIO
print("\n=== 带货品牌判定单元测试（阈值 %.0f%%，且需严格过半） ===" % (P * 100))
cases = [
    (["明希精选", "明希个护严选", "明希优品优选"],                          True,  1.00, "3/3 明希"),
    (["明希精选", "明希个护严选", "明希优品优选", "谷本日记官方旗舰店"],       True,  0.75, "3/4 明希"),
    (["明希精选", "明希个护严选", "谷本日记官方旗舰店"],                     True,  0.67, "2/3 明希 (严格过半)"),
    (["明希精选", "明希个护严选", "谷本日记官方旗舰店", "钙尔奇官方旗舰店"],   False, 0.50, "2/4 打平 -> 不跳"),
    (["完美日记官方旗舰店", "完美日记专卖店", "花西子官方旗舰店",
      "毛戈平官方旗舰店"],                                                False, 0.50, "2/4 完美日记打平"),
    (["谷本日记官方旗舰店", "钙尔奇官方旗舰店"],                            False, 0.50, "2 件 2 品牌 -> 不跳(防误判)"),
    (["谷本日记官方旗舰店", "谷本日记官方海外旗舰店"],                       True,  1.00, "2 件同品牌 -> 跳"),
    (["花西子官方旗舰店"],                                                True,  1.00, "仅 1 件 -> 跳"),
    (["a1", "b1", "c1", "d1", "e1", "明希精选", "明希优品优选"],            False, 0.29, "7 件最大 2 -> 不跳"),
    (["明希精选", "明希优品优选", "明希严选", "明希专柜", "谷本日记", "钙尔奇"], True, 0.67, "4/6 明希 -> 跳"),
    ([],                                                                False, 0.00, "无数据"),
]
ok = 0
for shops, exp_skip, exp_ratio, desc in cases:
    skip, ratio, brand, total, cnt = collect.brand_verdict(shops)
    good = (skip == exp_skip) and abs(ratio - exp_ratio) < 0.01
    if good:
        ok += 1
    print("  %s %-26s skip=%-5s ratio=%.2f brand=%-8s %d/%d" % (
        "OK " if good else "FAIL", desc, skip, ratio, brand or "-", cnt, total))
print("  -> %d/%d 通过" % (ok, len(cases)))
