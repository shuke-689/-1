#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""候选池回收器 —— 从**历史全部采集产出**里捞出还没加过的达人。

背景（为什么值得常备）：
  - 平台 11001 限流 + 候选切片漂移，导致「本轮采集产出为 0」是常态；
    而阶段B 又要求先攒够候选，于是经常卡在「台账已清空、名单却没新增」。
  - 但历史上每一轮 `darens*.json`（含 `archive/`）里，都可能有
    「有微信联系方式、当时没进阶段B」的达人 —— 这批人**不用重新开浏览器**就能加。

做法：
  1. 扫 `out/collect/**/*.json`（排除 apis*/probe*）；
  2. 用**当前代码里的规则**复核：规则2b/2c 结算额 + 规则2d 粉丝量 + 规则4 类目
     + 规则3b/3c/3d/3a + 规则7 昵称；
  3. 与台账 `out/wechat/add_results.json` 的微信号去重、按 uid 去重；
  4. 输出 `out/salvage_ready.json`（可直接并入名单的那批），并打印明细。

用法：
  python tools/salvage_scan.py                 # 只扫描出报告
  python tools/salvage_scan.py --merge         # 额外并入 darens.json（自动备份，按 uid 去重）
  python tools/salvage_scan.py --no-cate       # 不套规则4 类目口径（只按昵称+台账去重）

⚠️ 2026-09-22：分支Z 删除后，`z_verdict` 与规则3f 复核项**一并移除**，
   类目项改为与采集同源的 `cate_verdict`；旧参数 `--no-z` 仍可用（等价 `--no-cate`）。
