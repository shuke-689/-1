# -*- coding: utf-8 -*-
"""探针：2026-09-22 口径变更 —— 「内容类型」上平台侧 + 「主推类目/个人护理」级联。

用户新要求（原话要点）：
  · 平台侧筛选全部清除，只保留：主推类目 + 内容类型 + 直播结算总额
  · 个护家清 -> 选「个人护理」；美妆 -> 选「不限」
  · 内容类型：先在右侧点「展开」，再按图选 13 个
    （亲子/休闲娱乐/剧情/情感/时尚/明星/母婴/生活记录/舞蹈/艺术/音乐/颜值/其他）

本探针**只读侦察**，回答：
  A. 「内容类型」form-item 的结构：里面的标签 chip 是什么元素、class 是什么、
     「展开」按钮在哪；点展开前后 chip 数量对比。
  B. 点选 2 个 chip 后，接口 payload 里 `content_type` 的确切形态
     （filter.json 里已查到 field_name=content_type、value=中文名，需实测确认）。
  C. 「主推类目」点开 个护家清 后，级联面板的结构；点「个人护理」到底是
     **选中**还是**只展开第三列**（看回显 + payload 的 main_cate_new）。

⚠️ 不复制 JS 字符串：能用 ast 从 collect.py 抠的就抠（踩过的坑：探针自己抄一份会得假结论）。
⚠️ 不能 import collect（它会替换 sys.stdout）。
跑法：source tools/env.sh && "$PY" .probe/probe_ct_cate.py
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

WANT = ("FIND_FORMITEM_JS", "CLICK_FORMITEM_JS", "ALL_DROPDOWNS_JS", "CLOSE_DROPDOWN_JS",
        "FORMITEM_TEXT_JS", "FIND_CATE_JS", "FIND_CASCADER_JS", "LIST_CASCADER_JS")

CT13 = ["亲子", "休闲娱乐", "剧情", "情感", "时尚", "明星", "母婴",
        "生活记录", "舞蹈", "艺术", "音乐", "颜值", "其他"]

# ---- 探针自带的侦察 JS（验证通过后会搬进 collect.py）----
DUMP_CT_JS = """() => {
  const pick = () => {
    const all = [...document.querySelectorAll('div.auxo-form-item')];
    return all.find(e => (e.innerText || '').trim().startsWith('内容类型'));
  };
  const fi = pick();
  if (!fi) return null;
  const r = fi.getBoundingClientRect();
  const chips = [];
  fi.querySelectorAll('*').forEach(e => {
    const t = (e.innerText || '').trim();
    if (!t || t.length > 8) return;
    const kids = [...e.children].map(c => (c.innerText || '').trim());
    if (kids.includes(t)) return;
    const rr = e.getBoundingClientRect();
    if (rr.width < 8 || rr.height < 8) return;
    chips.push({t, tag: e.tagName, cls: String(e.className || '').slice(0, 70),
                x: Math.round(rr.x), y: Math.round(rr.y), w: Math.round(rr.width),
                h: Math.round(rr.height), bg: getComputedStyle(e).backgroundColor});
  });
  return {box: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                h: Math.round(r.height)}, n: chips.length, chips};
}"""

FIND_CT_EXPAND_JS = """() => {
  const fi = [...document.querySelectorAll('div.auxo-form-item')]
      .find(e => (e.innerText || '').trim().startsWith('内容类型'));
  if (!fi) return null;
  for (const e of fi.querySelectorAll('*')) {
    const t = (e.innerText || '').trim();
    if (t !== '展开' && t !== '收起') continue;
    if (e.children.length) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return null;
    return {text: t, x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height)};
  }
  return null;
}"""

FIND_CT_CHIP_JS = """(name) => {
  const fi = [...document.querySelectorAll('div.auxo-form-item')]
      .find(e => (e.innerText || '').trim().startsWith('内容类型'));
  if (!fi) return null;
  for (const e of fi.querySelectorAll('*')) {
    const t = (e.innerText || '').trim();
    if (t !== name) continue;
    if ([...e.children].map(c => (c.innerText || '').trim()).includes(t)) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    return {t, tag: e.tagName, cls: String(e.className || '').slice(0, 70),
            x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
            h: Math.round(r.height), bg: getComputedStyle(e).backgroundColor};
  }
  return null;
}"""

DUMP_POPUPS_JS = """() => {
  const out = [], seen = new Set();
  document.querySelectorAll('div,ul').forEach(e => {
    const cls = String(e.className || '');
    if (!/cascader|dropdown|popup|menu|select/i.test(cls)) return;
    const r = e.getBoundingClientRect();
    if (r.width < 80 || r.height < 50 || r.top < 0 || r.left < 0) return;
    if (r.right > window.innerWidth + 2 || r.bottom > window.innerHeight + 2) return;
    const key = [Math.round(r.x), Math.round(r.y), Math.round(r.width)].join(',');
    if (seen.has(key)) return;
    seen.add(key);
    const items = [];
    e.querySelectorAll('li,div[role=menuitem],span,a').forEach(x => {
      const t = (x.innerText || '').trim();
      if (!t || t.length > 10) return;
      const rr = x.getBoundingClientRect();
      if (rr.width < 8 || rr.height < 8) return;
      items.push({t, tag: x.tagName, cls: String(x.className || '').slice(0, 60),
                  x: Math.round(rr.x), y: Math.round(rr.y),
                  bg: getComputedStyle(x).backgroundColor});
    });
    out.push({cls: cls.slice(0, 80), box: {x: Math.round(r.x), y: Math.round(r.y),
              w: Math.round(r.width), h: Math.round(r.height)}, n: items.length,
              items: items.slice(0, 70)});
  });
  return out.slice(0, 5);
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

        def click_box(b, pause=1.4):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(pause)

        def close_dd(n=3):
            for _ in range(n):
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    if not (page.evaluate(J["ALL_DROPDOWNS_JS"]) or []):
                        return
                    if not page.evaluate(J["CLOSE_DROPDOWN_JS"]):
                        return
                except Exception:
                    pass
            return

        def last_filters():
            for q in reversed(reqs):
                try:
                    j = json.loads(q)
                except Exception:
                    continue
                f = j.get("filters")
                if isinstance(f, dict) and f:
                    return {k: v for k, v in f.items() if v}
            return None

        def wait_req(prev, sec=8):
            t0 = time.time()
            while time.time() - t0 < sec:
                if len(reqs) > prev:
                    try:
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    return True
                try:
                    page.wait_for_timeout(400)
                except Exception:
                    time.sleep(0.4)
            return False

        def dump_ct(tag):
            d = page.evaluate(DUMP_CT_JS)
            if not d:
                log("  [%s] 找不到「内容类型」form-item" % tag)
                return None
            log("  [%s] 内容类型 box=%s  chip 数=%d" % (tag, d["box"], d["n"]))
            for c in d["chips"]:
                log("      %-8s tag=%-6s bg=%-20s cls=%s"
                    % (c["t"], c["tag"], c["bg"], c["cls"][:46]))
            return d

        def dump_popups(tag):
            ps = page.evaluate(DUMP_POPUPS_JS) or []
            log("  [%s] 可见浮层 %d 个" % (tag, len(ps)))
            for d in ps:
                log("     popup cls=%s box=%s 项数=%d" % (d["cls"], d["box"], d["n"]))
                for it in d["items"]:
                    log("        %-10s tag=%-5s @(%s,%s) bg=%s"
                        % (it["t"], it["tag"], it["x"], it["y"], it["bg"]))
            return ps

        log("打开达人广场 …")
        page.goto(DAREN_URL, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)
        # SPA 会二次跳转（登录态/落地页），evaluate 可能撞上 "Execution context was destroyed"
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

        # ============ A. 内容类型结构 + 展开 ============
        log("")
        log("=" * 78)
        log("A. 「内容类型」收起态结构")
        log("=" * 78)
        d0 = dump_ct("收起态")
        n0 = d0["n"] if d0 else 0
        exp = page.evaluate(FIND_CT_EXPAND_JS)
        log("  「展开/收起」按钮: %s" % exp)

        if exp:
            log("  -> 点击「%s」" % exp["text"])
            click_box(exp, 1.8)
            d1 = dump_ct("展开后")
            n1 = d1["n"] if d1 else 0
            log("  展开前 chip=%d，展开后 chip=%d" % (n0, n1))

        # ============ B. 点选 2 个 chip，看 payload ============
        log("")
        log("=" * 78)
        log("B. 点选内容类型 -> payload")
        log("=" * 78)
        prev = len(reqs)
        for name in ("亲子", "时尚"):
            c = page.evaluate(FIND_CT_CHIP_JS, name)
            if not c:
                log("  !! 找不到 chip %s" % name)
                continue
            log("  点击 %s tag=%s bg=%s @(%s,%s) cls=%s"
                % (name, c["tag"], c["bg"], c["x"], c["y"], c["cls"][:50]))
            click_box(c, 1.2)
        got = wait_req(prev, 10)
        log("  触发新请求: %s" % got)
        f = last_filters()
        log("  最近 payload filters = %s"
            % json.dumps(f, ensure_ascii=False)[:420] if f else "  （没抓到）")
        after = page.evaluate(FIND_CT_CHIP_JS, "亲子")
        log("  点选后「亲子」bg=%s（变蓝=真的选中了）" % (after or {}).get("bg"))

        # ============ C. 主推类目 个护家清 -> 个人护理 ============
        log("")
        log("=" * 78)
        log("C. 主推类目 个护家清 级联面板")
        log("=" * 78)
        close_dd()
        hits = page.evaluate(J["FIND_CATE_JS"], "个护家清")
        log("  FIND_CATE_JS('个护家清') -> %s" % (hits[:2] if hits else "**没找到**"))
        if hits:
            click_box(hits[0], 2.4)
            dump_popups("个护家清面板")
            sub = page.evaluate(J["FIND_CASCADER_JS"], "个人护理")
            log("  FIND_CASCADER_JS('个人护理') -> %s" % (sub or "**没找到**"))
            if sub:
                prev2 = len(reqs)
                click_box(sub, 2.6)
                log("  点完「个人护理」后的回显: %s" % (
                    page.evaluate("""() => {
                        const out = [];
                        document.querySelectorAll('*').forEach(e => {
                            const t = (e.innerText || '').trim();
                            if (t.startsWith('主推类目') && t.length < 90) out.push(t);
                        });
                        return out.slice(0, 3);
                    }""")))
                dump_popups("点完之后")
                wait_req(prev2, 8)
                f2 = last_filters()
                log("  payload filters = %s"
                    % (json.dumps(f2, ensure_ascii=False)[:420] if f2 else "（没抓到）"))

        try:
            page.screenshot(path=os.path.join(OUT, "probe_ct_cate.png"))
            log("")
            log("截图: %s" % os.path.join(OUT, "probe_ct_cate.png"))
        except Exception as e:
            log("截图失败: %s" % e)
        ctx.close()


if __name__ == "__main__":
    main()
