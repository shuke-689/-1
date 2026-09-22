# 精确回答：**有微信可加**的达人中，有多少条会因新规则3f（或其它规则）被拦
import sys, os, json
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_recheck_wechat.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

import collect as C
import nick_rules as NR

recs = json.load(open(os.path.join(B, "out", "collect", "darens.json"), encoding="utf-8"))
led = json.load(open(os.path.join(B, "out", "wechat", "add_results.json"), encoding="utf-8"))
have = {r.get("contact") for r in led if r.get("contact")}

cand = [r for r in recs if r.get("contact") and r.get("contact_type") == "微信"]
P("darens 总 %d 条；有微信 %d 条；其中有微信且**未在台账** = %d 条"
  % (len(recs), len(cand), len([r for r in cand if r.get("contact") not in have])))
P("")

bad3f, badother, oknew = [], [], []
for r in cand:
    if r.get("contact") in have:
        continue
    f, fr, fn, ft, fc = C.shopshare_verdict(r.get("shops") or [])
    why = []
    okz, _h, whyz = C.z_verdict(r.get("main_cate"), r.get("content_type"))
    if not okz:
        why.append("Z:" + str(whyz))
    c3c, scnt, _s = C.shopcnt_verdict(r.get("shops") or [])
    if c3c:
        why.append("3c店铺仅%d家" % scnt)
    bs, br, bn, _b1, _b2 = C.brand_verdict(r.get("shops") or [])
    if bs:
        why.append("3a同品牌%.0f%%" % (br * 100))
    hit = C.product_exclude_hit(r.get("titles"))
    if hit:
        why.append("3b:" + hit)
    nk = NR.nick_exclude_reason(r.get("nickname") or "")
    if nk:
        why.append("规则7:" + nk)
    if f:
        bad3f.append((r, fr, fn, why))
    elif why:
        badother.append((r, why))
    else:
        oknew.append(r)

P("=== ⚠️ 有微信且未加、但会被【新规则3f】拦下：%d 个 ===" % len(bad3f))
for r, fr, fn, why in bad3f:
    P("  ❌ %-20s 微信=%-18s 最大店铺「%s」%.0f%%  其它:%s"
      % (str(r["nickname"])[:20], r["contact"], fn, fr * 100, " / ".join(why) or "-"))
P("")
P("=== 有微信且未加、被其它规则拦下：%d 个 ===" % len(badother))
for r, why in badother:
    P("  ❌ %-20s 微信=%-18s %s" % (str(r["nickname"])[:20], r["contact"], " / ".join(why)))
P("")
P("=== ✅ 干净可加（通过 Z + 3a/3b/3c/3f + 规则7）：%d 个 ===" % len(oknew))
for r in oknew:
    f, fr, fn, ft, fc = C.shopshare_verdict(r.get("shops") or [])
    P("  ✅ %-20s 微信=%-20s 店铺%d家 最大「%s」%.0f%%"
      % (str(r["nickname"])[:20], r["contact"], len(set(r.get("shops") or [])),
         fn or "-", fr * 100))
out.close()
print("done")
