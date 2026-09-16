# -*- coding: utf-8 -*-
"""从 filter.json 提取需要的筛选项，并解析 search_feed_author 的响应结构。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "out", "stage5")

lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


flt = json.load(open(os.path.join(D, "filter.json"), encoding="utf-8"))
data = flt["data"]

P("=" * 80)
P("filter.data 顶层键: %s" % list(data.keys()))
P("=" * 80)

# ---- 1. 所有顶层筛选组 ----
for h in data.get("headers", []):
    P("")
    P("### 筛选组: %s  (共 %d 个选项)" % (h.get("name"), len(h.get("header", []))))
    for o in h.get("header", [])[:30]:
        kids = o.get("children")
        P("   - %-14s field=%-42s value=%-14s %s" % (
            o.get("name"), o.get("field_name"), o.get("value"),
            ("children=%d" % len(kids)) if kids else ""))

# ---- 2. 定位目标类目 ----
P("")
P("=" * 80)
P("目标类目定位")
P("=" * 80)
for h in data.get("headers", []):
    for o in h.get("header", []):
        if o.get("name") in ("个护家清", "美妆"):
            P("")
            P("★ %s -> field_name=%s value=%s" % (o.get("name"), o.get("field_name"), o.get("value")))
            for c1 in o.get("children", [])[:60]:
                P("     二级: %-24s field=%s value=%s" % (
                    c1.get("name"), c1.get("field_name"), c1.get("value")))

# ---- 3. 其他筛选组的完整选项（非类目树） ----
P("")
P("=" * 80)
P("其他筛选组明细（结算/粉丝/画像/联系方式 等）")
P("=" * 80)
SKIP = {"主推类目"}
for h in data.get("headers", []):
    if h.get("name") in SKIP:
        continue
    P("")
    P("### %s" % h.get("name"))
    for o in h.get("header", [])[:60]:
        kids = o.get("children") or []
        P("   - %-20s field=%-40s value=%-16s type=%s" % (
            o.get("name"), o.get("field_name"), o.get("value"), o.get("type")))
        for c in kids[:14]:
            P("        └ %-22s field=%-40s value=%s" % (
                c.get("name"), c.get("field_name"), c.get("value")))

# ---- 4. 其它顶层字段（radio / 排序 等） ----
for k in data.keys():
    if k == "headers":
        continue
    v = data[k]
    P("")
    P("### 顶层字段 %s: %s" % (k, json.dumps(v, ensure_ascii=False)[:1500]))

# ---- 5. search_feed_author 响应结构 ----
sf = os.path.join(D, "search_feed_author.json")
P("")
P("=" * 80)
P("search_feed_author 响应结构")
P("=" * 80)
if os.path.exists(sf):
    s = json.load(open(sf, encoding="utf-8"))
    P(json.dumps(s, ensure_ascii=False, indent=1)[:9000])
else:
    P("(未找到 search_feed_author.json)")

open(os.path.join(D, "extract.txt"), "w", encoding="utf-8").write("\n".join(lines))
P("")
P("已写入 out/stage5/extract.txt")
