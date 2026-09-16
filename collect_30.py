# -*- coding: utf-8 -*-
"""双类目采集驱动：15 个「个护家清」 + 15 个「美妆」，合并成一份名单。

为什么分两批：
  精选联盟的「主推类目」筛选是级联选择，一次只能选一个大类；
  按类目分批跑 collect.py（每批独立设 TARGET_DAREN=15），最后按 uid 去重合并。

限流（重要）：
  抖音精进联盟的 square_pc_api 请求过密会返回
      {"code":11001,"msg":"请求过于频繁，请稍后再试"}
  此时列表会渲染成「未找到相关达人」，看起来像"该类目没数据"，其实是**被限流**。
  踩过：个护家清批次跑完后紧接着跑美妆批次，美妆直接拿 0 个。
  对策：① 每批之间强制冷却 BATCH_COOLDOWN 秒（默认 300）；
        ② collect.py 命中限流会写 out/collect/ratelimit_<tag>.txt，
           本驱动读到标记就冷却后重试该批（最多 MAX_RETRY 次）。

用法：
  python collect_30.py
环境变量：
  GHQ_TARGET  个护家清目标数（默认 15）
  MZ_TARGET   美妆目标数（默认 15）
  BATCH_COOLDOWN  批次间冷却秒数（默认 300）
  MAX_RETRY       单批限流重试次数（默认 3）
  MAX_SCROLL / MAX_CANDIDATE / SAME_BRAND_RATIO / DAREN_PAUSE 透传给 collect.py
"""
import io
import json
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "collect")
LOG = os.path.join(BASE, "out", "collect_30.log")
os.makedirs(OUT, exist_ok=True)

JOBS = [
    ("个护家清", "ghq", int(os.environ.get("GHQ_TARGET", "15"))),
    ("美妆", "mz", int(os.environ.get("MZ_TARGET", "15"))),
]
BATCH_COOLDOWN = int(os.environ.get("BATCH_COOLDOWN", "300"))
MAX_RETRY = int(os.environ.get("MAX_RETRY", "3"))
CATE_RETRY_WAIT = int(os.environ.get("CATE_RETRY_WAIT", "45"))
NEED_LOGIN = {"v": False}      # 登录态失效标记（collect.py 退出码 3）


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def marker(tag):
    return os.path.join(OUT, "ratelimit_%s.txt" % tag)


def run_once(parent, tag, target):
    """跑一次 collect.py，返回 (退出码, 是否被限流, 耗时)。"""
    env = os.environ.copy()
    env.update({
        "CATE_PARENT": parent,
        "CATE_CHILD": os.environ.get("CATE_CHILD", "不限"),
        "TARGET_DAREN": str(target),
        "OUT_TAG": "_" + tag,
    })
    if os.path.exists(marker(tag)):
        os.remove(marker(tag))
    # ⚠️ 先把上一版产物移走：否则本批**中止**时 run_batch 会把上一轮的旧文件
    #    当成本批成功结果合并进去（踩过：批次中止后仍合并了 265 条旧数据）
    jp = os.path.join(OUT, "darens_%s.json" % tag)
    if os.path.exists(jp):
        arc = os.path.join(OUT, "archive")
        os.makedirs(arc, exist_ok=True)
        dst = os.path.join(arc, "darens_%s_%s.json" % (tag, time.strftime("%Y%m%d_%H%M%S")))
        try:
            os.replace(jp, dst)
            log("  （上一版 darens_%s.json 已归档 -> %s）" % (tag, os.path.basename(dst)))
        except Exception:
            os.remove(jp)
    t0 = time.time()
    rc = subprocess.call([sys.executable, os.path.join(BASE, "collect.py")],
                         cwd=BASE, env=env)
    dt = time.time() - t0
    limited = os.path.exists(marker(tag))
    return rc, limited, dt


