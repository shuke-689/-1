# -*- coding: utf-8 -*-
"""从 out/collect/archive/ 的历史名单里重建「可加好友的候选名单」darens.json。

用途：`wechat_add.py`（阶段B）强制要求 `out/collect/darens.json`。
当阶段A因为登录/限流没跑出正式名单时，可以用历史归档救急跑一轮。

它做的事（**只读归档，只写 darens.json**）：
  1. 读 out/collect/archive/darens_*.json，按 uid 去重；
  2. 按**现行**业务规则复检（类目组合 / 内容类型 / 昵称排除 / 店铺禁忌词 / 同品牌占比）；
  3. 只保留 `contact_type == 微信`（**手机号一律搜不到，直接丢**）；
  4. 再按 **contact 去重**（同一微信号可能挂在两个 uid 下，否则会重复搜索）;
  5. 跳过已在 out/wechat/add_results.json 台账里处理过的 uid；
  6. 写出 out/collect/darens.json（运行时用的）+ out/collect/darens_from_archive.json（留痕）。

用法：
  "$PY" .probe/build_candidates_from_archive.py            # 只看报告
  "$PY" .probe/build_candidates_from_archive.py --write    # 真正写 darens.json
环境变量：
  CAND_LIMIT   最多保留几个（默认 10，配合微信 10 个/轮的风控）
  GENDER_FEMALE_ONLY=0 可放开性别限制（默认按规则6 只留 gender==2）
"""
import io
import json
import os
import sys

# ⚠️ 必须先 import collect：它内部会把 sys.stdout 重新包成 utf-8 文本流；
#    如果我们自己先包一层，两个 TextIOWrapper 抢同一个 buffer，
#    GC 时会把底层 buffer 关掉 -> 之后所有 print 都报 "I/O operation on closed file"。
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import collect as C          # noqa: E402  复用规则判定，避免逻辑分叉

if getattr(sys.stdout, "encoding", "").lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ARCH = os.path.join(BASE, "out", "collect", "archive")
OUTDIR = os.path.join(BASE, "out", "collect")
LEDGER = os.path.join(BASE, "out", "wechat", "add_results.json")

CAND_LIMIT = int(os.environ.get("CAND_LIMIT", "10"))
FEMALE_ONLY = os.environ.get("GENDER_FEMALE_ONLY", "1") not in ("0", "false", "False")


def load_ledger_uids():
    if not os.path.exists(LEDGER):
        return set()
    try:
        led = json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(led, dict):
        return {k for k, v in led.items() if (v or {}).get("add_status")}
    return {r.get("uid") for r in led if r.get("add_status")}


def verdict(r):
    """返回排除原因列表；空列表 = 通过。"""
    bad = []
    if r.get("contact_type") != "微信":
        bad.append("非微信号(%s)" % r.get("contact_type"))
    if FEMALE_ONLY and r.get("gender") != 2:
        bad.append("非女性(gender=%s)" % r.get("gender"))
    if (r.get("fans") or 0) >= 100000:
        bad.append("粉丝>=10w")
    city = r.get("city") or ""
    if any(x in city for x in ("海南", "新疆", "西藏")):
        bad.append("地区排除(%s)" % city)
    ok, _hits, why = C.cate_verdict(r.get("main_cate") or [])
    if not ok:
        bad.append("类目(%s:%s)" % (why, r.get("main_cate")))
    ct_hit = [x for x in (r.get("content_type") or []) if x in C.CONTENT_EXCLUDE]
    if ct_hit:
        bad.append("内容类型%s" % ct_hit)
    nh = C.nick_exclude_hit(r.get("nickname") or "")
    if nh:
        bad.append("昵称排除(%s)" % nh)
    shops = r.get("shops") or []
    ph = C.product_exclude_hit(shops)
    if ph:
        bad.append("店铺含禁忌词(%s)" % ph)
    if C.same_brand(shops):
        bad.append("带货同品牌占比过半")
    return bad


def main():
    write = "--write" in sys.argv
    if not os.path.isdir(ARCH):
        print("!! 没有归档目录 %s" % ARCH)
        return 1

    files = sorted(f for f in os.listdir(ARCH) if f.startswith("darens_") and f.endswith(".json"))
    if not files:
        print("!! 归档里没有 darens_*.json")
        return 1

    seen_uid, recs = set(), []
    for f in files:
        try:
            data = json.load(open(os.path.join(ARCH, f), encoding="utf-8"))
        except Exception as e:
            print("  （跳过 %s：%s）" % (f, e))
            continue
        for r in data:
            uid = r.get("uid")
            if not uid or uid in seen_uid:
                continue
            seen_uid.add(uid)
            r["_src_archive"] = f
            recs.append(r)
    print("归档 %d 个文件，按 uid 去重后 %d 条" % (len(files), len(recs)))

    done = load_ledger_uids()
    print("台账已处理 uid：%d 个" % len(done))

    passed, dropped = [], []
    for r in recs:
        if r.get("uid") in done:
            dropped.append((r, ["台账已处理"]))
            continue
        bad = verdict(r)
        (dropped if bad else passed).append((r, bad))
    print("规则复检：通过 %d 条，排除 %d 条" % (len(passed), len(dropped)))

    # 按 contact 去重（同一微信号可能挂在两个 uid 下 -> 否则会重复搜索）
    uniq, seen_ct = [], set()
    for r, _ in passed:
        ct = (r.get("contact") or "").strip()
        if not ct or ct in seen_ct:
            continue
        seen_ct.add(ct)
        uniq.append(r)
    dup = len(passed) - len(uniq)
    if dup:
        print("按 contact 去重：- %d 条重复微信号" % dup)
    print("最终候选 %d 个微信号" % len(uniq))

    picked = uniq[:CAND_LIMIT] if CAND_LIMIT else uniq
    if CAND_LIMIT and len(uniq) > CAND_LIMIT:
        print("按 CAND_LIMIT=%d 截取，本轮将加 %d 个" % (CAND_LIMIT, len(picked)))

    print()
    print("=== 本轮候选 ===")
    for i, r in enumerate(picked, 1):
        print("  %2d. %-20s %-18s %s" % (
            i, r.get("contact"), (r.get("nickname") or "")[:16],
            "/".join(r.get("main_cate") or [])))

    if dropped:
        print()
        print("=== 被排除（前 20）===")
        for r, bad in dropped[:20]:
            print("  %-20s %-16s %s" % (
                r.get("contact"), (r.get("nickname") or "")[:14], "; ".join(bad)))

    if not write:
        print()
        print("（预览模式：未写文件。加 --write 才写 out/collect/darens.json）")
        return 0

    os.makedirs(OUTDIR, exist_ok=True)
    for name in ("darens.json", "darens_from_archive.json"):
        with open(os.path.join(OUTDIR, name), "w", encoding="utf-8") as f:
            json.dump(picked, f, ensure_ascii=False, indent=1)
    print()
    print("已写出：")
    print("  out/collect/darens.json              （wechat_add.py 读这个）")
    print("  out/collect/darens_from_archive.json （留痕，标明来自归档）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
