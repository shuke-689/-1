#!/usr/bin/env bash
# 阶段B 连跑：反复 `wechat_add.py run --limit N`，直到
#   ① 出现微信风控「操作过于频繁」  ② 候选池加完（没有待加好友了）  ③ 达到 MAX_ROUNDS
#
# 用法:
#   tools/run_b_rounds.sh [LIMIT] [MAX_ROUNDS] [GAP_SEC]
#   默认    10           30            60
#
# ⚠️ 运行前必须满足（脚本**不会**替你满足）：
#   - 微信已登录；
#   - 微信「添加朋友」窗口**已经打开**（微信左下「+」→ 添加朋友）；
#   - 该窗口**没有被其他窗口遮挡**（读结果靠桌面区域截图，被挡住会读错）；
#   - 接下来全程**不要碰鼠标键盘**（脚本会抢）。
# 进入每一轮之前会打印提示；中途放弃请 Ctrl-C 或结束后台任务。
set -u

# ⚠️ 定位脚本自身目录**必须用纯 bash 参数展开**，不能用 dirname：
#    补 usr/bin 的活儿在 env.sh 里，而那才是 dirname 所在的地方（见 env.sh 顶部注释）。
_src="${BASH_SOURCE[0]:-$0}"
_src="${_src//\\//}"
case "$_src" in
  */*/*) HERE="${_src%/*}" ;;            # .../tools/run_b_rounds.sh -> .../tools
  *)     HERE="$PWD/tools" ;;
esac

# shellcheck source=env.sh
. "$HERE/env.sh"            # 导出 $PROJ / $PY / $PYTHONPATH / $GIT

cd "$PROJ" || exit 1

LIMIT=${1:-10}
MAX_ROUNDS=${2:-30}
GAP=${3:-60}
LOG="$PROJ/out/wechat_add_rounds.log"

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "================ 连跑开始：每轮 $LIMIT 个 / 最多 $MAX_ROUNDS 轮 / 轮间 ${GAP}s ================"
say "前置提醒：微信已登录 + 「添加朋友」窗口已打开且未被遮挡 + 期间勿动键鼠"

ROUND=0
while [ "$ROUND" -lt "$MAX_ROUNDS" ]; do
  ROUND=$((ROUND + 1))
  say "---------- 第 $ROUND/$MAX_ROUNDS 轮 开始 ----------"

  OUT="$("$PY" wechat_add.py run --limit "$LIMIT" 2>&1)"
  printf '%s\n' "$OUT" | tee -a "$LOG"

  # ① 风控 -> 立即停手（脚本内部也已停止，这里只是终结连跑）
  if printf '%s' "$OUT" | grep -q "检测到微信风控"; then
    say "!!! 出现微信风控 -> 连跑结束（第 $ROUND 轮）"
    exit 2
  fi
  # ② 前置没满足 -> 直接退出，别空转
  if printf '%s' "$OUT" | grep -q "找不到.*添加朋友"; then
    say "!!! 没找到「添加朋友」窗口 -> 请先打开它再重跑"
    exit 3
  fi
  # ③ 候选加完
  if printf '%s' "$OUT" | grep -q "没有待加好友了"; then
    say "--- 候选池已加完 -> 连跑结束（第 $ROUND 轮）"
    exit 0
  fi
  # ④ 剩余待加为 0 也收工
  LEFT="$(printf '%s' "$OUT" | sed -n 's/.*剩余待加 \([0-9]\+\) 个.*/\1/p' | tail -1)"
  if [ -n "${LEFT:-}" ] && [ "$LEFT" -eq 0 ]; then
    say "--- 剩余待加 0 个 -> 连跑结束（第 $ROUND 轮）"
    exit 0
  fi
  say "第 $ROUND 轮结束，剩余待加 ${LEFT:-?} 个；${GAP}s 后进入下一轮"
  [ "$ROUND" -lt "$MAX_ROUNDS" ] && sleep "$GAP"
done

say "================ 达到最大轮数 $MAX_ROUNDS，连跑结束 ================"
say "下一步：跑 feishu_sync.py 更新飞书表「状态」列"
