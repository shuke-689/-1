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

count_edge() {
    tasklist /fi "imagename eq msedge.exe" 2>/dev/null | tail -n +4 | wc -l
}

count_py() {
    tasklist /fi "imagename eq python.exe" 2>/dev/null | tail -n +4 | wc -l
}

taskkill /F /IM msedge.exe /T >/dev/null 2>&1 || true

for i in $(seq 1 20); do
    [ "$(count_edge)" -eq 0 ] && break
    sleep 0.5
done

echo "kill_edge: 剩余 msedge 进程 = $(count_edge) / python 进程 = $(count_py)（请立即启动采集，勿等待）"
