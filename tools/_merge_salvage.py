# 把 15 个已复核的回收候选并入 darens.json（按 uid 去重）
import sys, os, json, shutil, time
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
OUT = os.path.join(B, "out", "collect")
D = os.path.join(OUT, "darens.json")
line = lambda *a: print(*a, flush=True)

ready = json.load(open(os.path.join(B, "out", "_salvage_ready.json"), encoding="utf-8"))
add = [r["rec"] for r in ready]

bak = os.path.join(OUT, "darens.bak_before_add15_%s.json" % time.strftime("%H%M%S"))
shutil.copy2(D, bak)
line("已备份 darens.json -> %s" % os.path.basename(bak))

cur = json.load(open(D, encoding="utf-8"))
have_uid = {r.get("uid") for r in cur if r.get("uid")}
picked = [r for r in add if r.get("uid") not in have_uid]
line("现有 %d 条；待并入 %d 条（去重后 %d 条）" % (len(cur), len(add), len(picked)))

merged, seen = [], set()
for r in cur + picked:
    u = r.get("uid")
    if not u or u in seen:
        continue
    seen.add(u)
    merged.append(r)

import darens_io
darens_io.write_outputs(merged, OUT, "", log=line)
line("写回完成：darens.json = %d 条" % len(merged))
