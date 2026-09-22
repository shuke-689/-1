# 临时检查：复现用户截图里的三种标签组合 + 统计真实 main_cate 分布
# 输出写到 out/_z_check.txt（避免与 collect.py 的 stdout 包装冲突）
import sys, os, json, collections
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_z_check.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

import collect as C
P("FILTER_PROFILE(默认) =", C.FILTER_PROFILE)
P("Z_MAIN =", C.Z_MAIN)
P("Z_SINGLE_CONTENT =", C.Z_SINGLE_CONTENT)
P("Z_CONTENT_BLACKLIST =", C.Z_CONTENT_BLACKLIST)
P("")
P("=== 截图三例在 z_verdict 下的判定 ===")
cases = [("百变松松", "美妆", "时尚"), ("韦佳", "美妆", "时尚"), ("文子", "个护家清", "其他")]
for nick, m1, m2 in cases:
    for mc, ct, lab in [([m1, m2], [], "两词条都算主推类目"),
                        ([m1], [m2], "第二个词条算内容类型")]:
        ok, hits, why = C.z_verdict(mc, ct)
        P("  %-6s %-22s main_cate=%-22s content=%-8s -> ok=%-5s hits=%d why=%s"
          % (nick, lab, str(mc), str(ct), ok, hits, why or "-"))
P("")
d = json.load(open(os.path.join(B, "out", "collect", "darens.json"), encoding="utf-8"))
P("darens.json 条数 =", len(d))
cnt = collections.Counter()
for r in d:
    cnt[tuple(sorted(r.get("main_cate") or []))] += 1
P("--- main_cate 组合分布 Top 25 ---")
for mc, n in cnt.most_common(25):
    P("  %-50s %d" % (str(list(mc)), n))
P("")
# 检查「其他」这种占位类目是否被当作「别的类目」而放行（Z4a 漏洞）
leak = []
for r in d:
    mc = r.get("main_cate") or []
    hits = [c for c in C.Z_MAIN if c in mc]
    others = [c for c in mc if c not in C.Z_MAIN]
    if len(hits) == 1 and others:
        leak.append((r.get("nickname"), mc, r.get("content_type") or []))
P("--- 单主词条 + 存在 others（走 Z4a 放行）的条目：%d 条 ---" % len(leak))
for nick, mc, ct in leak[:25]:
    P("  %-16s main_cate=%-40s content=%s" % (str(nick)[:16], str(mc), str(ct)))
out.close()
print("done")
