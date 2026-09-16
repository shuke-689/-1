# -*- coding: utf-8 -*-
"""一键同步：把本地的优化推上去、把好友的优化拉下来。

    python sync.py status              # 看有哪些未提交改动
    python sync.py pull                # 拉取最新优化（含好友提交的）
    python sync.py push -m "新增XX规则"  # 提交并推送本地优化
    python sync.py auto -m "说明"       # 日常最常用：先提交 -> 再拉 -> 再推
    python sync.py remote <仓库地址>     # 首次绑定 / 切换云端仓库
    python sync.py log                 # 看最近提交

设计要点：
  * 自动探测 git（WorkBuddy 自带 PortableGit，不要求系统装 git）
  * 推送前拦截被误加的敏感文件（.edge-auto / out / .probe/libs）
  * 拉取后发现 requirements.txt 变化 -> 提醒重跑 setup_env.py
  * **本环境适配 1**：本机 git 写 refs/remotes/** 会静默失败
    （rc=0 但文件不落盘）-> fetch 后按 FETCH_HEAD 手工补齐（heal_remote_ref）。
  * **本环境适配 2**：不用 --autostash（本机会报 "Cannot autostash"）-> 改为
    「先提交本地改动，再拉取」，rebase 时工作区天然干净。
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

# 绝不允许进入版本库的路径前缀
FORBIDDEN = (".edge-auto/", ".edge-work/", ".probe/libs/", "out/",
             ".workbuddy/memory/")


def find_git():
    cands = []
    home = os.path.expanduser("~")
    pg = os.path.join(home, ".workbuddy", "binaries", "PortableGit", "versions")
    if os.path.isdir(pg):
        for v in sorted(os.listdir(pg)):
            for sub in ("cmd", "bin"):
                p = os.path.join(pg, v, sub, "git.exe")
                if os.path.exists(p):
                    cands.append(p)
    for p in (r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe",
              "/usr/bin/git", "/usr/local/bin/git"):
        if os.path.exists(p):
            cands.append(p)
    cands.sort(reverse=True)
    for c in cands:
        return c
    return "git"


GIT = find_git()


def hr(t=""):
    print("=" * 62)
    if t:
        print(t)
        print("=" * 62)


def run(args, capture=True, check=False):
    """跑一条 git 命令。返回 (退出码, 输出文本)。"""
    cmd = [GIT] + args
    try:
        p = subprocess.run(cmd, cwd=BASE, capture_output=capture,
                           text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        hr("❌ 找不到 git")
        print("git 路径： %s" % GIT)
        print("请确认 WorkBuddy 自带的 PortableGit 存在，或自行安装 Git 后重试。")
        sys.exit(1)
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        print(out.strip())
        sys.exit(p.returncode)
    return p.returncode, out.strip()


# ---------------------------------------------------------------- 基础查询

def have_repo():
    rc, _ = run(["rev-parse", "--is-inside-work-tree"])
    return rc == 0


def have_remote():
    rc, out = run(["remote"])
    return rc == 0 and bool(out.strip())


def current_branch():
    rc, out = run(["branch", "--show-current"])
    return out.strip() or "main"


def is_dirty():
    rc, out = run(["status", "--porcelain"])
    return bool(out.strip())


def _git_dir():
    rc, out = run(["rev-parse", "--git-dir"])
    if rc != 0 or not out.strip():
        return os.path.join(BASE, ".git")
    p = out.strip()
    return p if os.path.isabs(p) else os.path.join(BASE, p)


# ---------------------------------------------------------------- 环境适配

def head_sha(branch=None):
    """取本地分支当前指向的提交号。"""
    branch = branch or current_branch()
    rc, out = run(["rev-parse", branch])
    return out.strip() if rc == 0 else ""


def write_remote_ref(branch, sha, verbose=True, why=""):
    """直接把 `refs/remotes/origin/<branch>` **文件**写成 <sha>。

    为什么不用 `git update-ref`：本机 git 写 `refs/remotes/**` 会**静默失败**
    （`git update-ref refs/remotes/origin/main <sha>` 返回 0，但文件不落盘；
    `refs/heads/*` 一切正常）。实测**直接写文件是好的**，故走这条路径。
    返回 True 表示本次做了修正。
    """
    if not sha:
        return False
    gd = _git_dir()
    tgt = os.path.join(gd, "refs", "remotes", "origin", branch)
    cur = ""
    if os.path.exists(tgt):
        try:
            cur = open(tgt, encoding="utf-8").read().strip()
        except Exception:
            cur = ""
    if cur == sha:
        return False
    try:
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        with open(tgt, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
    except Exception as e:
        if verbose:
            print("  [环境适配] 修正远端跟踪引用失败：%s" % e)
        return False
    if verbose:
        print("  [环境适配] 已补齐远端跟踪引用 origin/%s -> %s%s"
              % (branch, sha[:8], why))
    return True


def heal_remote_ref(branch=None, verbose=True, only_if_missing=False):
    """按 **FETCH_HEAD** 补齐远端跟踪引用（用于 fetch/pull 之后）。

    本机 git 写 `refs/remotes/**` 静默失败的后果是 `git status` 显示
    `origin/main [gone]`、`git rebase origin/main` 找不到上游。

    重要：FETCH_HEAD 只反映**上一次 fetch**时的远端状态。push 之后它还是
    推送前的旧值，此时按它自愈会把引用**改回去**。所以：
      * fetch/pull 之后  -> 可以正常用（only_if_missing=False）
      * push 之后        -> 不要用，改用 head_sha() + write_remote_ref()
      * 只想查状态的场景 -> only_if_missing=True（仅在引用缺失/为空时补）
    """
    branch = branch or current_branch()
    gd = _git_dir()
    if only_if_missing:
        tgt = os.path.join(gd, "refs", "remotes", "origin", branch)
        cur = ""
        if os.path.exists(tgt):
            try:
                cur = open(tgt, encoding="utf-8").read().strip()
            except Exception:
                cur = ""
        if cur:
            return False  # 已有值，不动它（可能是刚 push 后的正确值）
    fh = os.path.join(gd, "FETCH_HEAD")
    if not os.path.exists(fh):
        return False
    sha = ""
    try:
        with open(fh, encoding="utf-8", errors="replace") as f:
            for line in f:
                # 形如：<sha>\t\tbranch 'main' of https://github.com/...
                if "branch '%s'" % branch in line:
                    sha = line.split("\t", 1)[0].strip()
                    break
    except Exception:
        return False
    return write_remote_ref(branch, sha, verbose=verbose,
                            why="（本机 git 写该路径静默失败）")


# ---------------------------------------------------------------- 仓库/提交

def ensure_repo():
    if not have_repo():
        hr("📦 首次使用：初始化本地仓库")
        run(["init", "-b", "main"], check=True)
        run(["config", "core.autocrlf", "false"])
        print("已初始化。接着绑定云端仓库：  python sync.py remote <地址>")


def show_forbidden():
    """检查暂存区里有没有不该提交的东西。"""
    rc, out = run(["diff", "--cached", "--name-only"])
    if rc != 0 or not out:
        return []
    return [f for f in out.splitlines()
            if f.replace("\\", "/").lstrip("./").startswith(FORBIDDEN)]


def read_req():
    try:
        with open(os.path.join(BASE, "requirements.txt"), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def commit_local(msg=None, quiet=False):
    """有改动就暂存并提交。返回是否产生了新提交。"""
    if not is_dirty():
        if not quiet:
            print("本地没有新改动。")
        return False
    run(["add", "-A"], check=True)
    bad = show_forbidden()
    if bad:
        hr("⛔ 拒绝提交：暂存区含敏感文件")
        for b in bad:
            print("   %s" % b)
        print()
        print("这些文件含登录态 / 达人微信号 / 大体积依赖，绝不能上传。")
        print("请先：  git reset")
        return False
    hr("📝 提交本地优化")
    if not msg:
        msg = "sync: %s" % time.strftime("%Y-%m-%d %H:%M")
    rc, out = run(["commit", "-m", msg])
    print(out or "(无输出)")
    return rc == 0


# ---------------------------------------------------------------- 子命令

def cmd_status():
    ensure_repo()
    # 仅在引用文件缺失时补（有值就不动：那可能是刚 push 后的正确值，
    # 而 FETCH_HEAD 仍是旧的，会把它改回去）
    heal_remote_ref(verbose=False, only_if_missing=True)
    hr("🔍 同步状态")
    rc, out = run(["status", "-sb"])
    print(out or "(干净)")
    rc, rem = run(["remote", "-v"])
    print()
    print("远端：" + (rem.splitlines()[0] if rem.strip()
                    else "❌ 未配置 -> python sync.py remote <地址>"))
    bad = show_forbidden()
    if bad:
        print()
        print("⚠️ 暂存区包含敏感/大文件，请先取消暂存：")
        for b in bad:
            print("     git reset -- %s" % b)


def cmd_pull():
    ensure_repo()
    if not have_remote():
        print("❌ 还没配置远端。先跑：  python sync.py remote <仓库地址>")
        return 1
    if is_dirty():
        print("⚠️ 工作区有未提交改动，rebase 需要干净工作区。")
        print("   先提交：  python sync.py push -m \"说明\"")
        print("   或一步到位：  python sync.py auto -m \"说明\"")
        return 1
    before = read_req()
    br = current_branch()
    hr("⬇️  拉取云端最新优化")
    rc, out = run(["fetch", "origin"])
    print(out or "(无输出)")
    if rc != 0:
        print()
        print("⚠️ 拉取失败，常见原因：")
        print("   * 凭据失效 -> 跑一次 git fetch，按提示在浏览器里授权")
        print("   * 网络不通（GitHub 在国内可能较慢）")
        return rc
    heal_remote_ref(br)
    rc, out = run(["rebase", "origin/%s" % br])
    print(out or "(无输出)")
    if rc != 0:
        print()
        print("⚠️ 拉取冲突了（你和好友改了同一处）。按下面处理：")
        print("   1) git status                 # 看哪些文件冲突")
        print("   2) 打开冲突文件，改掉 <<<<<<< ======= >>>>>>> 标记")
        print("   3) git add <文件> && git rebase --continue")
        print("   4) 再跑  python sync.py push -m \"合并冲突\"")
        return rc
    after = read_req()
    if before and after and before != after:
        print()
        print("📦 requirements.txt 有变动 -> 建议重跑：  \"$PY\" setup_env.py")
    return 0


def _push_only():
    if not have_remote():
        print("❌ 还没配置远端。先跑：  python sync.py remote <仓库地址>")
        return 1
    bad = show_forbidden()
    if bad:
        hr("⛔ 拒绝推送：暂存区含敏感文件")
        for b in bad:
            print("   %s" % b)
        print()
        print("请先：  git reset")
        return 1
    hr("⬆️  推送到云端")
    rc, out = run(["push"])
    print(out or "(无输出)")
    if rc == 0:
        # push 成功后远端已 == 本地 HEAD。本机 git 更新远端跟踪引用同样静默失败，
        # 这里按**本地 HEAD** 补齐（不能用 heal_remote_ref：那读的是推送前的 FETCH_HEAD）
        write_remote_ref(current_branch(), head_sha(), verbose=True,
                         why="（push 后按本地 HEAD 补齐，本机 git 写该路径静默失败）")
    else:
        print()
        print("⚠️ 推送失败，常见原因：")
        print("   * 云端有新提交 -> 先跑  python sync.py pull  再 push")
        print("   * 没登录 -> 首次推送需在浏览器里授权一次")
    return rc


def cmd_push(msg=None):
    ensure_repo()
    if not have_remote():
        print("❌ 还没配置远端。先跑：  python sync.py remote <仓库地址>")
        return 1
    commit_local(msg)
    return _push_only()


def cmd_auto(msg=None):
    """先提交 -> 再拉 -> 再推。顺序很重要：先提交，rebase 就不需要 autostash。"""
    ensure_repo()
    if not have_remote():
        print("❌ 还没配置远端。先跑：  python sync.py remote <仓库地址>")
        return 1
    commit_local(msg)
    print()
    rc = cmd_pull()
    if rc != 0:
        return rc
    print()
    return _push_only()


def cmd_remote(url):
    ensure_repo()
    rc, out = run(["remote"])
    if out.strip():
        run(["remote", "set-url", "origin", url], check=True)
        print("已更新 origin -> %s" % url)
    else:
        run(["remote", "add", "origin", url], check=True)
        print("已绑定 origin -> %s" % url)
    rc, out = run(["branch", "--show-current"])
    print("当前分支： %s" % (out.strip() or "main"))
    print()
    print("首次推送：  python sync.py push -m \"首次共享\"")


def cmd_log():
    ensure_repo()
    rc, out = run(["log", "--oneline", "-n", "15"])
    print(out or "(还没有提交)")


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else "auto"
    msg = None
    if "-m" in a:
        i = a.index("-m")
        if i + 1 < len(a):
            msg = a[i + 1]

    if cmd == "status":
        cmd_status()
    elif cmd == "pull":
        sys.exit(cmd_pull())
    elif cmd == "push":
        sys.exit(cmd_push(msg))
    elif cmd == "auto":
        sys.exit(cmd_auto(msg))
    elif cmd == "remote":
        if len(a) < 2:
            print(__doc__)
            sys.exit(1)
        cmd_remote(a[-1])
    elif cmd == "log":
        cmd_log()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
