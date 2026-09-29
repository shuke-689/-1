# -*- coding: utf-8 -*-
"""只读：列出 darens.json 里的手机号达人，标注是否已在 B 台账中。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

d = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
led = json.load(open(os.path.join(BASE, "out", "wechat", "add_results.json"), encoding="utf-8"))

ph = [r for r in d if (r.get("contact_type") == "手机") and (r.get("contact") or "").strip()]
print("darens 总数: %d / 手机号达人: %d" % (len(d), len(ph)))
for r in ph:
    c = r.get("contact") or ""
    st = [x.get("add_status") for x in led if (x.get("contact") or "") == c]
    nick = (r.get("nick") or "(无昵称)")[:24]
    print("  %-26s %-24s %s" % (nick, c, st if st else ["未加过"]))
