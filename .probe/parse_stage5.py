# -*- coding: utf-8 -*-
"""解析 stage5 抓到的接口响应，重点看 square/filter 和 square/search_feed_author。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "out", "stage5", "daren_api.jsonl")
DST = os.path.join(BASE, "out", "stage5")

out_lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out_lines.append(s)


with open(SRC, encoding="utf-8") as f:
    recs = [json.loads(l) for l in f if l.strip()]

P("共 %d 条响应" % len(recs))

for r in recs:
    u = r["url"]
    path = u.split("?")[0]
    short = path.replace("https://buyin.jinritemai.com", "")
    try:
        data = json.loads(r["body"])
    except Exception:
        continue

    # 只细看关键接口
    if "square/filter" in path:
        P("")
        P("#" * 78)
        P("## filter 接口: %s" % short)
        P("#" * 78)
        with open(os.path.join(DST, "filter.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        P(json.dumps(data, ensure_ascii=False, indent=1)[:8000])

    elif "search_feed_author" in path:
        P("")
        P("#" * 78)
        P("## search_feed_author 响应结构")
        P("#" * 78)
        with open(os.path.join(DST, "search_feed_author.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        def walk(o, prefix="", depth=0):
            if depth > 4:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, (dict, list)):
                        P("  %s%s: %s" % ("  " * depth, k, type(v).__name__))
                        walk(v, prefix + k + ".", depth + 1)
                    else:
                        sv = str(v)
                        if len(sv) > 90:
                            sv = sv[:90] + "..."
                        P("  %s%s = %r" % ("  " * depth, k, sv))
            elif isinstance(o, list):
                P("  %s[list len=%d]" % ("  " * depth, len(o)))
                if o:
                    walk(o[0], prefix + "[]", depth + 1)

        walk(data)

        # 找联系方式/微信号相关字段
        P("")
        P("--- 含 contact/wechat/wx 关键字的字段 ---")
        txt = json.dumps(data, ensure_ascii=False)
        for kw in ("contact", "wechat", "weixin", "wx_", "phone", "mobile", "联系方式"):
            idx = 0
            cnt = 0
            while cnt < 3:
                i = txt.find(kw, idx)
                if i < 0:
                    break
                P("  %r ... %s" % (kw, txt[max(0, i - 80):i + 120]))
                idx = i + 1
                cnt += 1

    else:
        P("")
        P("## 其他接口 %s" % short)
        s = json.dumps(data, ensure_ascii=False)
        P("   %s" % s[:400])

with open(os.path.join(DST, "api_summary.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))
P("")
P("摘要已写入 out/stage5/api_summary.txt")
