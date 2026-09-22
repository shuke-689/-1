# -*- coding: utf-8 -*-
"""把某个「带 tag 的采集产物」并入正式名单 `out/collect/darens.json`（按 uid 去重）。

为什么需要它：
  `collect.py` 用 `OUT_TAG` 跑（如试跑 `OUT_TAG=_try10`）时只写 `darens_try10.json`，
  **不会**碰正式名单 —— 这是刻意的（否则旧名单会被归档、只剩这一小批）。
  要把试跑/补采的结果并进正式名单时，用本脚本，别手工拼 json。

用法：
  python tools/merge_into_darens.py --from out/collect/darens_try10.json --dry
  python tools/merge_into_darens.py --from out/collect/darens_try10.json --only-with-contact

行为：
  · 先把 darens.json 备份成 out/collect/darens.bak_before_merge_<HHMMSS>.json
  · 现有优先（同 uid 以现名单为准），只追加新的
  · 用 darens_io.write_outputs 回写 json / csv / xlsx（口径与 A 阶段一致）
  · `--only-with-contact`：只并入有联系方式（contact 非空）的 —— 阶段 B 用得上；
    被过滤掉的多是「带货规则跳过」的达人，会把条数打出来。
  · `--dry`：只报告不落盘。
"""
import argparse
import io
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = os.path.join(BASE, "out", "collect")
TARGET = os.path.join(OUT, "darens.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="待并入的 json（裸 list）")
    ap.add_argument("--only-with-contact", action="store_true",
                    help="只并入 contact 非空的记录（阶段 B 才用得上）")
    ap.add_argument("--dry", action="store_true", help="只报告，不写盘")
    a = ap.parse_args()

    src_path = a.src if os.path.isabs(a.src) else os.path.join(BASE, a.src)
    add = json.load(open(src_path, encoding="utf-8"))
    if isinstance(add, dict):
        add = add.get("darens") or add.get("list") or add.get("records") or []
    cur = json.load(open(TARGET, encoding="utf-8"))
    print("来源：%s（%d 条）" % (os.path.relpath(src_path, BASE), len(add)))
    print("现有 %s：%d 条" % (os.path.relpath(TARGET, BASE), len(cur)))

    dropped = []
    if a.only_with_contact:
        keep = []
        for r in add:
            if r.get("contact"):
                keep.append(r)
            else:
                dropped.append(r.get("nickname") or "?")
        print("仅保留有联系方式的：%d 条（丢弃 %d 条：%s）"
              % (len(keep), len(dropped), "、".join(dropped) if dropped else "-"))
        add = keep

    have = {r.get("uid") for r in cur if r.get("uid")}
    picked = [r for r in add if r.get("uid") and r.get("uid") not in have]
    dup = len(add) - len(picked)
    print("待并入 %d 条 -> 去重后新增 %d 条（同 uid 已存在 %d 条）" % (len(add), len(picked), dup))
    for r in picked:
        print("   + %-18s fans=%-7s %s %s" % ((r.get("nickname") or "")[:18], r.get("fans"),
                                              r.get("contact_type") or "", r.get("contact") or ""))
    if a.dry:
        print("（--dry，未写盘）")
        return

    merged, seen = [], set()
    for r in cur + picked:
        u = r.get("uid")
        if not u or u in seen:
            continue
        seen.add(u)
        merged.append(r)

    bak = os.path.join(OUT, "darens.bak_before_merge_%s.json" % time.strftime("%H%M%S"))
    shutil.copy2(TARGET, bak)
    print("已备份 -> %s" % os.path.basename(bak))

    import darens_io
    darens_io.write_outputs(merged, OUT, "", log=print)
    print("写回完成：darens.json = %d 条" % len(merged))


if __name__ == "__main__":
    main()
