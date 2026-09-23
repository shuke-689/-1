# -*- coding: utf-8 -*-
"""多轮累积采集：反复跑 collect.py，把「台账里还没有的、有微信号的」达人攒够 N 个。

为什么需要它（2026-09-18 实测）：
  平台侧本地过滤（规则4 类目把关）后每轮保留的候选数**波动极大**
  （同一套筛选：15:01 那轮保留 127 个；17:19 那轮只保留 5 个），
  说明接口返回的**排序/切片在两次会话之间会变**。
  所以要凑够一批候选，只能**多轮反复采集**，每轮取「新增」的那部分。

  另外：`collect.py` 里的 TARGET_DAREN 是「累计有效数」，每轮都从候选列表顶部
  重新走一遍，所以重复跑会**重复采到已处理过的达人** —— 本驱动按
  「contact 不在台账里」来去重，重复的自动丢弃，不会重复加好友。

用法：
  python tools/collect_more.py                 # 攒够 25 个新的（默认）
  python tools/collect_more.py --target 20 --rounds 8
  python tools/collect_more.py --dry           # 只看台账/名单现状，不采集

环境变量（不传参数时生效）：
  MORE_TARGET_NEW  要攒够多少个「新微信号达人」（默认 25）
  MORE_ROUNDS      最多跑几轮 collect.py（默认 8）
  MORE_TARGET_DAREN 每轮给 collect.py 的 TARGET_DAREN（默认 62）
  MORE_ROUND_GAP   轮间冷却秒数（默认 20；平台限流时自动退避）
  MORE_RATE_WAIT   命中限流（本轮 0 产出）后的退避秒数（默认 120）

产出：
  out/collect/darens.json（把新达人**并入**原名单，按 uid 去重后重写）
  out/collect_more.log（本驱动的日志）
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out", "collect")
LEDGER = os.path.join(BASE, "out", "wechat", "add_results.json")
DARENS = os.path.join(OUT, "darens.json")
LOG = os.path.join(BASE, "out", "collect_more.log")

os.makedirs(OUT, exist_ok=True)


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(p, default):
    if not os.path.exists(p):
        return default
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as e:
        log("!! 读 %s 失败：%s（按空处理）" % (os.path.basename(p), e))
        return default


def known_contacts():
    """台账里出现过的联系方式（含未完成的）——重复加没意义。"""
    led = load_json(LEDGER, [])
    return {r.get("contact") for r in led if r.get("contact")}


def kill_edge():
    """杀掉**自动化残留**的 msedge（命令行含 `.edge-auto`），等它归零。

    为什么每轮都要做（2026-09-19 血泪）：
      Playwright 用 launch_persistent_context 启的 msedge，在 python 被强杀后
      **不会**跟着退出，会一直占着 .edge-auto/profile 的单例锁。
      下一轮 collect.py 启动就会秒失败：
        TargetClosedError + 「正在现有浏览器会话中打开」
      现象是「退出码 1 / 耗时 0.0 分 / 日志空白」，极易被误判成平台限流 11001。

    三个必须记住的点：
      * 🔴 **只杀命令行含 `.edge-auto` 的 PID**（安全铁律 #4）—— 别用 `/IM msedge.exe`，
        那会连**用户自己的 Edge** 一起杀（2026-09-23 实测：本机 14 个 msedge 全是
        用户自己的、自动化残留 0 个，旧代码等于每轮群灭一次用户的浏览器）。
      * taskkill/tasklist 必须用**单斜杠**；写 `//F` 会被当成无效参数而静默失败。
      * 杀完要**立刻**启动，不能等 —— 实测约 15 秒后 Edge 会自己带会话重启，
        又占住 profile。所以这里只轮询到归零（约 1-3 秒）就返回。

    实现收敛在 `tools/kill_auto_edge.py`（bash 侧的 tools/kill_edge.sh 也调它），
    避免「两处实现漂移」——本函数只做转调 + 兜底。
    """
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "kill_auto_edge.py")
    if os.path.exists(helper):
        try:
            subprocess.run([sys.executable, helper],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=180)
            return
        except Exception:
            pass
    # 兜底：helper 不可用时至少不要杀到用户自己的 Edge
    print("[kill_edge] ⚠️ 未找到 tools/kill_auto_edge.py，跳过清理（宁可不清理，也不误杀用户 Edge）")


def run_pass(idx, target_daren):
    """跑一轮 collect.py，返回该轮产出的 records。"""
    tag = "_more%d" % idx
    kill_edge()
    env = os.environ.copy()
    env.update({
        "CATE_PARENT": os.environ.get("CATE_PARENT", "个护家清"),
        "CATE_CHILD": os.environ.get("CATE_CHILD", "个人护理"),
        "TARGET_DAREN": str(target_daren),
        "OUT_TAG": tag,
        "MAX_SCROLL": os.environ.get("MAX_SCROLL", "150"),
        "MAX_CANDIDATE": os.environ.get("MAX_CANDIDATE", "600"),
        "DAREN_PAUSE": os.environ.get("DAREN_PAUSE", "1.5"),
        "LOGIN_WAIT_SEC": os.environ.get("LOGIN_WAIT_SEC", "600"),
        # 筛选口径透传（2026-09-22：平台侧固定 主推类目级联 + 内容类型 + 结算额；
        # 分支 Z / FILTER_PROFILE 已整体删除）
        "UNAUTH_LEVEL_MIN": os.environ.get("UNAUTH_LEVEL_MIN", "2"),
    })
    jp = os.path.join(OUT, "darens%s.json" % tag)
    if os.path.exists(jp):
        os.remove(jp)
    t0 = time.time()
    rc = subprocess.call([sys.executable, os.path.join(BASE, "collect.py")],
                         cwd=BASE, env=env)
    dt = time.time() - t0
    recs = load_json(jp, [])
    log("  第 %d 轮：退出码 %s，耗时 %.1f 分，产出 %d 条" % (idx, rc, dt / 60.0, len(recs)))
    return rc, recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int,
                    default=int(os.environ.get("MORE_TARGET_NEW", "25")),
                    help="要攒够多少个新的「有微信联系方式」达人")
    ap.add_argument("--rounds", type=int,
                    default=int(os.environ.get("MORE_ROUNDS", "8")))
    ap.add_argument("--target-daren", type=int,
                    default=int(os.environ.get("MORE_TARGET_DAREN", "62")))
    ap.add_argument("--gap", type=int,
                    default=int(os.environ.get("MORE_ROUND_GAP", "20")))
    ap.add_argument("--rate-wait", type=int,
                    default=int(os.environ.get("MORE_RATE_WAIT", "120")))
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    base_recs = load_json(DARENS, [])
    base_uids = {r.get("uid") for r in base_recs if r.get("uid")}
    have = known_contacts()
    log("=" * 70)
    log("现状：darens.json %d 条（uid %d 个）/ 台账联系方式 %d 个"
        % (len(base_recs), len(base_uids), len(have)))
    log("目标：攒够 %d 个新的有微信联系方式的达人（最多 %d 轮，每轮 TARGET_DAREN=%d）"
        % (args.target, args.rounds, args.target_daren))
    log("筛选口径：平台侧 = 主推类目(%s>%s) + 内容类型 + %s"
        % (os.environ.get("CATE_PARENT", "个护家清"),
           os.environ.get("CATE_CHILD", "个人护理"),
           os.environ.get("SALE_LABEL", "直播结算总额")))
    log("=" * 70)
    if args.dry:
        return

    picked = []          # 本轮攒到的新达人
    picked_contacts = set()
    rounds_without_new = 0

    for i in range(1, args.rounds + 1):
        if i > 1:
            log("轮间冷却 %d 秒…" % args.gap)
            time.sleep(args.gap)
        rc, recs = run_pass(i, args.target_daren)

        new_here = []
        for r in recs:
            c = r.get("contact")
            uid = r.get("uid")
            if not c or r.get("contact_type") != "微信":
                continue
            if c in have or c in picked_contacts or (uid and uid in base_uids):
                continue
            new_here.append(r)
            picked_contacts.add(c)
        for r in new_here:
            picked.append(r)

        log("  本轮新增可用（有微信·未处理过）：%d 个；累计 %d/%d"
            % (len(new_here), len(picked), args.target))
        for r in new_here:
            log("     + %s | %s" % (r.get("nickname"), r.get("contact")))

        if len(picked) >= args.target:
            log("已攒够目标 %d 个 -> 停止采集" % args.target)
            break

        if not recs:
            rounds_without_new += 1
            log("  本轮 0 产出（很可能平台限流）-> 退避 %d 秒" % args.rate_wait)
            time.sleep(args.rate_wait)
        elif not new_here:
            rounds_without_new += 1
            if rounds_without_new >= 3:
                log("连续 %d 轮没有新增 -> 平台候选切片已遍历完，停止" % rounds_without_new)
                break
        else:
            rounds_without_new = 0

    if not picked:
        log("!! 没有攒到任何新达人 -> 不覆盖已有正式名单")
        return

    merged, seen = [], set()
    for r in base_recs + picked:
        uid = r.get("uid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        merged.append(r)

    sys.path.insert(0, BASE)
    import darens_io
    darens_io.write_outputs(merged, OUT, "", log=log)
    okw = sum(1 for r in merged
              if r.get("contact") and r.get("contact_type") == "微信"
              and r.get("contact") not in have)
    log("=" * 70)
    log("合并写回 darens.json：%d 条（原 %d + 新 %d）" % (len(merged), len(base_recs), len(picked)))
    log("其中「有微信且台账里没有的」= %d 个 -> 可以直接跑阶段B" % okw)
    log("👉 下一步：python wechat_add.py status  然后  tools/run_b_rounds.sh 10 30 60")
    log("结束")


if __name__ == "__main__":
    main()
