# -*- coding: utf-8 -*-
"""把「已经筛选的达人」登记到飞书多维表格（用户 2026-09-17 要求）。

用户要求：**每次跑完 A 阶段及 B 阶段后**，把达人信息登记到
    https://ecnu9txhl35c.feishu.cn/base/DgCobcJykajunKsMcUXcZdOnnXd
表：`达人统计`（tblHE06hIkZxnafa）
列：达人名称 / 达人抖音号 / 粉丝数 / 结算总额 / 直播结算总额 / 短视频结算总额 / 状态

数据来源（全部本地，不发任何额外请求）：
  out/collect/darens.json         —— A 阶段产出（含 contacts / 结算区间 / 抖音号）
  out/wechat/add_results.json     —— B 阶段台账（add_status 决定「状态」列）

状态映射（用户只要两种值，不解释原因）：
    sent（已发申请）      -> 已申请
    already（已是好友）    -> 已申请
    not_found（搜不到）    -> 添加失败
    excluded（命中排除词）  -> 添加失败
    error / risk_control  -> **留空**（属临时态，下轮 B 会重试，不留误判）
    台账里没有            -> **留空**（A 刚跑完、B 还没跑）

幂等：以「达人名称」为键，已存在的记录走 update（只更新有值的列），不存在才 create。
所以 A 跑完先登记一遍、B 跑完再跑一遍，不会产生重复行。

用法：
    "$PY" feishu_sync.py                 # 登记/更新（默认只登记有效达人）
    "$PY" feishu_sync.py --dry           # 只打印将要写什么，不落库
    "$PY" feishu_sync.py --all           # 连未取到联系方式的也登记（一般不用）
    "$PY" feishu_sync.py --limit 5       # 只处理前 N 个（试跑）
"""
import argparse
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import nick_rules  # noqa: E402  规则7 词表（与 A / B 阶段共用，无副作用模块）

OUT = os.path.join(BASE, "out", "collect")
LEDGER = os.path.join(BASE, "out", "wechat", "add_results.json")
TMP = os.path.join(BASE, "out", "feishu")
os.makedirs(TMP, exist_ok=True)

DEFAULT_BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "DgCobcJykajunKsMcUXcZdOnnXd")
DEFAULT_TABLE_ID = os.environ.get("FEISHU_TABLE_ID", "tblHE06hIkZxnafa")

# 台账 add_status -> 飞书「状态」列取值
STATUS_MAP = {
    "sent": "已申请",
    "already": "已申请",
    "not_found": "添加失败",
    "excluded": "添加失败",
    # error / risk_control -> 不映射（留空，下轮重试）
}

# 需要确保存在的字段（幂等创建）
REQUIRED_FIELDS = [
    {"name": "达人抖音号", "type": "text"},
    {"name": "结算总额", "type": "text"},
    {"name": "直播结算总额", "type": "text"},
    {"name": "短视频结算总额", "type": "text"},
    {"name": "状态", "type": "select", "multiple": False,
     "options": [{"name": "已申请", "hue": "Green", "lightness": "Lighter"},
                 {"name": "添加失败", "hue": "Red", "lightness": "Lighter"}]},
]


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# ---- 调 lark-cli --------------------------------------------------------
# ⚠️ Windows 上不要直接 subprocess(["lark-cli", ...])：
#    `lark-cli` 只是个 shell 脚本，真正入口是
#      <pkg>/node_modules/@larksuite/cli/scripts/run.js
#    直接起 `lark-cli` 会 WinError 2；而走 `cmd /c lark-cli.cmd` 又会被
#    cmd 的引号规则把 JSON 参数搅坏。所以这里**直接 node + run.js**。
_PKG = os.environ.get("LARK_CLI_PKG") or os.path.join(
    os.path.expanduser("~"), ".workbuddy", "binaries", "node", "cli-connector-packages")
_RUNJS = os.path.join(_PKG, "node_modules", "@larksuite", "cli", "scripts", "run.js")


