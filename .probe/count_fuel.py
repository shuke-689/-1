# -*- coding: utf-8 -*-
"""只读：统计当前名单里「有微信号、且台账里没有」的待加燃料。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

d = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
led = json.load(open(os.path.join(BASE, "out", "wechat", "add_results.json"), encoding="utf-8"))
led_c = {(r.get("contact") or "") for r in led}

wx = [r for r in d if r.get("contact_type") == "微信" and (r.get("contact") or "").strip()]
free = [r for r in wx if (r.get("contact") or "") not in led_c]

print("darens.json = %d 条 / 微信号达人 = %d / 待加新微信号 = %d" % (len(d), len(wx), len(free)))
for r in free:
    print("   + %-26s %-20s fans=%s" % ((r.get("nick") or "(无昵称)")[:24],
                                        r.get("contact"), r.get("fans")))
print()
sent = sum(1 for r in led if r.get("add_status") == "sent")
print("台账 %d 条 / sent 总数 = %d（今日基线 370 ⇒ 今日已发 %d）" % (len(led), sent, sent - 370))