⚠️ 并入 darens.json 前务必确认 `tools/collect_more.py` 没有正在跑：
   驱动在**结束时**会用「启动时的 base + 本轮新增」整体重写 darens.json，
   会把这里并入的记录冲掉（已加入台账的不受影响，但名单会缺这几条）。
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
OUT = os.path.join(BASE, "out")
COLLECT = os.path.join(OUT, "collect")
LEDGER = os.path.join(OUT, "wechat", "add_results.json")
DARENS = os.path.join(COLLECT, "darens.json")
READY = os.path.join(OUT, "salvage_ready.json")
REPORT = os.path.join(OUT, "salvage_scan_report.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="把合格候选并入 darens.json")
    ap.add_argument("--no-cate", "--no-z", dest="no_cate", action="store_true",
                    help="不套本地类目口径（规则4）")
    a = ap.parse_args()

    import collect as C          # noqa: E402
    import nick_rules as NR      # noqa: E402

    out = open(REPORT, "w", encoding="utf-8")
    P = lambda *x: print(*x, file=out)

    led = json.load(open(LEDGER, encoding="utf-8"))
    have = {r.get("contact") for r in led if r.get("contact")}
    P("台账 %d 条 / 已用微信号 %d 个" % (len(led), len(have)))

    files = []
    for pat in ("*.json", os.path.join("archive", "*.json")):
        files += glob.glob(os.path.join(COLLECT, pat))
    files = [f for f in sorted(set(files))
             if not os.path.basename(f).startswith(("apis", "probe"))
             and os.path.basename(f) != "darens.json"]
    P("扫描 %d 个历史产出文件" % len(files))

    seen_uid, seen_contact, ready, skipped = set(), set(), [], []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict):
                continue
            c = r.get("contact")
            if not c or r.get("contact_type") != "微信":
                continue
            if c in have or c in seen_contact:
                continue
            if r.get("uid") and r.get("uid") in seen_uid:
                continue
            seen_contact.add(c)
            if r.get("uid"):
                seen_uid.add(r["uid"])

            why = []
            # 规则2b 结算额兜底 + 规则2c 未授权放行（复用 collect.py 的同一套判定）
            # ⚠️ 2026-09-22 补：此前这里**完全没有结算额关卡**，而 `--merge` 会直接把
            #    合格项写进 darens.json -> 阶段B 只认名单、不重筛，越界达人会被直接加好友。
            unauth_pass = False
            if C.LOCAL_SETTLE_FILTER:
                _lo, _hi = C.settle_pair(r)   # 兼容 live_low/high 与 settle_live{low,high}
                ok_s, note = C.settle_ok(_lo, _hi)
                if not ok_s:
                    if C.settle_unreadable(_lo, _hi) and C.level_ok(r.get("level")):
                        unauth_pass = True    # 规则2c
                    else:
                        why.append("2b结算额%s" % note)
            if not a.no_cate:
                okc, _h, whyc = C.cate_verdict(r.get("main_cate") or [])
                if not okc:
                    why.append("规则4类目:" + str(whyc))
            # 规则2d 粉丝量兜底（2026-09-22 补：回收原先不查粉丝量，
            #   而 `--merge` 会直接把合格项写进 darens.json）
            if C.LOCAL_FANS_FILTER:
                _fok, _fnote = C.fans_ok(r.get("fans"))
                if not _fok:
                    why.append("2d粉丝%s" % _fnote)
            # 规则2c 放行的达人「带货分析」本来就读不到 -> 下列 3a/3b/3c/3d 的样本
            # 字段是空的，各判定函数对空样本都返回「不判定」，不会误杀，故无需额外跳过。
            hit = C.product_exclude_hit(r.get("titles"))
            if hit:
                why.append("3b商品词:" + hit)
            shops = r.get("shops") or []
            c3c, scnt, _sl = C.shopcnt_verdict(shops)
            if c3c:
                why.append("3c店铺仅%d家" % scnt)
            # 规则3d 低价铺货（2026-09-22 补：原文件 docstring 声称查了 3d，实际没查）
            try:
                ratio_d = float(r.get("price_cheap_ratio") or 0)
            except (TypeError, ValueError):
                ratio_d = 0.0
            n_ok, n_all = r.get("price_n") or 0, r.get("price_rows") or 0
            if n_all and n_ok >= max(3, int(n_all * C.PRICE_MIN_PARSE)):
                if ratio_d >= C.CHEAP_RATIO:
                    why.append("3d低价%.0f%%" % (ratio_d * 100))
            elif n_all:
                why.append("3d样本不足(%s/%s)" % (n_ok, n_all))
            bs, br, bn, _bt, _bc = C.brand_verdict(shops)
            if bs:
                why.append("3a同品牌%.0f%%:%s" % (br * 100, bn))
            nk = NR.nick_exclude_reason(r.get("nickname") or "")
            if nk:
                why.append("规则7:" + nk)

            row = {"nickname": r.get("nickname"), "contact": c, "uid": r.get("uid"),
                   "fans": r.get("fans"), "main_cate": r.get("main_cate"),
                   "content_type": r.get("content_type"), "from": os.path.basename(f),
                   "why": why, "_rec": r}
            (ready if not why else skipped).append(row)

    P("")
    P("=== 可回收（不在台账 + 通过当前全部规则）：%d 个 ===" % len(ready))
    for r in ready:
        P("  ✅ %-20s 微信=%-20s 粉丝=%-8s main=%-24s [%s]"
          % (str(r["nickname"])[:20], r["contact"], r["fans"],
             str(r["main_cate"])[:24], r["from"]))
    P("")
    P("=== 被规则挡下（仅列前 40 条）===")
    for r in skipped[:40]:
        P("  ❌ %-20s %s" % (str(r["nickname"])[:20], " | ".join(r["why"])))
    if len(skipped) > 40:
        P("  … 另有 %d 条" % (len(skipped) - 40))

    json.dump([{k: v for k, v in r.items() if k != "_rec"} for r in ready],
              open(READY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if a.merge and ready:
        base = json.load(open(DARENS, encoding="utf-8"))
        bu = {r.get("uid") for r in base if r.get("uid")}
        add = [r["_rec"] for r in ready if r["uid"] not in bu]
        if add:
            bak = os.path.join(COLLECT, "darens.bak_before_salvage_%s.json"
                               % time.strftime("%H%M%S"))
            shutil.copy2(DARENS, bak)
            merged, seen = [], set()
            for r in base + add:
                u = r.get("uid")
                if not u or u in seen:
                    continue
                seen.add(u)
                merged.append(r)
            import darens_io
            darens_io.write_outputs(merged, COLLECT, "", log=lambda *x: print(*x, file=out))
            P("")
            P("已并入 %d 个；darens.json 现 %d 条；备份 %s"
              % (len(add), len(merged), os.path.basename(bak)))
        else:
            P("")
            P("并入：无新增（uid 全部已存在）")

    out.close()
    print("ready %d -> %s" % (len(ready), READY))
    print("report -> %s" % REPORT)


if __name__ == "__main__":
    main()
