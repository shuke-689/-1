# -*- coding: utf-8 -*-
"""阶段B「加到 N 个为止」驱动（2026-09-21 新增）。

为什么要它：`tools/run_b_rounds.sh` 是「固定 limit × 固定轮数」，
差 1 个时若给 `--limit 4`，那一轮 4 个全成 → **当日多发 3 个**
（RUNBOOK §3.9 ② 的实测事故）。

本驱动每轮**按「目标 − 今日已发」动态算 limit**（并封顶 `--max-per-round`）：
    今日已发 = 台账 sent 总数 − 开跑前基线
达标即停，绝不超发；差 1 个就只给 1 个。

用法:
  python tools/run_b_to_target.py --target 50                # 基线自动取当前 sent
  python tools/run_b_to_target.py --target 50 --baseline 236 # 显式指定今日基线
  python tools/run_b_to_target.py --target 50 --dry          # 只算不跑
环境变量: BT_TARGET / BT_BASELINE / BT_MAX_PER_ROUND / BT_GAP / BT_MAX_ROUNDS

⚠️ 前置（脚本**不检查也不准备**）：
   微信已登录；「添加朋友」窗口已打开且未被遮挡；全程勿动鼠标键盘。
⚠️ **绝不能与阶段A 采集并行**（B 靠桌面区域截图，A 会把 Edge 拉到最前 →
   误判 risk_control 整轮中止 / 误判 not_found 永久跳过）。见 RUNBOOK §3.2。
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LED = os.path.join(BASE, "out", "wechat", "add_results.json")
LOG = os.path.join(BASE, "out", "wechat_add_rounds.log")
PY = sys.executable


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_ledger():
    try:
        with open(LED, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def stat():
    led = read_ledger()
    vals = led.values() if isinstance(led, dict) else led
    cnt = {}
    for v in vals:
        if isinstance(v, dict):
            k = v.get("add_status") or "?"
            cnt[k] = cnt.get(k, 0) + 1
    return cnt


def sent_total():
    return stat().get("sent", 0)


def close_stale_apply_windows():
    """关掉遗留的「申请添加朋友」窗口（rect 0x0 会让整轮报 cannot write empty image）。

    RUNBOOK §3.9 ① ：必须 PostMessage(WM_CLOSE)，且校验 rect 时**要传 hwnd**。
    """
    n = 0
    try:
        sys.path.insert(0, os.path.join(BASE, ".probe"))
        import win_io
        for w in win_io.list_windows():
            t = str(w.get("title") or "")
            if "申请添加朋友" in t:
                try:
                    ctypes.windll.user32.PostMessageW(w["hwnd"], 0x0010, 0, 0)
                    n += 1
                except Exception:
                    pass
    except Exception as e:
        log("  ! 清残留申请页失败：%s" % e)
    if n:
        log("  已关闭遗留「申请添加朋友」窗口 %d 个" % n)
    return n


def one_round(limit):
    cmd = [PY, "wechat_add.py", "run", "--limit", str(limit)]
    p = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    for ln in out.splitlines():
        print("[run] " + ln, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(out if out.endswith("\n") else out + "\n")
    except Exception:
        pass
    return p.returncode, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=int(os.environ.get("BT_TARGET", "50")))
    ap.add_argument("--baseline", type=int, default=None,
                    help="今日基线（开跑前的 sent 总数）；不传则取当前值")
    ap.add_argument("--max-per-round", type=int,
                    default=int(os.environ.get("BT_MAX_PER_ROUND", "10")))
    ap.add_argument("--gap", type=int, default=int(os.environ.get("BT_GAP", "60")))
    ap.add_argument("--max-rounds", type=int,
                    default=int(os.environ.get("BT_MAX_ROUNDS", "30")))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    base_sent = sent_total()
    baseline = a.baseline if a.baseline is not None else base_sent
    log("=" * 66)
    log("阶段B「加到 %d 个为止」/ 今日基线 sent=%d / 当前 sent=%d / 每轮≤%d 个"
        % (a.target, baseline, base_sent, a.max_per_round))
    log("台账状态分布: %s" % stat())
    log("=" * 66)
    if a.dry:
        log("[dry] 只计算，不执行")
        return 0

    done = base_sent - baseline
    rounds = 0
    while rounds < a.max_rounds:
        need = a.target - done
        if need <= 0:
            log("★ 今日已发 %d 个，达到目标 %d -> 停止" % (done, a.target))
            break
        limit = min(a.max_per_round, need)
        rounds += 1
        log("---------- 第 %d 轮：还差 %d 个，本轮 limit=%d ----------" % (rounds, need, limit))

        before = sent_total()
        rc, out = one_round(limit)
        after = sent_total()
        gained = after - before
        done = after - baseline

        if "检测到微信风控" in out:
            log("!!! 检测到微信风控 -> 立即停止（今日已发 %d 个）" % done)
            return 2
        if re.search(r"找不到.*添加朋友", out):
            log("!!! 找不到「添加朋友」窗口 -> 请先打开它再重跑")
            return 3
        if "没有待加好友了" in out or "剩余待加 0 个" in out:
            log("--- 候选池已加完 -> 停止（今日已发 %d 个，未达目标 %d）" % (done, a.target))
            return 0
        log("第 %d 轮结束：本轮发出 %d 个，今日累计 %d/%d" % (rounds, gained, done, a.target))

        if gained == 0:
            # §3.9 ①：整轮 0 成功且报 empty image / error = 残留申请页挡住截图
            if "empty image" in out or "无法" in out and "error" in out.lower():
                close_stale_apply_windows()
        if need - gained > 0 and rounds < a.max_rounds:
            log("%ds 后进入下一轮" % a.gap)
            time.sleep(a.gap)

    log("=" * 66)
    log("阶段B 收尾：今日发出 %d 个（目标 %d）/ 台账 sent 总数 %d / 分布 %s"
        % (done, a.target, sent_total(), stat()))
    log("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