def _node_exe():
    cands = [os.environ.get("LARK_CLI_NODE"),
             os.path.join(_PKG, "node.exe"),
             shutil.which("node")]
    cands += sorted(glob.glob(os.path.join(
        os.path.expanduser("~"), ".workbuddy", "binaries", "node",
        "versions", "*", "node.exe")), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def lark(args, timeout=120):
    """调 lark-cli，返回 (ok, parsed_json_or_text)。"""
    node = _node_exe()
    if not node or not os.path.exists(_RUNJS):
        return False, "找不到 node(%s) 或 run.js(%s)" % (node, _RUNJS)
    cmd = [node, _RUNJS] + args + ["--as", "user"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except Exception as e:
        return False, "运行失败: %s" % str(e)[:150]
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        return False, "rc=%d %s %s" % (p.returncode, out[:200], (p.stderr or "")[:200])
    try:
        return True, json.loads(out)
    except Exception:
        return True, out


def fmt_range(d):
    """{'low':x,'high':y} -> 'x-y'；与 darens_io.fmt_range 保持一致。"""
    if not isinstance(d, dict):
        return ""
    lo, hi = d.get("low"), d.get("high")
    if lo is None and hi is None:
        return ""
    return "%s-%s" % (lo if lo is not None else "", hi if hi is not None else "")


def ensure_fields(bt, tid):
    """缺的字段补上（已存在就跳过）。"""
    ok, res = lark(["base", "+field-list", "--base-token", bt, "--table-id", tid])
    if not ok:
        log("  ! 读字段失败：%s" % str(res)[:160])
        return False
    have = set()
    try:
        for f in res["data"]["fields"]:
            have.add(f["name"])
    except Exception:
        return False
    missing = [f for f in REQUIRED_FIELDS if f["name"] not in have]
    if not missing:
        log("  字段齐备（%d 个）" % len(have))
        return True
    log("  缺 %d 个字段，正在创建: %s" % (len(missing), "/".join(f["name"] for f in missing)))
    ok2, res2 = lark(["base", "+field-create", "--base-token", bt, "--table-id", tid,
                      "--json", json.dumps(missing, ensure_ascii=False)])
    if not ok2:
        log("  ! 建字段失败：%s" % str(res2)[:200])
        return False
    log("  字段创建成功")
    return True


def fetch_existing(bt, tid):
    """读回已有记录，返回 {达人名称: {record_id, fields}}。

    ⚠️ 两个坑（都踩过）：
      1. ndjson 里字段是**平铺在顶层**的（`{"record_id":..,"达人名称":..}`），
         **不是**嵌在 `fields` 下 —— 按 `r["fields"]` 取会一条都读不到（曾静默返回 0 条）。
      2. `--output` 指向的文件已存在时 lark-cli 会报 failed_precondition，必须 `--overwrite`。
    """
    nd = os.path.join(TMP, "existing.ndjson")
    try:
        if os.path.exists(nd):
            os.remove(nd)
    except Exception:
        pass
    ok, res = lark(["base", "+record-list", "--base-token", bt, "--table-id", tid,
                    "--limit", "2000", "--format", "ndjson", "--output", nd,
                    "--overwrite"])
    if not ok:
        log("  ! 读记录失败：%s" % str(res)[:200])
        return None
    idx = {}
    if not os.path.exists(nd):
        log("  ! 没拿到 ndjson（%s）" % nd)
        return idx
    with open(nd, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            flat = dict(r)
            nest = r.get("fields") if isinstance(r.get("fields"), dict) else {}
            name = flat.get("达人名称") or nest.get("达人名称")
            if isinstance(name, list):
                name = name[0] if name else None
            if name:
                idx[str(name).strip()] = {"record_id": r.get("record_id"),
                                          "fields": {**nest, **flat}}
    return idx


def build_rows(recs, ledger, all_rec, limit, keep_excluded=False):
    """把 darens.json + 台账 组装成飞书记录。返回 (rows, stats)。

    `keep_excluded=False`（默认）时**跳过昵称命中排除词的达人** ——
    规则是会长大的（2026-09-17 追加了 13 个词），旧名单不会自动重筛，
    而被跳过的达人本来就不该出现在登记表里。要连它们一起登记用 `--include-excluded`。
    """
    rows = []
    stat = {"total": 0, "no_contact": 0, "已申请": 0, "添加失败": 0, "空": 0,
            "无抖音号": 0, "昵称排除": 0}
    for r in recs:
        stat["total"] += 1
        if not all_rec and not r.get("contact"):
            stat["no_contact"] += 1
            continue
        name = (r.get("nickname") or "").strip()
        if not name:
            continue
        if not keep_excluded and nick_rules.nick_exclude_reason(name):
            stat["昵称排除"] += 1
            continue
        st = (ledger.get(r.get("uid")) or {}).get("add_status") or ""
        f = {
            "达人名称": name,
            "达人抖音号": r.get("douyin_id") or "",
            "结算总额": fmt_range(r.get("settle_total")),
            "直播结算总额": fmt_range(r.get("settle_live")),
            "短视频结算总额": fmt_range(r.get("settle_video")),
            "所属平台": ["抖音"],
        }
        if r.get("fans") is not None:
            try:
                f["粉丝数"] = int(r["fans"])
            except Exception:
                pass
        label = STATUS_MAP.get(st)
        if label:
            f["状态"] = [label]
        stat[label or "空"] = stat.get(label or "空", 0) + 1
        if not f["达人抖音号"]:
            stat["无抖音号"] += 1
        rows.append(f)
        if limit and len(rows) >= limit:
            break
    return rows, stat


def push(bt, tid, rows, existing, dry):
    """按「达人名称」diff 出 create / update 并提交。"""
    creates, updates = [], []
    for f in rows:
        name = f["达人名称"]
        old = existing.get(name)
        if not old:
            creates.append(f)
            continue
        # 只提交有值的列（避免把已有内容清空）
        src = dict(f)
        src.pop("达人名称", None)
        delta = {}
        oldf = old.get("fields") or {}
        for k, v in src.items():
            if v in ("", None, []):
                continue
            cur = oldf.get(k)
            if isinstance(cur, list) and cur and isinstance(cur[0], dict):
                cur = cur[0].get("text") or cur[0].get("name") or ""
            if k in ("粉丝数",) and cur is not None:
                try:
                    if int(cur) == int(v):
                        continue
                except Exception:
                    pass
            if str(cur or "") == str(v):
                continue
            delta[k] = v
        if delta:
            updates.append((old.get("record_id"), delta))

    log("  待新增 %d 条 / 待更新 %d 条" % (len(creates), len(updates)))
    if dry:
        for f in creates[:5]:
            log("    + %s" % json.dumps(f, ensure_ascii=False))
        for rid, d in updates[:5]:
            log("    ~ %s %s" % (rid, json.dumps(d, ensure_ascii=False)))
        log("  （--dry 模式，未落库）")
        return len(creates), len(updates), 0

    okn = 0
    for i in range(0, len(creates), 200):
        chunk = creates[i:i + 200]
        p = os.path.join(TMP, "create_%d.json" % i)
        json.dump({"create_records": chunk}, open(p, "w", encoding="utf-8"),
                  ensure_ascii=False)
        ok, res = lark(["base", "+record-batch-create", "--base-token", bt,
                        "--table-id", tid, "--json", "@" + p], timeout=180)
        log("    新增第 %d 批(%d 条)：%s" % (i // 200 + 1, len(chunk),
                                          "OK" if ok else str(res)[:160]))
        if ok:
            okn += len(chunk)
        time.sleep(0.6)

    okm = 0
    for i in range(0, len(updates), 200):
        chunk = updates[i:i + 200]
        p = os.path.join(TMP, "update_%d.json" % i)
        json.dump({"update_records": {rid: d for rid, d in chunk}},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)
        ok, res = lark(["base", "+record-batch-update", "--base-token", bt,
                        "--table-id", tid, "--json", "@" + p], timeout=180)
        log("    更新第 %d 批(%d 条)：%s" % (i // 200 + 1, len(chunk),
                                          "OK" if ok else str(res)[:160]))
        if ok:
            okm += len(chunk)
        time.sleep(0.6)
    return len(creates), len(updates), okn + okm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-token", default=DEFAULT_BASE_TOKEN)
    ap.add_argument("--table-id", default=DEFAULT_TABLE_ID)
    ap.add_argument("--all", action="store_true", help="连未取到联系方式的也登记")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--include-excluded", action="store_true",
                    help="连昵称命中规则7排除词的也登记（一般不用）")
    a = ap.parse_args()

    dpath = os.path.join(OUT, "darens.json")
    if not os.path.exists(dpath):
        log("!! 找不到 %s —— 先跑完 A 阶段" % dpath)
        sys.exit(1)
    recs = json.load(open(dpath, encoding="utf-8"))
    ledger = {}
    if os.path.exists(LEDGER):
        # 台账是**记录列表**（每条含 uid / add_status），不是 {uid: {...}} 字典
        raw = json.load(open(LEDGER, encoding="utf-8"))
        if isinstance(raw, dict):
            ledger = raw
        else:
            for x in (raw or []):
                if isinstance(x, dict) and x.get("uid"):
                    ledger[x["uid"]] = x
    log("darens.json %d 条 / 台账 %d 条" % (len(recs), len(ledger)))

    rows, stat = build_rows(recs, ledger, a.all, a.limit, a.include_excluded)
    log("将登记 %d 条（有效 %d；状态：已申请 %d、添加失败 %d、留空 %d；"
        "无抖音号 %d；昵称命中排除词跳过 %d）" % (
            len(rows), stat["total"] - stat["no_contact"], stat.get("已申请", 0),
            stat.get("添加失败", 0), stat.get("空", 0), stat["无抖音号"],
            stat.get("昵称排除", 0)))
    if not rows:
        log("没有可登记的行，结束")
        return

    log("目标 Base=%s Table=%s" % (a.base_token, a.table_id))
    if not ensure_fields(a.base_token, a.table_id):
        log("!! 字段准备失败，中止（避免写坏表结构）")
        sys.exit(2)
    existing = fetch_existing(a.base_token, a.table_id)
    if existing is None:
        log("!! 读已有记录失败，中止（避免写出重复行）")
        sys.exit(3)
    log("  表内已有 %d 条记录" % len(existing))

    c, u, n = push(a.base_token, a.table_id, rows, existing, a.dry)
    log("完成：新增 %d / 更新 %d / 实际成功 %d" % (c, u, n))


if __name__ == "__main__":
    main()
