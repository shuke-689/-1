# -*- coding: utf-8 -*-
"""探针：平台侧「有联系方式」筛选是否还在 / 标签有没有改名 / payload 字段名。

为什么单独做一个探针：
  2026-09-22 平台把「**粉丝量**」改名成「**粉丝指数**」（选项一字未变）→ 首选标签找不到
  就整块筛选失败。同一天用户又要求把「**有联系方式**」加回平台侧 —— 这类**开关型**筛选项
  一旦改名，`FIND_FORMITEM_JS` 的前缀匹配就会落空（`apply_contact_filter()` 会**软失败**：
  只记日志继续跑，不中止），所以需要一个「一眼看出在不在、叫什么名字」的侦察手段。

本探针**只读 + 可回滚**（点一次勾上、再点一次取消），回答：
  A. 页面上**全部** form-item 的文本与序号 —— 看清「有联系方式」排在第几个
     （⚠️ `collect.py` 的筛选回显原来只打前 20 个，而它正好排在 20 名之后，被这个截断坑过）。
  B. 该 form-item 自身的结构（tag / class / 尺寸 / 背景色），确认是**开关型**（点击即生效、
     不弹下拉）还是已经变成下拉型。
  C. 点一下之后的 payload：`has_contact` 到底叫什么键、值是什么形态。

⚠️ 不复制 JS 字符串：能用 ast 从 collect.py 抠的就抠（探针自己抄一份会得假结论）。
⚠️ 不能 import collect（它会替换 sys.stdout）。
⚠️ **A 阶段（collect.py / collect_30.py）在跑时不要跑本探针** —— 同一个
   `.edge-auto/profile` 是单例锁，会互相抢；而且探针自己会点筛选、发请求。
跑法：source tools/env.sh && "$PY" .probe/probe_contact.py
"""
import ast
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
DAREN_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
OUT = os.path.join(BASE, "out")

WANT = ("FIND_FORMITEM_JS", "ALL_DROPDOWNS_JS", "CLOSE_DROPDOWN_JS", "FORMITEM_TEXT_JS")

TARGET_LABEL = os.environ.get("CONTACT_LABEL", "有联系方式")

# ---- 探针自带侦察 JS ----
# 列出全部 form-item（文本 + 坐标 + 尺寸），序号即页面顺序
LIST_FORMITEMS_JS = """() => {
  const out = [];
  document.querySelectorAll('div.auxo-form-item').forEach((e, i) => {
    const t = (e.innerText || '').trim();
    if (!t) return;
    const r = e.getBoundingClientRect();
    out.push({i: i, t: t.slice(0, 40), w: Math.round(r.width), h: Math.round(r.height),
              x: Math.round(r.x), y: Math.round(r.y),
              bg: getComputedStyle(e).backgroundColor});
  });
  return out;
}"""

# 目标 form-item 的内部结构：找那些「文字就是整行文本、且自己没同文本子节点」的叶子
DUMP_TARGET_JS = """(label) => {
  const fi = [...document.querySelectorAll('div.auxo-form-item')]
      .find(e => (e.innerText || '').trim().startsWith(label));
  if (!fi) return null;
  const r = fi.getBoundingClientRect();
  const kids = [];
  fi.querySelectorAll('*').forEach(e => {
    const t = (e.innerText || '').trim();
    if (!t || t.length > 16) return;
    const sub = [...e.children].map(c => (c.innerText || '').trim());
    if (sub.includes(t)) return;
    const rr = e.getBoundingClientRect();
    if (rr.width < 4 || rr.height < 4) return;
    kids.push({t: t, tag: e.tagName, cls: String(e.className || '').slice(0, 80),
               x: Math.round(rr.x), y: Math.round(rr.y),
               w: Math.round(rr.width), h: Math.round(rr.height),
               bg: getComputedStyle(e).backgroundColor,
               color: getComputedStyle(e).color});
  });
  return {box: {x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)},
          text: (fi.innerText || '').trim().slice(0, 60),
          cls: String(fi.className || '').slice(0, 80), kids: kids};
}"""


def log(m):
    print(m, flush=True)