def run_batch(parent, tag, target):
    """跑一批（带限流冷却重试），返回该批 records。"""
    log("=" * 70)
    log(">>> 第 %s 批：类目=%s / 目标=%d 个有效达人" % (tag, parent, target))
    log("=" * 70)
    rc, dt = 0, 0.0
    for attempt in range(1, MAX_RETRY + 2):
        rc, limited, dt = run_once(parent, tag, target)
        if rc == 3:
            # 登录态失效：重试没有意义，交给上层整体中止
            log("<<< %s 批中止：精选联盟登录态已失效" % parent)
            NEED_LOGIN["v"] = True
            return []
        if limited and attempt <= MAX_RETRY:
            try:
                why = open(marker(tag), encoding="utf-8").read().strip()
            except Exception:
                why = "11001"
            log("<<< %s 批被限流（%s）-> 冷却 %d 秒后重试（第 %d/%d 次）" % (
                parent, why[:40], BATCH_COOLDOWN, attempt, MAX_RETRY))
            time.sleep(BATCH_COOLDOWN)
            continue
        if limited:
            log("<<< %s 批重试 %d 次仍被限流，放弃该批" % (parent, MAX_RETRY))
        # 退出码 2 = 类目按钮没点到（页面布局/渲染抖动）-> 短冷却重试
        if rc == 2 and attempt <= MAX_RETRY:
            log("<<< %s 批：类目筛选未生效（退出码 2）-> 冷却 %d 秒后重试（第 %d/%d 次）" % (
                parent, CATE_RETRY_WAIT, attempt, MAX_RETRY))
            time.sleep(CATE_RETRY_WAIT)
            continue
        break
    jp = os.path.join(OUT, "darens_%s.json" % tag)
    if not os.path.exists(jp):
        log("<<< %s 批失败：退出码 %d，且没有产出 %s" % (parent, rc, jp))
        return []
    data = json.load(open(jp, encoding="utf-8"))
    ok = sum(1 for r in data if r.get("contact"))
    okw = sum(1 for r in data if r.get("contact_type") == "微信")
    log("<<< %s 批完成：退出码 %d，耗时 %.1f 分，处理 %d 个，有效 %d 个（微信 %d）"
        % (parent, rc, dt / 60.0, len(data), ok, okw))
    return data


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("开始双类目采集：%s（批次冷却 %d 秒）" % (
        " + ".join("%s×%d" % (p, t) for p, _, t in JOBS), BATCH_COOLDOWN))

    all_recs = []
    for idx, (parent, tag, target) in enumerate(JOBS):
        if idx:
            log("冷却 %d 秒，等平台限流窗口过去…" % BATCH_COOLDOWN)
            time.sleep(BATCH_COOLDOWN)
        all_recs.extend(run_batch(parent, tag, target))
        if NEED_LOGIN["v"]:
            log("!! 精选联盟登录态失效 -> 中止整个采集流程")
            log("!! 请先执行：  python login.py   （扫码登录后）再重跑 python collect_30.py")
            return

    # 按 uid 去重（同一达人可能同时挂个护家清和美妆）
    seen, merged = set(), []
    for r in all_recs:
        uid = r.get("uid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        merged.append(r)

    ok = [r for r in merged if r.get("contact")]
    okw = [r for r in ok if r.get("contact_type") == "微信"]
    log("=" * 70)
    log("合并结果：共 %d 个达人（去重后），有效 %d 个，其中微信号 %d 个"
        % (len(merged), len(ok), len(okw)))
    for cate in ("个护家清", "美妆"):
        n = sum(1 for r in ok if r.get("src_cate") == cate)
        log("   %s：有效 %d 个" % (cate, n))
    log("=" * 70)

    if not merged:
        log("!! 两批都没有产出（很可能仍被限流）-> 不覆盖已有正式名单")
        return

    sys.path.insert(0, BASE)
    import darens_io
    darens_io.write_outputs(merged, OUT, "", log=log)
    log("已写出合并名单（正式文件，无 tag 后缀）")
    log("结束")


if __name__ == "__main__":
    main()
