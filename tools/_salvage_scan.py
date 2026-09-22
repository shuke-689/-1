# 扫描所有历史采集产出，找「有微信联系方式 且 不在台账 且 通过 Z 口径」的达人
import sys, os, json, glob, collections
B = r"C:\Users\Administrator\WorkBuddy\抖音"
sys.path.insert(0, B)
out = open(os.path.join(B, "out", "_salvage_scan.txt"), "w", encoding="utf-8")
P = lambda *a: print(*a, file=out)

import nick_rules as NR
import darens_io  # noqa  (仅确认可导入)

# Z 纯函数：从 collect.py 抽出来单跑，避免 import collect 的 stdout 副作用
Z_MAIN = ("个护家清", "美妆")
Z_SINGLE_CONTENT = ("时尚", "情感", "剧情", "颜值", "音乐", "舞蹈", "亲子")


def z_verdict(main_cate, content_type):
    mc = list(main_cate or [])
    hits = [c for c in Z_MAIN if c in mc]
    if not hits:
        return False, 0, "z_nocate"
    if len(hits) >= 2:
        return True, 2, ""
    if [c for c in mc if c not in Z_MAIN]:
        return True, 1, ""
    if any(c in Z_SINGLE_CONTENT for c in (content_type or [])):
        return True, 1, ""
    return False, 1, "z_single"


led = json.load(open(os.path.join(B, "out", "wechat", "add_results.json"), encoding="utf-8"))
have = {r.get("contact") for r in led if r.get("contact")}
P("台账条数 = %d，其中已用微信号 = %d" % (len(led), len(have)))

files = sorted(set(glob.glob(os.path.join(B, "out", "collect", "*.json"))
                     + glob.glob(os.path.join(B, "out", "collect", "archive", "*.json"))))
files = [f for f in files if "apis" not in os.path.basename(f)]
P("扫描文件数 = %d" % len(files))

seen_uid, seen_contact = set(), set()
rows = []
per_file = collections.Counter()
for f in files:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        P("  [skip] %s (%s)" % (os.path.basename(f), e))
        continue
    if not isinstance(d, list):
        continue
    for r in d:
        if not isinstance(r, dict):
            continue
        c = r.get("contact")
        uid = r.get("uid")
        if not c or r.get("contact_type") != "微信":
            continue
        if c in have or c in seen_contact:
            continue
        if uid and uid in seen_uid:
            continue
        seen_contact.add(c)
        if uid:
            seen_uid.add(uid)
        ok, hits, why = z_verdict(r.get("main_cate"), r.get("content_type"))
        nick_kw = NR.nick_exclude_reason(r.get("nickname") or "")
        nick_ok = not nick_kw
        rows.append({"file": os.path.basename(f), "nickname": r.get("nickname"),
                     "contact": c, "uid": uid, "fans": r.get("fans"),
                     "main_cate": r.get("main_cate"), "content_type": r.get("content_type"),
                     "z_ok": ok, "z_why": why, "nick_ok": nick_ok, "nick_kw": nick_kw})
        per_file[os.path.basename(f)] += 1

P("")
P("=== 不在台账的「有微信」达人：共 %d 条 ===" % len(rows))
P("--- 按来源文件 ---")
for k, v in per_file.most_common():
    P("  %-34s %d" % (k, v))

zpass = [r for r in rows if r["z_ok"] and r["nick_ok"]]
P("")
P("=== 其中 通过 Z 口径 + 昵称规则：%d 条 ===" % len(zpass))
for r in zpass:
    P("  %-18s 微=%-18s 粉丝=%-8s main=%-26s content=%-12s [%s]"
      % (str(r["nickname"])[:18], r["contact"], r["fans"], str(r["main_cate"]),
         str(r["content_type"]), r["file"]))

P("")
P("--- 未通过 Z（仅记录原因统计）---")
cnt = collections.Counter((r["z_why"] or ("nick:" + str(r["nick_kw"]))) for r in rows if not (r["z_ok"] and r["nick_ok"]))
for k, v in cnt.most_common():
    P("  %-28s %d" % (str(k), v))

with open(os.path.join(B, "out", "_salvage_pass.json"), "w", encoding="utf-8") as f:
    json.dump(zpass, f, ensure_ascii=False, indent=1)
out.close()
print("done")