def load_js():
    src = io.open(os.path.join(BASE, "collect.py"), encoding="utf-8").read()
    found = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in WANT:
                try:
                    found[t.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    missing = [w for w in WANT if w not in found]
    if missing:
        log("!! 没抠到常量: %s" % missing)
        sys.exit(1)
    log("已从 collect.py 抠到 %d 个 JS 常量" % len(found))
    return found


def main():
    J = load_js()
    reqs = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            viewport={"width": 2552, "height": 1262}, args=["--start-maximized"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_req(r):
            if "search_feed_author" in r.url and r.method == "POST":
                try:
                    reqs.append(r.post_data or "")
                except Exception:
                    pass

        page.on("request", on_req)

        def click_box(b, pause=1.6):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(pause)

        def last_filters():
            for q in reversed(reqs):
                try:
                    j = json.loads(q)
                except Exception:
                    continue
                f = j.get("filters")
                if isinstance(f, dict) and f:
                    return f
            return None

        def wait_req(prev, sec=10):
            t0 = time.time()
            while time.time() - t0 < sec:
                if len(reqs) > prev:
                    try:
                        page.wait_for_timeout(1400)
                    except Exception:
                        pass
                    return True
                try:
                    page.wait_for_timeout(400)
                except Exception:
                    time.sleep(0.4)
            return False

        log("打开达人广场 …")
        page.goto(DAREN_URL, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)
        txt = ""
        for _t in range(8):
            try:
                txt = page.evaluate(
                    "() => (document.body && document.body.innerText || '').slice(0, 400)")
                if txt and txt.strip():
                    break
            except Exception as e:
                log("  (第%d次取 body 失败，等页面稳定：%s)" % (_t + 1, str(e)[:60]))
            time.sleep(3)
        log("当前 URL: %s" % page.url)
        if not any(m in (txt or "") for m in ("主推类目", "找达人", "按商品找达人")):
            log("!! 未登录（body 前 200 字：%r），需先在 .edge-auto 的 Edge 窗口里登录再重跑"
                % (txt or "")[:200])
            ctx.close()
            return
        log("登录态: 已登录")

        # ============ A. 全部 form-item ============
        log("")
        log("=" * 78)
        log("A. 页面上全部 form-item（看「%s」在第几个）" % TARGET_LABEL)
        log("=" * 78)
        items = page.evaluate(LIST_FORMITEMS_JS) or []
        log("  共 %d 个：" % len(items))
        hit_i = None
        for it in items:
            mark = ""
            if it["t"].startswith(TARGET_LABEL):
                mark = "   <<<<<< 命中"
                if hit_i is None:
                    hit_i = it["i"]
            log("   #%-3d %-24s h=%-4s @(%s,%s)%s"
                % (it["i"], it["t"], it["h"], it["x"], it["y"], mark))
        if hit_i is None:
            log("  !! 前面这些都没有「%s」开头的项 —— 可能被改名了。" % TARGET_LABEL)
            log("     对策：export CONTACT_LABEL=\"新名\" 再跑；或把名单发我，我改常量。")
        else:
            log("  ✔ 找到「%s」（序号 #%d）" % (TARGET_LABEL, hit_i))

        # ============ B. 目标 form-item 结构 ============
        log("")
        log("=" * 78)
        log("B. 「%s」自身结构（判断是开关型还是下拉型）" % TARGET_LABEL)
        log("=" * 78)
        d = page.evaluate(DUMP_TARGET_JS, TARGET_LABEL)
        if not d:
            log("  找不到该 form-item，跳过 B/C。")
        else:
            log("  box=%s text=%r" % (d["box"], d["text"]))
            log("  cls=%s" % d["cls"])
            for k in d["kids"]:
                log("     %-14s tag=%-5s bg=%-20s color=%-18s h=%-3s cls=%s"
                    % (k["t"], k["tag"], k["bg"], k["color"], k["h"], k["cls"][:44]))

            # ============ C. 点一下 -> payload ============
            log("")
            log("=" * 78)
            log("C. 点一下「%s」-> payload（开关型：无下拉）" % TARGET_LABEL)
            log("=" * 78)
            box = d["box"]
            prev = len(reqs)
            click_box(box, 2.2)
            dds = page.evaluate(J["ALL_DROPDOWNS_JS"]) or []
            log("  点后可见下拉: %d 个（0 = 开关型，符合预期）" % len(dds))
            for dd in dds:
                log("     下拉选项: %s" % " | ".join(
                    i["t"] for i in (dd.get("items") or [])))
            got = wait_req(prev, 10)
            log("  触发新请求: %s" % got)
            f = last_filters()
            if f:
                log("  最近 payload 里 has_contact = %r"
                    % f.get("has_contact"))
                log("  payload filters = %s"
                    % json.dumps({k: v for k, v in f.items() if v},
                                 ensure_ascii=False)[:420])
            else:
                log("  （没抓到 payload）")
            shown = None
            try:
                shown = page.evaluate(J["FORMITEM_TEXT_JS"], TARGET_LABEL)
            except Exception:
                pass
            log("  回显文本: %r" % shown)

            # 回滚：再点一下取消（避免留下筛选状态）
            prev = len(reqs)
            click_box(box, 2.2)
            wait_req(prev, 6)
            f2 = last_filters()
            log("  再点一下（取消）后 has_contact = %r"
                % (f2.get("has_contact") if f2 else None))

        # 顺手把下拉清干净，别留着浮层
        for _ in range(3):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.3)

        try:
            page.screenshot(path=os.path.join(OUT, "probe_contact.png"))
            log("")
            log("截图: %s" % os.path.join(OUT, "probe_contact.png"))
        except Exception as e:
            log("截图失败: %s" % e)
        ctx.close()


if __name__ == "__main__":
    main()
