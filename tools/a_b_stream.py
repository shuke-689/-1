# -*- coding: utf-8 -*-
"""A→B 串流调度：**A 每集满 N 个微信号，立刻并入名单并跑 B 加好友（随后跑 C 登记）**。

用户 09-28 定的规则：
  「在 A 阶段降低筛选频次，逐个点开符合要求的达人，然后进行登记；
    集满 10 个微信号后，同步进行添加好友；添加好友至 30 个为止；
    但筛选不停；每天要求筛选达人 80 个做备选（个护 40 / 美妆 40）；
    剔除前期以及添加过的；筛选频次 15 秒一次。」

⚠️ **「同步」= 紧接着做，不是并行** —— A 走浏览器自动化、B 抢真实键鼠，
   **两者真并行是明令禁止的**（B 靠窗口截图读结果，被 Edge 盖住会读错）。
   所以本脚本实现为**串行流水线**：
        A 一小轮(逐个点开达人·登记) → 并入名单 → C 登记
        → 集满 10 个微信号就跑 B(当天累计封顶 30) → C
        → **立刻回到 A 继续下一轮**（"筛选不停" = 整体流程不因 B 而收工）
        直到 当天备选 80 个（个护 40 + 美妆 40）达成，或撞遮罩/连续空转。

规则 → 参数映射：
  · 每天 80 个备选、个护 40 / 美妆 40  → `--daily 80 --cat-quota "个护家清>个人护理=40,美妆>不限=40"`
  · 集满 10 个微信号就跑 B              → `--chunk 10`
  · B 添加好友至 30 个为止（当天）      → `--b-cap 30`（+ `--b-baseline` 指定今日已发基线）
  · 筛选频次 15 秒一次                  → `--daren-interval 15`（传给 collect.py 的 DAREN_MIN_INTERVAL）
  · 剔除前期及添加过的                  → 台账/名单按 uid + 联系方式去重（collect.py 与 B 各自都做）

🔴 关于「15 秒一次」的实话：这是**下限节流**，不是提速魔法。实测单个达人（开主页 +
   带货分析 + 抓微信号）在**不撞限流**时约 40 秒，其中「达人抖音主页」抓抖音号就占 ~30 秒；
   撞一次 11001 还要额外退避 90 秒（09-28 实测节奏 131 秒/人）。
   ⇒ 想真正压到接近 15 秒/人，加 `SKIP_DOUYIN_ID=1`（代价：飞书「抖音号」列留空）。

停止条件：
  · 当天各类目配额都达成；
  · 某个类目连续 2 轮 0 新微信号（且**无**限流截断标记）⇒ 判**该类目淘空** → **换下一个类目继续**；
  · 连续 3 轮命中限流截断标记 ⇒ 收工（不等限流窗口）；
  · 连续 3 轮 A **退出码 1**（运行异常，绝大多数是自动化 Edge 残留占锁）⇒ 收工；
  · A **退出码 3**（登录失效）⇒ 立即中止；
  · 全部类目都淘空 ⇒ 收工（会提示换更宽的子类目）；
  · 达到 `--max-rounds`。

🔴 **别把「限流截断」当「淘空」**（09-28 实测踩到）：`collect.py` 的截断护栏会把
   「连续 15 屏无新增且接口仅 2 条」判为限流 → **不产出名单** + 写 `out/collect/ratelimit<tag>.txt`。
   现象与"类目淘空"一模一样（都是 0 条），但处置相反：限流要停手，淘空要换类目。
   本脚本按该标记区分，并且**每轮开始会清掉旧标记**（否则上一轮的标记会被误读）。

用法：
  python tools/a_b_stream.py --dry                 # 只看现状与配置
  python tools/a_b_stream.py                       # 按默认规则跑（80/40+40/10/30/15s）
  python tools/a_b_stream.py --b-baseline 349      # 指定今日已发基线（防超发）

状态文件 `out/daily_state.json`（跨日自动重置）：记录当天各类目已采备选数、sent 起始值，
   以及"自上次 B 以来攒了几个微信号"。**中途重跑会接着算，不会重复发好友申请。**

环境变量：STREAM_DAILY / STREAM_CHUNK / STREAM_B_CAP / STREAM_B_BASELINE /
         STREAM_DAREN_INTERVAL / STREAM_MAX_ROUNDS / STREAM_CAT_QUOTA / STREAM_DRY
安全铁律（脚本已内置）：只清**自动化自己启的** Edge；B 每轮 ≤ chunk（≤10）；
         B 自带桌面体检与冻帧守卫（锁屏自动拒绝）；手机号达人由 B 默认跳过。
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
STATE = os.path.join(BASE, "out", "daily_state.json")
LOG = os.path.join(BASE, "out", "a_b_stream.log")

DEFAULT_QUOTA = "个护家清>个人护理=40,美妆>不限=40"


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


def save_json(p, obj):
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def ledger_rows():
    return load_json(LEDGER, [])


def sent_total():
    return sum(1 for r in ledger_rows() if r.get("add_status") == "sent")


def known_contacts():
    """台账里出现过的联系方式（含未完成的）——重复加没意义。"""
    return {r.get("contact") for r in ledger_rows() if r.get("contact")}


# ------------------------------------------------------------------ 当天状态
def load_state(baseline=None):
    """当天状态（跨日重置）。baseline 给了就**强制**用它当今日已发起点。"""
    today = time.strftime("%Y-%m-%d")
    st = load_json(STATE, {})
    if st.get("date") != today:
        st = {"date": today, "done": {}, "sent_start": sent_total(), "pending_wx": 0}
        log("新的一天 -> 重置当天状态（sent 起点 = %d）" % st["sent_start"])
    if baseline is not None:
        st["sent_start"] = int(baseline)
        log("（按参数强制今日已发基线 = %d）" % st["sent_start"])
    st.setdefault("done", {})
    st.setdefault("pending_wx", 0)
    return st


def save_state(st):
    save_json(STATE, st)


def sent_today(st):
    """当天已发 = 台账 sent 总数 - 当天起点（以台账为准，工具外跑的也算进来）。"""
    return max(0, sent_total() - int(st.get("sent_start", 0)))


# ------------------------------------------------------------------ 子步骤
def kill_edge():
    """只清自动化自己启的 Edge（见 tools/kill_auto_edge.py，别改成杀全量）。"""
    helper = os.path.join(BASE, "tools", "kill_auto_edge.py")
    if not os.path.exists(helper):
        log("⚠️ 未找到 tools/kill_auto_edge.py，跳过 Edge 清理（宁可不清理，也不误杀用户 Edge）")
        return
    try:
        subprocess.run([sys.executable, helper], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=180)
    except Exception as e:
        log("⚠️ 清 Edge 失败：%s" % str(e)[:80])


def parse_quota(s):
    """'个护家清>个人护理=40,美妆>不限=40' -> [(父, 子, 配额, key)]"""
    out = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        cat, _, num = item.rpartition("=")
        p, _, c = cat.partition(">")
        p, c = p.strip() or "个护家清", c.strip() or "不限"
        try:
            n = int(num)
        except Exception:
            n = 40
        out.append((p, c, n, "%s>%s" % (p, c)))
    return out or [(p, c, 40, "%s>%s" % (p, c))
                   for p, c in [("个护家清", "个人护理"), ("美妆", "不限")]]


def run_a(k, target, cate_parent, cate_child, interval):
    """跑一轮 collect.py，返回 (退出码, 本批记录, 日志路径)。"""
    tag = "_s%d" % k
    kill_edge()
    env = os.environ.copy()
    env.update({
        "CATE_PARENT": cate_parent,
        "CATE_CHILD": cate_child,
        "TARGET_DAREN": str(max(1, target)),
        "OUT_TAG": tag,
        "DAREN_MIN_INTERVAL": str(interval),
        "MAX_SCROLL": os.environ.get("STREAM_MAX_SCROLL", "150"),
        "MAX_CANDIDATE": os.environ.get("STREAM_MAX_CANDIDATE", "600"),
        "DAREN_PAUSE": os.environ.get("STREAM_DAREN_PAUSE", "1.5"),
        "LOGIN_WAIT_SEC": os.environ.get("STREAM_LOGIN_WAIT_SEC", "600"),
        "UNAUTH_LEVEL_MIN": os.environ.get("UNAUTH_LEVEL_MIN", "2"),
        "SKIP_DOUYIN_ID": os.environ.get("SKIP_DOUYIN_ID", "0"),
    })
    jp = os.path.join(OUT, "darens%s.json" % tag)
    lp = os.path.join(BASE, "out", "collect%s.log" % tag)
    # ⚠️ 必须清掉**旧的限流标记**：本脚本每跑一次 k 都从 1 开始，
    #    上一次运行留下的 ratelimit_s2.txt 会被误当成"本轮限流"（分类就错了）。
    rmp = os.path.join(OUT, "ratelimit%s.txt" % tag)
    # 🔴 删旧文件必须**容忍失败**：Windows 上偶发 WinError 32（别的进程/杀软刚碰过），
    #    09-29 实测因此**整条流水线崩掉**（PermissionError: out\collect_s2.log 正在使用）。
    #    删不掉也无所谓 —— 后面 open(...,"a") 是追加写，不影响本轮结果。
    for _p in (jp, lp, rmp):
        try:
            if os.path.exists(_p):
                os.remove(_p)
        except OSError as e:
            log("  ⚠️ 清旧文件失败（忽略，继续跑）：%s（%s）"
                % (os.path.basename(_p), e))

    t0 = time.time()
    with open(lp, "a", encoding="utf-8", errors="replace") as fh:
        rc = subprocess.call([sys.executable, os.path.join(BASE, "collect.py")],
                             cwd=BASE, env=env, stdout=fh, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    recs = load_json(jp, [])
    log("  A 第 %d 轮（%s>%s，目标 %d）：退出码 %s，耗时 %.1f 分，产出 %d 条"
        % (k, cate_parent, cate_child, target, rc, dt / 60.0, len(recs)))
    return rc, recs, lp


def mask_hits(log_path):
    try:
        return open(log_path, encoding="utf-8", errors="replace").read().count("遮罩")
    except Exception:
        return 0


def new_wechat(recs, have, base_uids):
    got, seen = [], set()
    for r in recs:
        c, uid = r.get("contact"), r.get("uid")
        if not c or r.get("contact_type") != "微信":
            continue
        if c in have or c in seen or (uid and uid in base_uids):
            continue
        got.append(r)
        seen.add(c)
    return got


def merge_batch(k):
    tag = "_s%d" % k
    src = os.path.join(OUT, "darens%s.json" % tag)
    if not os.path.exists(src):
        log("  !! 本批无产物文件（%s）-> 无可并内容" % os.path.basename(src))
        return False
    rc = subprocess.call([sys.executable, os.path.join(BASE, "tools", "merge_into_darens.py"),
                          "--from", src, "--only-with-contact"], cwd=BASE)
    log("  merge_into_darens.py 退出码 %s" % rc)
    return rc == 0


def run_b(limit, dry):
    before = sent_total()
    cmd = [sys.executable, os.path.join(BASE, "wechat_add.py"), "run", "--limit", str(limit)]
    if dry:
        cmd.append("--dry")
    t0 = time.time()
    subprocess.call(cmd, cwd=BASE, env=os.environ.copy())
    log("  B：耗时 %.1f 分，本轮 sent +%d" % ((time.time() - t0) / 60.0, sent_total() - before))
    try:
        print(open(os.path.join(BASE, "out", "wechat_add.log"),
                   encoding="utf-8", errors="replace").read().strip(), flush=True)
    except Exception:
        pass


def run_c():
    rc = subprocess.call([sys.executable, os.path.join(BASE, "feishu_sync.py")], cwd=BASE)
    log("  C：feishu_sync.py 退出码 %s" % rc)
    return rc


# ------------------------------------------------------------------ 主流程
def main():
    env = os.environ
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", type=int, default=int(env.get("STREAM_DAILY", "80")),
                    help="当天备选目标总数（默认 80）")
    ap.add_argument("--cat-quota", default=env.get("STREAM_CAT_QUOTA", DEFAULT_QUOTA),
                    help='各类目配额，逗号分隔的「父>子=个数」')
    ap.add_argument("--chunk", type=int, default=int(env.get("STREAM_CHUNK", "10")),
                    help="集满几个微信号就跑一次 B（默认 10）")
    ap.add_argument("--b-cap", type=int, default=int(env.get("STREAM_B_CAP", "30")),
                    help="B **当天**累计发出上限（默认 30）")
    ap.add_argument("--b-baseline", type=int,
                    default=(int(env["STREAM_B_BASELINE"]) if env.get("STREAM_B_BASELINE") else None),
                    help="今日已发基线（台账 sent 起点）；不传则用当天首次运行时的 sent 总数")
    ap.add_argument("--daren-interval", type=float,
                    default=float(env.get("STREAM_DAREN_INTERVAL", "15")),
                    help="筛选频次：达人之间的最小间隔秒（默认 15）")
    ap.add_argument("--max-rounds", type=int, default=int(env.get("STREAM_MAX_ROUNDS", "30")))
    ap.add_argument("--dry", action="store_true",
                    default=str(env.get("STREAM_DRY", "")).lower() in ("1", "true", "yes"))
    args = ap.parse_args()

    quotas = parse_quota(args.cat_quota)
    st = load_state(args.b_baseline)
    base_uids = {r.get("uid") for r in load_json(DARENS, []) if r.get("uid")}
    have = known_contacts()

    log("=" * 74)
    log("A→B 串流调度%s" % ("（dry 模式：只报告不执行）" if args.dry else ""))
    log("当天状态：%s | 备选进度 %s（目标共 %d）| 今日已发 %d/%d"
        % (st["date"],
           " / ".join("%s %d/%d" % (k, st["done"].get(k, 0), n) for p, c, n, k in quotas),
           args.daily, sent_today(st), args.b_cap))
    log("现状：darens.json %d 条 / 台账 %d 条（联系方式 %d 个）/ sent 累计 %d"
        % (len(load_json(DARENS, [])), len(ledger_rows()), len(have), sent_total()))
    log("规则：逐个点开达人 → 登记；集满 %d 个微信号 → 跑 B（当天上限 %d）→ C → **回 A 继续**；"
        % (args.chunk, args.b_cap))
    log("      达人节流 %.0f 秒起；最多 %d 轮；撞遮罩/连续 3 轮空转即停"
        % (args.daren_interval, args.max_rounds))
    log("=" * 74)
    if args.dry:
        return

    rounds_without_new = 0
    rate_streak = 0                 # 连续命中「列表截断」的轮数（平台限流）
    crash_streak = 0                # 连续 A 运行异常（退出码 1，多为 Edge 残留占锁）的轮数
    rc2_streak = 0                  # 连续退出码 2（筛选条件/payload 未通过）的轮数；**不等于淘空**
    empty_streak = {}               # key -> 该类目连续空转轮数（淘空判定）
    rate_hits_cat = {}              # key -> 本轮运行中该类目命中限流的次数（用于换类目轮换）
    EXHAUST_AT = 2                  # 某类目连续 2 轮 0 新号 -> 判淘空，换下一个类目
    RATE_STOP_AT = 3                # 连续 3 轮限流 -> 收工（别耗在限流窗口上）
    for k in range(1, args.max_rounds + 1):
        # ---- 选类目：只在「配额未满 且 未判淘空」的类目里挑缺口最大的 ----
        todo_cats = [(p, c, n, key) for p, c, n, key in quotas
                     if st["done"].get(key, 0) < n and empty_streak.get(key, 0) < EXHAUST_AT]
        if not todo_cats:
            left = [(key, st["done"].get(key, 0), n) for p, c, n, key in quotas
                    if st["done"].get(key, 0) < n]
            if left:
                log("所有类目都已淘空（还没到配额）：%s"
                    % " / ".join("%s %d/%d" % (x, a, b) for x, a, b in left))
                log("-> 建议换个更宽的子类目（如 个护家清>不限）或改天再采；收工")
            else:
                log("当天备选配额已全部达成 -> 收工")
            break
        # 先按「本轮该类目被限流次数」升序（避开刚被限流的类目）、再按缺口降序
        todo_cats.sort(key=lambda x: (rate_hits_cat.get(x[3], 0),
                                      -(x[2] - st["done"].get(x[3], 0))))
        p, c, quota_n, key = todo_cats[0]
        need = quota_n - st["done"].get(key, 0)
        # 本轮目标：不超过 chunk（因为攒够 chunk 个微信号就要跑 B），也不超过该类目缺口
        target = max(1, min(args.chunk, need))

        log("-" * 74)
        log("第 %d 轮：类目 %s>%s（该类目还差 %d 个）-> A 目标 %d 个微信号"
            % (k, p, c, need, target))
        rc, recs, lp = run_a(k, target, p, c, args.daren_interval)
        fresh = new_wechat(recs, have, base_uids)

        if not fresh:
            hits = mask_hits(lp)
            # ⓪ 运行异常（退出码 1）—— 09-29 实测：退出码 1 的绝大多数是**自动化 Edge 残留占锁**
            #    （现象：耗时 0.0 分 / 日志里只有 playwright 的 close 记录 / TargetClosedError
            #      +「正在现有浏览器会话中打开」；见 RUNBOOK §1.5）。
            #    🔴 绝不能当成「类目淘空」：exit 1 是**崩溃**，不是没数据 ——
            #       当淘空会白白换类目、还把配额判成满不了。这里改成清 Edge 重试。
            if rc == 1:
                crash_streak += 1
                log("  !! A 退出码 1 = 运行异常（最常见：自动化 Edge 残留占锁，见 RUNBOOK §1.5）"
                    "；连续 %d/3 轮" % crash_streak)
                if crash_streak >= 3:
                    log("  !! 连续 3 轮运行异常 -> 收工（先手动确认 Edge 与登录态，别硬耗）")
                    break
                log("  -> 重新清 Edge 后重试本类目")
                time.sleep(5)
                continue
            if rc == 3:
                log("  !! 退出码 3 = 登录失效 -> 整体中止（去 Edge 窗口登录后重跑本脚本）")
                break
            if rc == 2:
                # 🔴 09-30 实测补丁：退出码 2 = 平台筛选条件/payload 校验没过
                #    （见 RUNBOOK §1.6：冷却 45s 重试）。**绝不能**当「类目淘空」——
                #    上午实测：个护轮一次 rc=2 就被记成 empty_streak 1/2，
                #    再撞一次就会把好好的类目误判淘空、白换类目。
                rc2_streak += 1
                log("  !! A 退出码 2 = 平台筛选条件/payload 未通过（**不是**类目淘空）"
                    "-> 冷却 45 秒重试本类目；连续 %d/3" % rc2_streak)
                if rc2_streak >= 3:
                    log("  !! 连续 3 轮退出码 2 -> 收工（先人工复核平台筛选条件是否被平台改名/改动）")
                    break
                time.sleep(45)
                continue
            rc2_streak = 0
            crash_streak = 0
            # 🔴 先分清「平台限流截断」还是「这个类目真淘空了」—— 09-28 实测踩过：
            #    截断护栏命中时 collect.py 会写 ratelimit<tag>.txt 并且**不产出名单**，
            #    现象与"淘空"一样（都是 0 条），但处置完全不同（限流要停手，淘空要换类目）。
            rl_mark = os.path.exists(os.path.join(OUT, "ratelimit_s%d.txt" % k))
            if rl_mark:
                rate_streak += 1
                rate_hits_cat[key] = rate_hits_cat.get(key, 0) + 1
                log("  !! 本轮命中**列表截断护栏**（out/collect/ratelimit_s%d.txt）"
                    "-> 平台限流，本批不产出（注意：**不是**候选池淘空）" % k)
                log("     按铁律**不等限流窗口**；连续 %d/%d 轮限流" % (rate_streak, RATE_STOP_AT))
                if rate_streak >= RATE_STOP_AT:
                    log("  !! 连续 %d 轮被限流 -> 收工（改天或等限流过去再跑，状态会接着算）" % rate_streak)
                    break
                log("  -> 换下一个类目试（不同类目的列表请求可能不受同一波限流影响）")
                continue
            rate_streak = 0
            empty_streak[key] = empty_streak.get(key, 0) + 1
            rounds_without_new += 1
            log("  !! 本轮**新微信号 0 个**（产出 %d 条；无截断标记 => 判**该类目淘空**；"
                "日志「遮罩」%d 次；该类目连续空转 %d/%d）"
                % (len(recs), hits, empty_streak[key], EXHAUST_AT))
            if hits >= 3:
                log("  !! 日志成片「遮罩」-> **先查 MASK_SKIP，别急着判账号限权**（09-28 已两次证伪）：")
                log("     小样本复核：MASK_SKIP=0 TARGET_DAREN=6 OUT_TAG=_probe MAX_SCROLL=60 \"$PY\" collect.py")
                log("     · 出现「联系=微信」= 一切正常，直接重跑本脚本（状态会接着算）")
                log("     · 仍取不到值 -> 看日志「有「达人微信号」行但没找到眼睛图标」= wechat_icon 定位坏了")
                break
            if empty_streak[key] >= EXHAUST_AT:
                log("  -> 类目 %s **判为淘空**（%d 轮 0 新号）-> 换下一个类目继续" % (key, EXHAUST_AT))
            continue
        rounds_without_new = 0
        rate_streak = 0
        crash_streak = 0
        rc2_streak = 0
        empty_streak[key] = 0

        log("  A 本轮出**新微信号 %d 个**%s" % (
            len(fresh), "（达本轮目标）" if len(fresh) >= target else "（不足目标 %d）" % target))
        for r in fresh:
            log("     + %s | %s" % (r.get("nickname"), r.get("contact")))

        # 立刻并入正式名单（长跑被杀的教训：到手就先钉住）+ 更新当天进度
        if merge_batch(k):
            base_uids |= {r.get("uid") for r in fresh if r.get("uid")}
            have |= {r.get("contact") for r in fresh if r.get("contact")}
        st["done"][key] = st["done"].get(key, 0) + len(fresh)
        st["pending_wx"] = st.get("pending_wx", 0) + len(fresh)
        save_state(st)

        # 取到就登记一次（用户：「点开符合要求的达人，然后进行登记」）
        run_c()

        # ---- 集满 chunk 个微信号 -> 跑 B（当天封顶 b_cap）----
        room = args.b_cap - sent_today(st)
        if st["pending_wx"] >= args.chunk and room > 0:
            limit = min(args.chunk, room)
            log("  已集满 %d 个微信号 -> 跑 B（本次最多 %d 个；当天还剩 %d 个额度）"
                % (st["pending_wx"], limit, room))
            run_b(limit, args.dry)
            run_c()
            st["pending_wx"] = 0
            save_state(st)
        else:
            log("  （已攒 %d/%d 个微信号；当天 B 额度还剩 %d）-> 回 A 继续筛选"
                % (st["pending_wx"], args.chunk, max(0, room)))

        if sent_today(st) >= args.b_cap:
            log("  当天添加好友已达上限 %d 个 -> 后续只筛选不加好友" % args.b_cap)

    log("=" * 74)
    log("调度结束：备选进度 %s | 今日已发 %d/%d | 台账 sent 累计 %d"
        % (" / ".join("%s %d/%d" % (k, st["done"].get(k, 0), n) for p, c, n, k in quotas),
           sent_today(st), args.b_cap, sent_total()))
    log("👉 继续跑：解锁屏幕 + 微信「添加朋友」窗口可见后，重跑本脚本即可（状态存在 %s）"
        % os.path.relpath(STATE, BASE))
    log("   抖音号若留空（SKIP_DOUYIN_ID=1 跑的），可事后补：删掉对应 douyin_id 重跑 A 或用 douyin_id.py 单独补")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("!! 收到中断（Ctrl+C / 被杀）-> 退出")
        raise
    except Exception:
        # 🔴 09-29 教训：本脚本曾以退出码 1 **无声退出**（日志里连 traceback 都没有，
        #    只剩下一轮开头），排查全靠猜。这里强制把堆栈落进日志，别再"静默死亡"。
        import traceback
        tb = traceback.format_exc()
        try:
            log("!! a_b_stream 异常退出（退出码 1）：\n%s" % tb)
        except Exception:
            pass
        sys.stderr.write("!! a_b_stream 异常退出（退出码 1）：\n%s\n" % tb)
        sys.stderr.flush()
        raise
