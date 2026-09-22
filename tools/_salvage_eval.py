# 对 15 个待回收候选套完整 Z 口径（含新规则3f 店铺占比）
import sys, os, json, glob
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_salvage_eval.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

import collect as C
import nick_rules as NR

pass_rows = json.load(open(os.path.join(B, "out", "_salvage_pass.json"), encoding="utf-8"))
raw = []
for f in set(r["file"] for r in pass_rows):
    for p in (os.path.join(B, "out", "collect", "archive", f),
              os.path.join(B, "out", "collect", f)):
        if os.path.exists(p):
            raw += json.load(open(p, encoding="utf-8"))
            break
by_uid = {r.get("uid"): r for r in raw if isinstance(r, dict)}

P("口径：FILTER_PROFILE=%s，SHOP_SHARE_RATIO=%.0f%%" % (C.FILTER_PROFILE, C.SHOP_SHARE_RATIO * 100))
P("")
keep = []
for r in pass_rows:
    rec = by_uid.get(r["uid"], {})
    nick = rec.get("nickname")
    shops = rec.get("shops") or []
    urls = rec.get("titles") or []
    lines = []
    # Z 类目/内容类型
    ok_z, hits, why_z = C.z_verdict(rec.get("main_cate"), rec.get("content_type"))
    lines.append("Z=%s%s" % (ok_z, "" if ok_z else "(" + str(why_z) + ")"))
    # 昵称
    nk = NR.nick_exclude_reason(nick)
    lines.append("昵称=%s" % ("OK" if not nk else nk))
    # 3c 店铺家数
    c3c, scnt, slist = C.shopcnt_verdict(shops)
    lines.append("3c店铺数=%d%s" % (scnt, "跳过" if c3c else "OK"))
    # 3f 单一店铺占比（新规则）
    c3f, fratio, fname, ftotal, fcnt = C.shopshare_verdict(shops)
    lines.append("3f最大店铺=%s %.0f%%(%d/%d)%s" % (fname or "-", fratio * 100, fcnt, ftotal,
                                                  " 跳过" if c3f else " OK"))
    # 3 品牌
    bskip, bratio, bname, btotal, bcnt = C.brand_verdict(shops)
    lines.append("3品牌=%s %.0f%%%s" % (bname or "-", bratio * 100, " 跳过" if bskip else " OK"))
    # 3b 商品禁忌词
    hit = C.product_exclude_hit(rec.get("titles"))
    lines.append("3b商品词=%s" % (hit or "OK"))
    # 3d 低价
    cskip, cratio, cn_ok, cn_all, cwhy = C.cheap_verdict(
        [{"price": None}] * (rec.get("price_rows") or 0))
    lines.append("3d低价历史值=%.0f%%(未重算)" % ((rec.get("price_cheap_ratio") or 0) * 100))
    bad = (not ok_z) or bool(nk) or c3c or c3f or bskip or hit
    P("%s %-20s | %s" % ("❌" if bad else "✅", str(nick)[:20], " | ".join(lines)))
    if not bad:
        keep.append({"nickname": nick, "contact": rec.get("contact"),
                     "uid": rec.get("uid"), "rec": rec})

P("")
P("=== 通过全部规则、可进入阶段B：%d 个 ===" % len(keep))
for k in keep:
    P("   %-20s 微信=%s" % (str(k["nickname"])[:20], k["contact"]))
json.dump(keep, open(os.path.join(B, "out", "_salvage_ready.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
out.close()
print("done")
