#!/usr/bin/env bash
# 清理残留的 Edge 进程（2026-09-19 新增）
#
# 背景：collect.py / douyin_id.py 用 Playwright 的 launch_persistent_context 启动
# Playwright 自带的 msedge（--user-data-dir=.edge-auto/profile）。
# 如果 python 进程被强杀（例如后台任务被回收、超时被 kill），msedge 不一定会跟着退出，
# 于是它继续占用 .edge-auto/profile 的 singleton 锁 —— 下次启动就会立刻失败：
#
#   playwright._impl._errors.TargetClosedError:
#     BrowserType.launch_persistent_context: Target page, context or browser has been closed
#   [pid=xxxxx][out] 正在现有浏览器会话中打开。   ← Edge 认成「已有实例」直接交接退出
#
# 特点是 **退出极快（0.0 分钟）、日志几乎为空**，很容易误判成「平台限流」。
# 判别方法：日志里搜 "正在现有浏览器会话中打开" 或 "TargetClosedError"。
#
# ⚠️ 两个实测坑：
#   1. `taskkill //F //IM ...` 里用双斜杠**不行** —— taskkill 会报
#      「无效参数/选项 - '//F'」。必须用**单斜杠**（Git Bash 不会转换这些短参数）。
#   2. 杀完不能马上启动：Windows 侧 profile 锁要再等几秒才释放；
#      但也不能等太久 —— 实测 **杀掉约 15 秒后 Edge 会自己带着上次的会话重启**，
#      又占住 profile。所以「杀 → 立刻启动」是唯一稳的窗口。
#
# 因此本脚本**只负责杀 + 确认归零**，不要在它后面接 sleep；调用方拿到 0 就尽快启动采集。

# ⚠️ 三个实测坑：
#   1. **必须用单斜杠**：`taskkill //F //IM ...` / `tasklist //fi ...` 会被
#      taskkill/tasklist 当成无效参数（报「无效参数/选项 - '//F'」），
#      命令静默失败 —— 而且 `| wc -l` 会输出 0，看上去像「已经清干净了」，
#      于是后面的启动失败被误判成「平台限流」。**这是本文件最大的坑。**
#   2. 杀完不能久等：实测 **杀掉约 15 秒后 Edge 会自己带着上次的会话重启**，
#      又占住 profile。所以「杀 → 立刻启动」是唯一稳的窗口。
#   3. 但也不能马上启动：Windows 侧 profile 锁要再等几秒才释放。
#      折中：杀掉后轮询到进程归 0（约 1-3 秒）就立刻启动。

# 🔴 2026-09-23 修正：**只杀命令行含 `.edge-auto` 的 msedge**。
#   旧版是 `taskkill /F /IM msedge.exe /T` —— 它把**用户自己开的 Edge 也一起杀掉**，
#   直接违反「安全铁律 #4：清理残留 Edge 时只按命令行包含 .edge-auto\profile 精确匹配，
#   绝不碰用户自己的 Edge」。实测本机 14 个 msedge 全是用户自己的（自动化残留 0 个），
#   照旧版跑就是「每轮采集都把用户的浏览器群灭一次」。
#   实测逻辑收敛到 tools/kill_auto_edge.py（bash / collect_more 共用同一份实现；
#   tasklist 看不到命令行，所以内部用 PowerShell 的 Win32_Process.CommandLine）。
#
#   ⚠️ 本脚本**允许**在未 source tools/env.sh 的情况下直接跑（SKILL 里就是这么写的），
#      所以这里自带 $PY 探测，不依赖 $PY 已导出。

_self="${BASH_SOURCE[0]:-$0}"
_self="${_self//\\//}"
case "$_self" in
  */*/*) _tools="${_self%/*}" ;;
  *)     _tools="$PWD/tools" ;;
esac
_proj="${_tools%/*}"

if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    for _p in "$HOME"/.workbuddy/binaries/python/versions/*/python.exe; do
        [ -x "$_p" ] && PY="$_p"          # 取词法最大版本号（glob 已排序）
    done
fi
: "${PY:=python}"

count_py() {
    tasklist /fi "imagename eq python.exe" 2>/dev/null | tail -n +4 | wc -l
}

"$PY" "$_tools/kill_auto_edge.py"

echo "kill_edge: python 进程 = $(count_py)（请立即启动采集，勿等待）"
