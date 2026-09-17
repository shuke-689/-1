#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 .py 里给 page.evaluate() 用的 JS 字符串常量抠出来，交给 node 做语法校验。

为什么需要它：
  - Playwright 的 JS 负载是**字符串**，Python 侧看不出语法错，只有跑到那一步才报；
  - 跑阶段A/B 时 Edge profile 被占用，**没法另起探针去真机试**；
  - 所以先把 JS 抠成 .js 放 `out/_jscheck/`，用 `node --check` 过语法，
    再用桩 DOM 跑行为测试（见 `out/_jscheck/test_find_close.js`）。

用法:
    "$PY" tools/check_js.py douyin_id.py [其它.py ...]
    "$PY" tools/check_js.py douyin_id.py --dump     # 只导出不校验

能解析的写法（按源码顺序，可引用前面已解析的常量）：
    NAME  = \"\"\"...\"\"\"                      字面量
    NAME  = \"\"\"...%s...\"\"\" % (arg,)           str % args（用 AST 里的实参填掉）
    NAME  = \"() => {\" + _COMMON + \"...\"}        多个常量/字面量用 + 拼
输出只取「名字以 _JS 结尾且不以 _ 开头」的（`_POPUP_COMMON_JS` 这类中间件只用于解析）。
"""
import ast
import json
import os
import subprocess
import sys

OUT = os.path.join("out", "_jscheck")


class Resolver(object):
    def __init__(self, src):
        self.src = src
        self.vals = {}          # 模块级「字符串结果」的名字 -> 值

    def lit(self, node):
        try:
            return ast.literal_eval(node)
        except Exception:
            return None

    def res(self, node):
        """递归求值：字面量 / 名字 / 元组·列表 / + 拼接 / % 填充 / list()·json.dumps()。"""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.vals.get(node.id)
        if isinstance(node, (ast.Tuple, ast.List)):
            vals = [self.res(e) for e in node.elts]
            return None if any(v is None for v in vals) else tuple(vals)
        if isinstance(node, (ast.Dict, ast.Set)):
            return self.lit(node)
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname == "list" and node.args:
                v = self.res(node.args[0])
                return list(v) if isinstance(v, (list, tuple)) else None
            if fname == "dumps" and node.args:
                v = self.res(node.args[0])
                if isinstance(v, (list, dict, tuple)):
                    return json.dumps(v, ensure_ascii=False)
                return None
            return None
        if isinstance(node, ast.BinOp):
            left = self.res(node.left)
            if left is None:
                return None
            if isinstance(node.op, ast.Add):
                right = self.res(node.right)
                return None if right is None else left + right
            if isinstance(node.op, ast.Mod):
                args = self.res(node.right)        # 不用 literal_eval：实参可能是 json.dumps(...)
                if args is None:
                    return None
                if not isinstance(args, tuple):
                    args = (args,)
                try:
                    return left % args
                except Exception as e:
                    print("  ! %% 填充失败: %s" % e)
                    return None
        return None

    def run(self):
        out = {}
        tree = ast.parse(self.src, filename="<src>")
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            name = getattr(node.targets[0], "id", None)
            if not name:
                continue
            v = self.res(node.value)
            if v is None:
                continue
            self.vals[name] = v                       # 全部记下来，供后面引用（含 _ 开头）
            if name.endswith("_JS") and not name.startswith("_") and isinstance(v, str):
                out[name] = v
        return out


def find_node():
    node = os.environ.get("NODE") or ""
    if node:
        return node
    root = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries",
                        "node", "versions")
    cands = []
    if os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d, "node.exe")
            if os.path.isfile(p):
                cands.append(p)
    return cands[-1] if cands else "node"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dump_only = "--dump" in sys.argv
    if not args:
        print(__doc__)
        return 2

    node = find_node()
    os.makedirs(OUT, exist_ok=True)
    total, bad = 0, 0
    for path in args:
        print("== %s ==" % path)
        items = Resolver(open(path, encoding="utf-8").read()).run()
        if not items:
            print("  （没有可校验的 *_JS 常量）")
        for name in sorted(items):
            js = items[name]
            total += 1
            dst = os.path.join(OUT, "%s.js" % name)
            with open(dst, "w", encoding="utf-8") as f:   # 包成箭头函数才能被 node 解析
                f.write("const f = " + js + ";\n")
            if dump_only:
                print("  导出 %s（%d 字节）" % (dst, len(js)))
                continue
            r = subprocess.run([node, "--check", dst], capture_output=True, text=True)
            if r.returncode == 0:
                print("  OK   %s -> %s（%d 字节）" % (name, dst, len(js)))
            else:
                bad += 1
                print("  FAIL %s -> %s" % (name, dst))
                print("       " + (r.stderr or "").strip().replace("\n", "\n       ")[:600])

    print("\n合计 %d 个常量，语法失败 %d 个" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
