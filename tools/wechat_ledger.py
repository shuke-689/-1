#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""台账修复器 —— 把**疑似误判**的状态改回「待加」，或查看台账明细。

为什么需要它：
  `not_found` 在 `wechat_add.py` 里属于 `DONE_STATUS` -> **永久跳过**。
  但 RUNBOOK §3 已明确记录：`not_found` 可能是**误判**（截图/窗口状态异常导致
  结果页读错，或搜索步骤失败）。一旦误判，这个达人再也不会被重试 —— 直接丢候选。
  本工具只做一件事：把指定微信号的行从 `not_found` 改回待加（= 从台账里摘掉该行），
  让它下一轮重新排队。**不改动其它任何状态**。

用法：
  python tools/wechat_ledger.py --list dup              # 列出台账里重复/异常的行
  python tools/wechat_ledger.py --show not_found        # 列出某状态的行
  python tools/wechat_ledger.py --requeue zhaoquqing,sisao119
      # 把这两个微信号的 not_found 行摘掉 -> 下轮重试（自动备份 add_results.json）

⚠️ 纯本地文件操作，不会碰微信、不会发申请。
"""
import argparse
import json
import os
import shutil
import sys
import time
import collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(BASE, "out", "wechat", "add_results.json")
DONE = ("sent", "already", "excluded", "not_found")


def load():
    return json.load(open(LEDGER, encoding="utf-8"))


def save(recs):
    bak = os.path.join(os.path.dirname(LEDGER),
                       "add_results.bak_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(LEDGER, bak)
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    # csv 汇总一并刷新
    try:
        sys.path.insert(0, BASE)
        import wechat_add
        wechat_add.export_csv(recs)
    except Exception as e:
        print("（csv 刷新跳过：%s）" % e)
    return bak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", metavar="STATUS", help="列出某状态的行")
    ap.add_argument("--list", metavar="WHAT", choices=["dup", "count"], help="dup=重复行")
    ap.add_argument("--requeue", metavar="微信号,微信号", help="把这些号的 not_found 摘掉")
    a = ap.parse_args()

    recs = load()
    print("台账 %d 条 / 状态 %s" % (len(recs), dict(collections.Counter(
        r.get("add_status") for r in recs))))

    if a.list == "count":
        for k, v in collections.Counter(r.get("add_status") for r in recs).items():
            print("  %-14s %d" % (k, v))
        return
    if a.list == "dup":
        c = collections.Counter(r.get("contact") for r in recs if r.get("contact"))
        for k, v in c.items():
            if v > 1:
                print("  重复 %s x%d" % (k, v))
        return
    if a.show:
        for r in recs:
            if r.get("add_status") == a.show:
                print("  %-22s 微=%-24s %s" % (str(r.get("nickname"))[:22],
                                              str(r.get("contact"))[:24],
                                              str(r.get("add_note"))[:30]))
        return

    if a.requeue:
        want = {x.strip() for x in a.requeue.split(",") if x.strip()}
        hit = [r for r in recs if r.get("contact") in want]
        miss = want - {r.get("contact") for r in hit}
        print("命中 %d 条（未找到：%s）" % (len(hit), ",".join(sorted(miss)) or "无"))
        for r in hit:
            print("  - %-22s 微=%-24s 原状态=%s" % (str(r.get("nickname"))[:22],
                                                 str(r.get("contact"))[:24],
                                                 r.get("add_status")))
        keep = [r for r in recs if r.get("contact") not in want]
        bak = save(keep)
        print("已摘除 %d 条；台账 %d -> %d；备份 %s"
              % (len(recs) - len(keep), len(recs), len(keep), os.path.basename(bak)))
        print("👉 这些达人已回到待加队列：python wechat_add.py status")


if __name__ == "__main__":
    main()
