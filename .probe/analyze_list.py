# -*- coding: utf-8 -*-
"""分析阶段6抓到的 search_feed_author 响应：字段、地区分布、联系方式字段、筛选请求体。"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "out", "stage6", "list_api.jsonl")

recs = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
print("共 %d 条 search_feed_author 响应\n" % len(recs))

for i, r in enumerate(recs):
    try:
        d = json.loads(r["body"])
    except Exception:
        continue
    lst = (d.get("data") or {}).get("list") or []
    print("=" * 78)
    print("#%d  条数=%d  has_more=%s" % (i, len(lst), (d.get("data") or {}).get("has_more")))
    print("  请求体: %s" % (r["req"][:700] if r.get("req") else "(未捕获)"))
    if not lst:
        continue
    cities = Counter(a["author_base"].get("city", "") for a in lst)
    print("  地区分布: %s" % dict(cities))
    genders = Counter(a["author_base"].get("gender") for a in lst)
    print("  性别分布: %s" % dict(genders))
    fans = [a["author_base"].get("fans_num") for a in lst]
    print("  粉丝数范围: %s ~ %s" % (min(fans), max(fans)))
    names = [a["author_base"].get("nickname") for a in lst]
    print("  前5个: %s" % names[:5])
    # 联系方式字段
    ac = lst[0].get("author_contact")
    print("  author_contact[0]: %s" % json.dumps(ac, ensure_ascii=False))
    # 结算字段
    si = lst[0].get("sale_info", {})
    print("  sale_info 键: %s" % list(si.keys()))
    for k in ("video_total_sales_settle", "total_sales_settle"):
        if k in si:
            print("    %s = %s" % (k, json.dumps(si[k], ensure_ascii=False)[:250]))

# 全量地区统计
print()
print("=" * 78)
allc = Counter()
allg = Counter()
for r in recs:
    try:
        d = json.loads(r["body"])
    except Exception:
        continue
    for a in (d.get("data") or {}).get("list") or []:
        allc[a["author_base"].get("city", "")] += 1
        allg[a["author_base"].get("gender")] += 1
print("全部地区: %s" % dict(allc.most_common(40)))
print("全部性别: %s  (1=男 2=女)" % dict(allg))

# 是否有海南/新疆/西藏
print()
print("需排除地区是否出现: ", {k: v for k, v in allc.items()
      if any(x in k for x in ("海南", "新疆", "西藏", "海外", "香港", "澳门", "台湾"))})
