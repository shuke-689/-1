# -*- coding: utf-8 -*-
"""飞书登记表体检：找出结算额异常的行。

背景（2026-09-17 排查）：
    平台侧「直播结算总额 = 1w-10w」筛选**不严格**，实测一批 156 条里漏出 16 条
    （约 10%），其中 settle_live = 0-0 的会被原样写上飞书 ——
    表现为「结算总额 / 直播结算总额 / 短视频结算总额」三列全 `0-0`。
    collect.py 已加规则2b 本地兜底拦截，此脚本用于**回查历史遗留**。

用法：
    "$PY" feishu_audit.py              # 只读体检，列出异常行
    "$PY" feishu_audit.py --json       # 顺带把结果写成 out/feishu/audit.json
只读：只调 record-list，绝不写库、不删行。
"""
import argparse
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import feishu_sync as F  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SETTLE_COLS = ("结算总额", "直播结算总额", "短视频结算总额")


def cell(fields, key):
    """飞书单元格可能是 str 或 [str]，统一成 str。"""
    v = fields.get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or "")
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-token", default=F.DEFAULT_BASE_TOKEN)
    ap.add_argument("--table-id", default=F.DEFAULT_TABLE_ID)
    ap.add_argument("--json", action="store_true", help="另存 out/feishu/audit.json")
    a = ap.parse_args()

    idx = F.fetch_existing(a.base_token, a.table_id)
    if idx is None:
        print("!! 读记录失败（先确认 lark-cli 已登录：lark-cli auth status）")
        return 1

    print("飞书表 %s / %s" % (a.base_token, a.table_id))
    print("共 %d 条记录" % len(idx))

    bad = []
    for name, rec in idx.items():
        f = rec.get("fields") or {}
        vals = {c: cell(f, c) for c in SETTLE_COLS}
        if all(vals[c].strip() in ("0-0", "") for c in SETTLE_COLS):
            bad.append({
                "达人名称": name,
                "record_id": rec.get("record_id"),
                "状态": cell(f, "状态"),
                "达人抖音号": cell(f, "达人抖音号"),
                "粉丝数": cell(f, "粉丝数"),
                **vals,
            })

    print("")
    if not bad:
        print("✔ 没有结算额异常的行")
    else:
        print("⚠ 结算额异常（三列全 0-0 / 空）共 %d 条：" % len(bad))
        print("  %-24s %-8s %-10s %-8s %s" % (
            "达人名称", "状态", "结算总额", "粉丝数", "抖音号"))
        print("  " + "-" * 74)
        for r in bad:
            print("  %-24s %-8s %-10s %-8s %s" % (
                r["达人名称"][:22], r["状态"] or "-", r["结算总额"] or "(空)",
                r["粉丝数"] or "-", r["达人抖音号"] or "-"))
        print("")
        print("  说明：这些行是「平台筛选漏出」的历史遗留。新数据已由")
        print("       collect.py 规则2b 本地兜底拦截，不会再进来。")
        print("       处理方式（需自行确认）：在飞书表里手动删除，或保留作历史。")

    if a.json:
        os.makedirs(F.TMP, exist_ok=True)
        p = os.path.join(F.TMP, "audit.json")
        json.dump({"total": len(idx), "abnormal": bad},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  已写出 %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
