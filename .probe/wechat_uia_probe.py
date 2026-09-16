# -*- coding: utf-8 -*-
"""用 UI Automation 读取微信主窗口的控件树，判断能否被程序化操控。"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import uiautomation as auto  # noqa: E402


def main():
    print("UIA 初始化...")
    root = auto.GetRootControl()
    print("桌面根节点 OK: %s" % root.Name)

    target = None
    for w in root.GetChildren():
        try:
            name = (w.Name or "").strip()
        except Exception:
            continue
        cls = w.ClassName or ""
        if name == "微信" or "Weixin" in cls or "WeChat" in cls:
            target = w
            break

    if target is None:
        print("未找到微信窗口")
        return

    print("找到微信窗口: Name=%r Class=%r Handle=%s" % (target.Name, target.ClassName, target.NativeWindowHandle))
    print("可交互? ", target.IsEnabled, " 可见?", not target.IsOffscreen)

    print("=" * 70)
    print("顶层控件树 (深度 3):")

    def walk(ctrl, depth=0, maxdepth=3):
        if depth > maxdepth:
            return
        try:
            children = ctrl.GetChildren()
        except Exception:
            children = []
        for c in children:
            try:
                cname = (c.Name or "").replace("\n", " ")[:40]
                print("%s[%s] %r  type=%s" % ("  " * depth, depth, cname, c.ControlTypeName))
            except Exception:
                pass
            walk(c, depth + 1, maxdepth)

    walk(target, 1, 3)

    print("=" * 70)
    print("尝试定位关键控件:")
    for label, cond in [
        ("搜索框", lambda c: c.ControlTypeName == "EditControl"),
        ("按钮类", lambda c: c.ControlTypeName == "ButtonControl"),
        ("列表项", lambda c: c.ControlTypeName == "ListItemControl"),
        ("文本", lambda c: c.ControlTypeName == "TextControl"),
    ]:
        def bfs(node):
            stack = [node]
            out = []
            while stack:
                cur = stack.pop()
                out.append(cur)
                try:
                    stack.extend(cur.GetChildren())
                except Exception:
                    pass
            return out

        nodes = bfs(target)
        hits = [n for n in nodes if cond(n)]
        print("  %s: %d 个" % (label, len(hits)))
        for h in hits[:5]:
            try:
                print("      - %r" % ((h.Name or "")[:50],))
            except Exception:
                pass


if __name__ == "__main__":
    main()
