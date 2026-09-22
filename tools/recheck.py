#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""名单复核器 —— 用**当前代码里的规则**重新检查 `out/collect/darens.json`。

用途（为什么需要它）：
  - 名单是历史多轮累积的，规则却一直在长（如 2026-09-22 简化了规则4、下架了分支Z）。
  - 某一轮采集可能是在**新规则写进代码之前**启动的 -> 它产出的名单没经过新规则。
  - 阶段B 只认 darens.json，不重筛 -> 必须在这里补一道闸，避免把不该加的达人加出去。

复核项（全部在本地用记录里已存的字段重算，不再打开浏览器）：
  · 规则2b 结算额兜底 settle_ok(live_low, live_high)   -> 不在 SALE_OPTION 区间内即不合格
    （规则2c 未授权放行：结算额读不到但等级 >= UNAUTH_LEVEL_MIN 的，与 collect.py 一致地放行）
  · 规则2d 粉丝量兜底 fans_ok(fans)                    -> 超 FANS_MAX（或取不到）不合格
  · 规则4  主推类目   cate_verdict(main_cate)          -> 没命中 个护家清/美妆 其一即 nocate
  · 规则3b 禁忌商品   product_exclude_hit(titles)
  · 规则3c 店铺家数   shopcnt_verdict(shops)
  · 规则3d 低价铺货   price_cheap_ratio >= CHEAP_RATIO（且 price_n/price_rows >= PRICE_MIN_PARSE）
  · 规则3a 同品牌     brand_verdict(shops)
  · 规则7  昵称排除   nick_rules.nick_exclude_reason(nickname)

⚠️ 2026-09-22 变更：原名 `tools/z_recheck.py`（Z 口径复核器）。分支Z 删除后，
   其中的 `z_verdict` 与规则3f（`shopshare_verdict`）复核项**一并移除**，
   类目项改为与采集同源的 `cate_verdict`。报告文件名改为 `out/recheck_report.txt`。

用法：
  python tools/recheck.py            # 只出报告，不改名单
  python tools/recheck.py --drop     # 额外：把不合格的达人从 darens.json 摘掉（自动备份）

⚠️ 只对「有微信联系方式」的记录做裁决（没有联系方式的本来也加不了），
   但报告里会列出全部不合格项，便于人工复核。
"""
import argparse
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
OUT = os.path.join(BASE, "out")
COLLECT = os.path.join(OUT, "collect")
DARENS = os.path.join(COLLECT, "darens.json")
REPORT = os.path.join(OUT, "recheck_report.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true",
                    help="把不合格的达人从 darens.json 摘掉（会先备份）")
    ap.add_argument("--file", default=DARENS, help="待复核的名单 json")
    a = ap.parse_args()

    sys.path.insert(0, BASE)
    import collect as C          # noqa: E402
    import nick_rules as NR      # noqa: E402

    recs = json.load(open(a.file, encoding="utf-8"))
    out = open(REPORT, "w", encoding="utf-8")
    P = lambda *x: print(*x, file=out)

    P("复核文件 = %s" % a.file)
    P("记录数 = %d" % len(recs))
    P("口径：%s=%s-%s / UNAUTH_LEVEL_MIN=%d / FANS_MAX=%d / CHEAP_RATIO=%.0f%%"
      " / MIN_SHOP_CNT=%d / 规则4=命中%s其一"
      % (C.SALE_LABEL, C.SETTLE_MIN, C.SETTLE_MAX, C.UNAUTH_LEVEL_MIN, C.FANS_MAX,
         C.CHEAP_RATIO * 100, C.MIN_SHOP_CNT, "/".join(C.CATE_MUST_ANY)))
    P("")

    bad, keep = [], []
    for r in recs:
        why = []
        # 规则2b 结算额兜底（与 collect.py 复用同一个 settle_ok，避免口径分叉）
        # 规则2c 未授权放行：结算额读不到数值但等级够 -> collect.py 放行，
        #   并且会把「带货分析」四条一并免掉（数据本来就读不到）——这里保持一致。
        unauth_pass = False
        if C.LOCAL_SETTLE_FILTER:
            _lo, _hi = C.settle_pair(r)     # 兼容 live_low/high 与 settle_live{low,high} 两种存档形态
            ok_s, note = C.settle_ok(_lo, _hi)
            if not ok_s:
                if C.settle_unreadable(_lo, _hi) and C.level_ok(r.get("level")):
                    unauth_pass = True          # 规则2c
                else:
                    why.append("2b结算额%s" % note)
        # 规则4 主推类目（2026-09-22 简化：只要命中 个护家清/美妆 其一）
        okc, _hits, whyc = C.cate_verdict(r.get("main_cate") or [])
        if not okc:
            why.append("规则4类目:%s" % whyc)
        # 规则2d 粉丝量兜底
        if C.LOCAL_FANS_FILTER:
            _fok, _fnote = C.fans_ok(r.get("fans"))
            if not _fok:
                why.append("2d粉丝%s" % _fnote)
        if unauth_pass:
            # 规则2c 命中：带货分析（3a/3b/3c/3d）在采集时已因「未授权」被免掉，
            # 名单里这几个字段本就是空的 -> 不再拿它们判不合格，否则会误杀。
            nk = NR.nick_exclude_reason(r.get("nickname") or "")
            if nk:
                why.append("规则7:" + nk)
            rec = {"nickname": r.get("nickname"), "contact": r.get("contact"),
                   "uid": r.get("uid"), "why": why}
            (bad if why else keep).append(rec)
            if why:
                P("❌ %-20s 微信=%-20s %s" % (str(r.get("nickname"))[:20],
                                            str(r.get("contact"))[:20], " | ".join(why)))
            continue
        hit = C.product_exclude_hit(r.get("titles"))
        if hit:
            why.append("3b商品词:%s" % hit)
        shops = r.get("shops") or []
        c3c, scnt, slist = C.shopcnt_verdict(shops)
        if c3c:
            why.append("3c店铺仅%d家" % scnt)
        # 3d 低价铺货（用记录里存好的占比，再校验样本是否足够）
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
        # 3a 同品牌
        bs, br, bn, bt, bc = C.brand_verdict(shops)
        if bs:
            why.append("3a同品牌%.0f%%:%s" % (br * 100, bn))
        # 规则7 昵称
        nk = NR.nick_exclude_reason(r.get("nickname") or "")
        if nk:
            why.append("规则7:" + nk)

        rec = {"nickname": r.get("nickname"), "contact": r.get("contact"),
               "uid": r.get("uid"), "why": why}
        (bad if why else keep).append(rec)
        if why:
            P("❌ %-20s 微信=%-20s %s" % (str(r.get("nickname"))[:20],
                                        str(r.get("contact"))[:20], " | ".join(why)))

    P("")
    P("=== 汇总：不合格 %d 条 / 合格 %d 条（共 %d）===" % (len(bad), len(keep), len(recs)))

    if a.drop and bad:
        bad_uids = {b["uid"] for b in bad if b["uid"]}
        bak = os.path.join(COLLECT, "darens.bak_before_recheck_%s.json"
                           % time.strftime("%H%M%S"))
        shutil.copy2(a.file, bak)
        new = [r for r in recs if r.get("uid") not in bad_uids]
        import darens_io
        darens_io.write_outputs(new, COLLECT, "", log=lambda *x: print(*x, file=out))
        P("")
        P("已摘除 %d 条；darens.json 现 %d 条；备份 %s"
          % (len(recs) - len(new), len(new), os.path.basename(bak)))
    out.close()
    print("report -> %s" % REPORT)


if __name__ == "__main__":
    main()
