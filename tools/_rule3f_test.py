# 单测：规则3f（单一店铺占比）——输出到 out/_rule3f_test.txt
import sys, os
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_rule3f_test.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

import collect as C

P("FILTER_PROFILE 默认 =", C.FILTER_PROFILE, "（应为 Z）")
P("SHOP_SHARE_RATIO =", C.SHOP_SHARE_RATIO)
P("")
cases = [
    (["A店"] * 10, "10/10 同一家店 -> 应跳过"),
    (["A店"] * 6 + ["B店"] * 4, "6/10=60% 严格过半 -> 应跳过"),
    (["A店"] * 5 + ["B店"] * 5, "5/10=50% 不算严格过半 -> 不跳过"),
    (["A店"] * 3 + ["B店"] * 2, "3/5=60% 严格过半 -> 应跳过"),
    (["A店", "B店"], "1/2=50% 各占一半 -> 不跳过"),
    (["A店"] * 2 + ["B店"] * 3, "A店 40% -> 不跳过"),
    ([], "无数据 -> 不跳过（由上层未判定逻辑兜）"),
]
allok = True
for shops, desc in cases:
    skip, ratio, name, total, n = C.shopshare_verdict(shops)
    P("  %-34s shops=%-28s -> skip=%-5s 占比=%.0f%% (%s %d/%d)"
      % (desc, str(shops)[:28], skip, ratio * 100, name or "-", n, total))
P("")
# 与 brand_verdict 口径一致性交叉验证
P("=== 与 brand_verdict 口径对齐检查（同为 50% 阈值 + 严格过半）===")
for shops in (["A店"] * 6 + ["B店"] * 4, ["A店"] * 5 + ["B店"] * 5):
    P("  shops=%s -> shopskip=%s brandskip=%s" % (
        shops, C.shopshare_verdict(shops)[0], C.brand_verdict(shops)[0]))
P("")
P("=== 新常量/函数就位检查 ===")
for nm in ("SHOP_SHARE_RATIO", "shopshare_verdict", "shopshare"):
    P("  %-18s %s" % (nm, hasattr(C, nm)))
out.close()
print("done")
