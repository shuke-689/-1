#!/usr/bin/env bash
# ============================================================
#  可移植环境初始化 —— 在**项目根目录**执行：
#
#    source tools/env.sh
#    "$PY" login.py --check
#    "$PY" collect_30.py
#
#  目的：把原本写死成 C:\Users\Administrator\... 的路径换成自动探测，
#        这样好友换台机器 / 换个用户名也能跑。
#
#  ⚠️ 实现约束：本脚本必须**只用 bash 内建语法**定位路径。
#     因为它要补的 usr/bin 里才有 dirname/tail/sort/ls，
#     一旦依赖它们就会踩「先有鸡还是先有蛋」（dirname: command not found）。
# ============================================================

# ---- 0) 项目根：纯 bash 参数展开，不用 dirname ------------------
_src="${BASH_SOURCE[0]:-$0}"
_src="${_src//\\//}"                     # 反斜杠 -> 正斜杠
case "$_src" in
  */*/*) PROJ="${_src%/*/*}" ;;          # a/b/c/tools/env.sh -> a/b/c
  *)     PROJ="$PWD" ;;                  # 相对路径退化：按「在项目根执行」处理
esac
case "$PROJ" in
  /*) ;;                                 # 已是绝对路径（含 /c/... 形式）
  *)  PROJ="$PWD/$PROJ" ;;
esac
export PROJ

# ---- 1) 补 Git Bash 的 usr/bin（缺了它 ls/head/dirname 全找不到）----
_git_root="$HOME/.workbuddy/binaries/PortableGit/versions"
_usr_bin=()
for _d in "$_git_root"/*/usr/bin; do
  [ -d "$_d" ] && _usr_bin+=("$_d")
done
if [ ${#_usr_bin[@]} -gt 0 ]; then
  export PATH="${_usr_bin[$(( ${#_usr_bin[@]} - 1 ))]}:$PATH"
fi

# ---- 2) 托管 Python（取词法最大版本号目录）----
_py_c=()
for _p in "$HOME/.workbuddy/binaries/python/versions"/*/python.exe; do
  [ -f "$_p" ] && _py_c+=("$_p")
done
if [ ${#_py_c[@]} -gt 0 ]; then
  export PY="${_py_c[$(( ${#_py_c[@]} - 1 ))]}"
elif command -v python >/dev/null 2>&1; then
  export PY="$(command -v python)"
else
  export PY="python"
  echo "[env.sh] ⚠️ 没找到 WorkBuddy 托管 Python，退回 PATH 里的 python" >&2
fi

# ---- 3) git（PortableGit 自带的 cmd/git.exe）----
_git_c=()
for _g in "$_git_root"/*/cmd/git.exe "$_git_root"/*/bin/git.exe; do
  [ -f "$_g" ] && _git_c+=("$_g")
done
if [ ${#_git_c[@]} -gt 0 ]; then
  export GIT="${_git_c[$(( ${#_git_c[@]} - 1 ))]}"
  export PATH="${GIT%/*}:$PATH"
  # ---- 3b) MinGit 布局补 GIT_EXEC_PATH ----
  # WorkBuddy 自带的 PortableGit 是精简版：`git --exec-path` 指向
  # mingw64/libexec/git-core，那里只有 shell 脚本；真正的 git-remote-http(s).exe
  # 只在 mingw64/bin。不补的话 commit 正常但 push/pull 报
  #   git: 'remote-https' is not a git command
  _groot="${GIT%/*/*}"                       # <...>/PortableGit/versions/1.2.0
  if [ -f "$_groot/mingw64/bin/git-remote-https.exe" ] && \
     [ ! -f "$_groot/mingw64/libexec/git-core/git-remote-https.exe" ]; then
    export GIT_EXEC_PATH="$_groot/mingw64/bin"
    export PATH="$_groot/mingw64/bin:$_groot/cmd:$_groot/usr/bin:$PATH"
  fi
elif command -v git >/dev/null 2>&1; then
  export GIT="$(command -v git)"
else
  export GIT="git"
fi

# ---- 4) 项目内依赖目录（放在 PATH 修好之后，cygpath 才可用）----
if command -v cygpath >/dev/null 2>&1; then
  export PYTHONPATH="$(cygpath -w "$PROJ/.probe/libs" 2>/dev/null || echo "$PROJ/.probe/libs")"
else
  export PYTHONPATH="$PROJ/.probe/libs"
fi

# ---- 5) 校验（只提示，不中断）----
if [ ! -d "$PROJ/.probe/libs" ]; then
  echo "[env.sh] ⚠️ 依赖目录不存在：$PROJ/.probe/libs" >&2
  echo "[env.sh]    先跑：  \"\$PY\" setup_env.py" >&2
fi
if [ ! -d "$PROJ/.edge-auto/profile" ]; then
  echo "[env.sh] ℹ️  还没登录过，采集前先跑：  \"\$PY\" login.py" >&2
fi
