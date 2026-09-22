# 检查待回收候选是否具备店铺明细（能否套用新规则3f）
import sys, os, json
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_salvage_fields.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

pass_rows = json.load(open(os.path.join(B, "out", "_salvage_pass.json"), encoding="utf-8"))
# 找到来源文件里的原始记录
import glob
raw = []
for f in set(r["file"] for r in pass_rows):
    d = json.load(open(os.path.join(B, "out", "collect", "archive", f), encoding="utf-8")) \
        if os.path.exists(os.path.join(B, "out", "collect", "archive", f)) else \
        json.load(open(os.path.join(B, "out", "collect", f), encoding="utf-8"))
    raw += d if isinstance(d, list) else []
by_uid = {r.get("uid"): r for r in raw if isinstance(r, dict)}

P("待回收候选 = %d 个" % len(pass_rows))
if raw:
    P("样例记录的字段清单 =")
    for k in sorted(raw[0].keys()):
        P("   %s = %r" % (k, str(raw[0].get(k))[:60]))
P("")
P("=== 逐个检查是否有店铺明细 ===")
ok, lack = [], []
for r in pass_rows:
    rec = by_uid.get(r["uid"], {})
    shops = rec.get("shops") or []
    rows = rec.get("shop_rows") or 0
    (ok if shops else lack).append(r)
    P("  %-18s shops=%d shop_rows=%s shop_cnt=%s top_shop=%s"
      % (str(r["nickname"])[:18], len(shops), rows,
         rec.get("shop_cnt"), rec.get("top_shop")))
P("")
P("有店铺明细 = %d 个；无店铺明细 = %d 个" % (len(ok), len(lack)))
P("-> 无明细的按项目铁律「绝不未判定就查微信」不可直接添加")
out.close()
print("done")
