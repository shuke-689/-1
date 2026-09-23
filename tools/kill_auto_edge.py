# -*- coding: utf-8 -*-
"""只清理「自动化自己启的」msedge —— 命令行含 `.edge-auto` 的那些。

🔴 安全铁律 #4：清理残留 Edge **只能**按命令行精确匹配 `.edge-auto\\profile`，
   **绝不碰用户自己的 Edge**。
   2026-09-23 实测踩到：`tools/kill_edge.sh` 与 `tools/collect_more.py` 里都是
   `taskkill /F /IM msedge.exe /T` —— 那是**杀全部 Edge**。当时本机 14 个 msedge
   **全是用户自己的**（`edge-auto` 归属 0 个），等于「每轮采集都把用户的浏览器群灭一次」。
   已把两处都改为「先取命令行、只杀含 `.edge-auto` 的 PID」。

为什么需要 WMI：`tasklist` 不显示命令行。用 PowerShell 的 `Win32_Process.CommandLine`
取（python 子进程直接起 powershell，不需要额外的第三方依赖）。

用法：
    "$PY" tools/kill_auto_edge.py          # 杀 + 轮询归零（供 kill_edge.sh / collect_more 调用）
    "$PY" tools/kill_auto_edge.py --list    # 只列 PID，不杀
    "$PY" tools/kill_auto_edge.py --all-count   # 顺带打印全部 msedge 数（对比用）

兼容性：python 3.8+，无第三方依赖。
"""
import subprocess
import sys
import time

_PS_QUERY = ("(Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
             "Where-Object {{ $_.CommandLine -like '*{kw}*' }} | "
             "Select-Object -ExpandProperty ProcessId)")

_PS_BINARIES = ("powershell",
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


def _ps(script, timeout=60):
    for exe in _PS_BINARIES:
        try:
            out = subprocess.run([exe, "-NoProfile", "-Command", script],
                                 capture_output=True, timeout=timeout)
        except Exception:
            continue
        return out.stdout.decode("utf-8", "replace")
    return ""


def msedge_pids(keyword="edge-auto"):
    """返回命令行含 `keyword` 的 msedge PID 列表。keyword="" → 全部 msedge。"""
    script = _PS_QUERY.format(kw=keyword) if keyword else \
        "(Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\").ProcessId"
    return [int(t) for t in _ps(script).split() if t.strip().isdigit()]


def kill_edge(poll_rounds=20, gap=0.5, verbose=False):
    """杀掉自动化残留的 msedge 并等它归零。返回 (杀掉数, 剩余数)。"""
    pids = msedge_pids("edge-auto")
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    left = pids
    for _ in range(poll_rounds):
        left = msedge_pids("edge-auto")
        if not left:
            break
        time.sleep(gap)
    if verbose:
        print("kill_edge: 杀 %d 个自动化 msedge，剩余 %d 个" % (len(pids), len(left)))
    return len(pids), len(left)


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--list" in args:
        print("自动化(edge-auto) msedge PID:", msedge_pids("edge-auto"))
        print("全部 msedge 数:", len(msedge_pids("")))
    elif "--all-count" in args:
        print("全部 msedge 数:", len(msedge_pids("")))
    else:
        kill_edge(verbose=True)
