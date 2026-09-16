# -*- coding: utf-8 -*-
"""一次性环境安装 / 自检。

把 requirements.txt 里的依赖装进**项目内**的 .probe/libs，
不污染全局 Python，也不影响别人。

用法：
  python setup_env.py            # 安装依赖（默认走清华镜像，国内快）
  python setup_env.py --no-mirror  # 走官方 PyPI
  python setup_env.py --check    # 只自检，不安装
  python setup_env.py --force    # 重新装一遍
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(BASE, ".probe", "libs")
REQ = os.path.join(BASE, "requirements.txt")

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 顶层依赖 -> 用于自检的 import 名
CHECK_IMPORTS = [
    ("playwright.sync_api", "playwright"),
    ("openpyxl", "openpyxl"),
    ("rapidocr_onnxruntime", "rapidocr_onnxruntime"),
    ("PIL", "pillow"),
    ("numpy", "numpy"),
    ("comtypes", "comtypes"),
    ("uiautomation", "uiautomation"),
]


def hr(t=""):
    print("=" * 62)
    if t:
        print(t)
        print("=" * 62)


def check():
    """把 .probe/libs 挂到 sys.path 上，逐个 import。"""
    if LIBS not in sys.path:
        sys.path.insert(0, LIBS)
    ok, bad = [], []
    for mod, pkg in CHECK_IMPORTS:
        try:
            __import__(mod)
            ok.append(pkg)
        except Exception as e:
            bad.append("%s (%s)" % (pkg, str(e)[:60]))
    hr("环境自检")
    print("Python : %s" % sys.version.split()[0])
    print("解释器 : %s" % sys.executable)
    print("依赖目录: %s  %s" % (LIBS, "存在" if os.path.isdir(LIBS) else "缺失"))
    print("-" * 62)
    print("✅ 已就绪 %d 个: %s" % (len(ok), ", ".join(ok) if ok else "-"))
    if bad:
        print("❌ 缺失 %d 个:" % len(bad))
        for b in bad:
            print("     - %s" % b)
        print()
        print("修复：  \"$PY\" setup_env.py")
    else:
        print("全部依赖就绪。")
    # Edge 检查（playwright 用 channel=msedge，不下载浏览器）
    try:
        import shutil
        edge = None
        for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
            if os.path.exists(c):
                edge = c
                break
        print("-" * 62)
        print("Microsoft Edge: %s" % (edge or "❌ 未找到（阶段A 必需）"))
    except Exception:
        pass
    return not bad


def install(use_mirror=True, force=False):
    os.makedirs(LIBS, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "install",
           "--target", LIBS, "-r", REQ]
    if force:
        cmd.append("--upgrade")
    if use_mirror:
        cmd += ["-i", MIRROR]
    hr("安装依赖 -> %s" % LIBS)
    print("命令： %s" % " ".join(cmd))
    print("-" * 62)
    rc = subprocess.call(cmd)
    if rc != 0:
        print()
        print("⚠️ 安装失败（退出码 %d）。可尝试：" % rc)
        print("   1) 换官方源：  \"$PY\" setup_env.py --no-mirror")
        print("   2) 去掉 requirements.txt 里的 == 版本锁后重试")
        return False
    return True


def main():
    args = set(sys.argv[1:])
    only_check = "--check" in args
    if only_check:
        sys.exit(0 if check() else 1)
    ok = install(use_mirror="--no-mirror" not in args, force="--force" in args)
    if ok:
        print()
        check()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
