# -*- coding: utf-8 -*-
"""取「达人抖音号」—— 达人主页 → 点「达人抖音主页」→ 读抖音主页上的「抖音号：xxx」。

用户 2026-09-17 要求登记飞书时要这个字段，取法就是用户给的那两步。

===== 为什么不是简单点一下就完事（踩过的坑，别退回去）=====
探针 `.probe/probe_douyin_id.py` / `_id2.py` 实测：
1. 达人主页**接口里已经没有** `account_douyin` 字段了（老版本有，现在返回 None）
   → 只能走「点进抖音主页再读」这条路。
2. 🔴 **点击会串号**：`page.goto(达人主页)` 后如果 **SPA 还没重渲染完**就去点
   「达人抖音主页」，点到的是**上一个达人**的链接 →
   实测「汕头谷饶珊姐富之雅」和「一米六的安安」读到了**同一个抖音号 89435391431**
   （截图证据 out/probe_douyin/一米六的安安_douyin.png，页头赫然是「汕头谷饶珊姐富之雅」）。
   所以**每次点击前必须先确认主页上确实是本人**（`wait_profile_ready`）。
3. 抖音主页会弹「登录后免费畅享高清视频」的登录框，但**只挡中间**，
   顶部「昵称 + 抖音号：xxx + IP属地」照样能读到 → 不用登录。
4. 「达人抖音主页」元素的 href 是空的（JS 跳转），**没法直接拿 URL**，只能点。
5. 点击本身也有抖动（4 个里 1 个第一次点不开）→ 必须**重试**。

===== 铁律 =====
**宁可留空，绝不写错。** 主页身份对不上 / 抖音页读不到 -> 返回 ("", "")，
交给调用方留空，绝不猜。
"""
import json
import os
import re
import time

# 抖音号：形如 "抖音号：89435391431"，也可能是自定义字母号
DOUYIN_NO_RE = re.compile(r"抖音号[：:]\s*([A-Za-z0-9_.\-]{2,32})")
# 抖音主页顶部昵称：取「抖音号」那一行上面一行
_HANDLE_LINE_RE = re.compile(r"抖音号[：:]")

# 找「达人抖音主页」按钮（左栏卡片标题右侧的 "more"，A 标签优先）
FIND_BTN_JS = """() => {
    const out = [];
    document.querySelectorAll('a,div,span,button').forEach(e => {
        const t = (e.innerText||'').trim();
        if (t !== '达人抖音主页') return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 80) return;
        out.push({tag: e.tagName, href: e.getAttribute('href') || '',
                  x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height)});
    });
    out.sort((a, b) => (a.tag === 'A' ? -1 : 0) - (b.tag === 'A' ? -1 : 0)
                       || (b.w * b.h) - (a.w * a.h));
    return out;
}"""


def norm(s):
    """归一化：只留中英文数字，去 emoji / 空格 / 符号（昵称带 emoji 很常见）。"""
    return "".join(ch for ch in (s or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff").lower()


def profile_ready_js(nick_norm, maxlen=60):
    """主页左上角卡片区里是否出现该达人昵称（用于确认页面已切到本人）。"""
    return """(args) => {
        const [want, maxlen] = args;
        const clean = s => (s||'').replace(/[^0-9A-Za-z\\u4e00-\\u9fff]/g, '').toLowerCase();
        let hit = false;
        document.querySelectorAll('div,span,h1,h2,a,p').forEach(e => {
            if (hit) return;
            const r = e.getBoundingClientRect();
            if (r.x > 620 || r.y > 300 || r.width < 20 || r.height < 8) return;
            const t = (e.innerText || '').trim();
            if (!t || t.length > maxlen) return;
            const c = clean(t);
            if (c && want && (c.indexOf(want) >= 0 || want.indexOf(c) >= 0)) hit = true;
        });
        return hit;
    }"""


def read_douyin_page_js():
    """在抖音主页读 {douyin_no, nick_in_body, body_head}。

    ⚠️ 别指望从页面上精确抠「昵称」DOM —— 实测顶部区域抓到的全是抖音的
    站内导航（精选/推荐/AI抖音/直播中…），而且登录弹窗会在 DOM 里插一堆文案。
    改用**整页正文包含性**做交叉校验：达人昵称（归一化后）是否出现在抖音页正文里。
    这只作**证据记录**，不作拦截条件（百应昵称与抖音昵称偶尔不一致，
    真要拦会把好数据丢掉；真正防串号靠 `wait_profile_ready`）。
    """
    return """() => {
        const txt = (document.body.innerText || '');
        const m = txt.match(/抖音号[：:]\\s*([A-Za-z0-9_.\\-]{2,32})/);
        return {douyin_no: m ? m[1] : '', body_head: txt.slice(0, 4000)};
    }"""


def nick_in_body(body_text, nickname):
    """归一化后判断达人昵称是否出现在抖音页正文里（交叉校验证据）。"""
    want = norm(nickname)
    if not want or len(want) < 2:
        return None
    return want in norm(body_text)


# ===================== 弹窗处理（用户 2026-09-17 要求） =====================
# 进抖音达人主页后会弹「登录后免费畅享高清视频 / 扫码登录」的登录框，
# 用户要求：**照图点右上角 X 关掉，再读抖音号**。
# 实测这个框只挡中间，顶部「昵称 + 抖音号」本来也读得到，
# 但关掉更稳（弹窗会 intercept 点击 / 挡住 DOM 区域），且是用户明确要求。
#
# ⚠️ 判定「有弹窗」必须靠**文案**，不能靠「有没有全屏遮罩」——
#    抖音主页本身就有铺满的布局容器，靠遮罩判定会到处误点 ✕。
POPUP_TEXT_KW = ("登录后免费畅享高清视频", "免费畅享高清视频", "登录后免费观看",
                 "扫码登录", "登录抖音", "登录后可")

POPUP_PROBE_JS = """() => {
    const txt = (document.body.innerText || '');
    const kw = %s.find(k => txt.indexOf(k) >= 0) || '';
    return {kw: kw};
}""" % (json.dumps(list(POPUP_TEXT_KW), ensure_ascii=False),)

# 找弹窗右上角的关闭按钮。
#
# ⚠️ 2026-09-17 教训：抖音是 CSS-Modules，class 名是**哈希串**（`J8iVz0S9`），
#    所以 `[class*="close"]` 必然一个都匹配不到 —— 日志里「点 X: …」那行从来没出现过，
#    直接跳到「⚠️ 弹窗没关掉」。旧实现（label / class / ✕文本 三路）在抖音上全军覆没。
#
# 现行算法 = **几何法**，完全不依赖 class 名：
#   1) 找出所有「包含弹窗文案 + fixed/absolute 定位 + 面积 <92% 视口」的容器；
#      面积 >92% 视口的是背后的半透明遮罩，必须排除，否则「右上角」就变成页面右上角。
#      再按面积**升序**取最紧的 8 个（真正贴着弹窗的容器排前面，冗余的外层 wrapper 排后面）；
#   2) 对每个容器分别扫描其内部小元素（8~90 px），以**该容器自己的右上角**为基准算距离，
#      合并打分（越贴角分越低）。多个容器一起算 -> 外面套一层大 wrapper 也不会把 ✕ 挤出去；
#      带 close|关闭|dismiss|cancel 关键字的直接降 1000 分优先；
#   3) 兜底给「最紧那个容器右上角内侧」的猜测点（pri 90000，最后才试）。
FIND_CLOSE_JS = """() => {
    const KW = %s;
    const out = [];
    const rect = (e) => { try { return e.getBoundingClientRect(); } catch (err) { return null; } };
    const vis = (e) => {
        const st = getComputedStyle(e);
        if (st.visibility === 'hidden' || st.display === 'none') return false;
        if (parseFloat(st.opacity || '1') < 0.1) return false;
        return true;
    };
    const VW = innerWidth, VH = innerHeight;

    // ---- 1) 所有合格的弹窗容器，按面积升序 ----
    const roots = [];
    document.querySelectorAll('div,section,article,aside,form').forEach(e => {
        const t = e.innerText || '';
        if (!t) return;
        if (!KW.some(k => t.indexOf(k) >= 0)) return;
        const r = rect(e); if (!r) return;
        if (r.width < 120 || r.height < 100) return;
        if (r.width > VW * 0.92 || r.height > VH * 0.92) return;   // 铺满=遮罩，排除
        const st = getComputedStyle(e);
        if (st.position !== 'fixed' && st.position !== 'absolute') return;
        roots.push({el: e, r: r, area: r.width * r.height});
    });
    if (!roots.length) return out;
    roots.sort((a, b) => a.area - b.area);
    const picked = roots.slice(0, 8);

    // ---- 2) 每个容器各自求「右上角邻居」 ----
    const seenEl = new Set();
    picked.forEach(R => {
        // 窗口随容器尺寸放宽（大 wrapper 的角离 ✕ 可能远一些）
        const ww = Math.max(100, Math.min(240, R.r.width * 0.3));
        const wh = Math.max(100, Math.min(240, R.r.height * 0.3));
        R.el.querySelectorAll('*').forEach(e => {
            const tg = e.tagName;
            if (tg !== 'DIV' && tg !== 'SPAN' && tg !== 'I' && tg !== 'BUTTON' &&
                tg !== 'A' && tg !== 'SVG' && tg !== 'IMG' && tg !== 'P') return;
            const r = rect(e); if (!r) return;
            if (r.width < 8 || r.height < 8) return;
            if (r.width > 90 || r.height > 90) return;
            if (!vis(e)) return;
            const dx = R.r.right - r.right;
            const dy = r.top - R.r.top;
            if (dx < -6 || dy < -6) return;      // 在右上角之外
            if (dx > ww || dy > wh) return;      // 离该容器右上角太远
            const s = [(e.getAttribute('aria-label') || ''),
                       (e.getAttribute('title') || ''),
                       (e.getAttribute('data-e2e') || ''),
                       (typeof e.className === 'string' ? e.className : '')].join(' ').toLowerCase();
            const hit = (s.indexOf('close') >= 0 || s.indexOf('关闭') >= 0 ||
                         s.indexOf('dismiss') >= 0 || s.indexOf('cancel') >= 0 ||
                         s.indexOf('✕') >= 0 || s.indexOf('×') >= 0);
            const k = Math.round(r.x) + ',' + Math.round(r.y) + ',' + r.width + ',' + r.height;
            if (seenEl.has(k)) return;
            seenEl.add(k);
            out.push({x: Math.round(r.x), y: Math.round(r.y),
                      w: Math.round(r.width), h: Math.round(r.height),
                      why: hit ? 'label' : 'corner', pri: (hit ? 0 : 1000) + dx + dy,
                      tag: e.tagName, txt: (e.innerText || '').trim().slice(0, 8)});
        });
    });

    // ---- 3) 兜底猜测点：最紧容器的右上角内侧 32x32 ----
    const T = picked[0].r;
    const gx = Math.round(T.right - 34), gy = Math.round(T.top + 2);
    if (gx > 0 && gy > 0 && gx < VW && gy < VH) {
        out.push({x: gx, y: gy, w: 32, h: 32, why: 'corner-guess',
                  pri: 90000, tag: 'GUESS', txt: ''});
    }

    out.sort((a, b) => a.pri - b.pri);
    return out.slice(0, 10);
}""" % (json.dumps(list(POPUP_TEXT_KW), ensure_ascii=False),)

# 找不到关闭按钮时的取证 dump：把弹窗根 + 右上角区域元素的结构打印出来，
# 供下次定位失败时**从日志直接看出来**该怎么点（不用再单开探针，profile 被占用也测不了）。
POPUP_DUMP_JS = """() => {
    const KW = %s;
    const rect = (e) => { try { return e.getBoundingClientRect(); } catch (err) { return null; } };
    const desc = (e, r) => ({
        tag: e.tagName,
        cls: (typeof e.className === 'string' ? e.className : '').slice(0, 60),
        label: (e.getAttribute('aria-label') || '').slice(0, 20),
        title: (e.getAttribute('title') || '').slice(0, 20),
        e2e: (e.getAttribute('data-e2e') || '').slice(0, 24),
        xy: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
        txt: (e.innerText || '').trim().slice(0, 16)
    });
    const roots = [];
    document.querySelectorAll('div,section,article,aside,form').forEach(e => {
        const t = e.innerText || '';
        if (!t || !KW.some(k => t.indexOf(k) >= 0)) return;
        const r = rect(e); if (!r) return;
        if (r.width < 120 || r.height < 100) return;
        if (r.width > innerWidth * 0.92 || r.height > innerHeight * 0.92) return;
        const st = getComputedStyle(e);
        if (st.position !== 'fixed' && st.position !== 'absolute') return;
        roots.push({el: e, r: r, area: r.width * r.height});
    });
    if (!roots.length) return {vw: innerWidth, vh: innerHeight, root: null,
                       note: '未找到 fixed/absolute 弹窗容器（文案可能来自页面正文，非弹窗）'};
    roots.sort((a, b) => a.area - b.area);
    const T = roots[0];
    const near = [];
    roots.slice(0, 4).forEach(R => {
        R.el.querySelectorAll('*').forEach(el => {
            const r = rect(el); if (!r) return;
            if (r.width < 6 || r.height < 6 || r.width > 120 || r.height > 120) return;
            const dx = R.r.right - r.right, dy = r.top - R.r.top;
            if (dx < -6 || dy < -6 || dx > 160 || dy > 160) return;
            const d = desc(el, r);
            d.root = [Math.round(R.r.x), Math.round(R.r.y), Math.round(R.r.width), Math.round(R.r.height)];
            near.push(d);
        });
    });
    near.sort((a, b) => (a.xy[0] + a.xy[1]) - (b.xy[0] + b.xy[1]));
    return {vw: innerWidth, vh: innerHeight,
            roots: roots.slice(0, 4).map(R => desc(R.el, R.r)),
            root: desc(T.el, T.r), near: near.slice(0, 14)};
}""" % (json.dumps(list(POPUP_TEXT_KW), ensure_ascii=False),)


def popup_present(page):
    """当前抖音页是否还在弹登录框；返回命中的文案（'' = 没有）。"""
    try:
        return (page.evaluate(POPUP_PROBE_JS) or {}).get("kw") or ""
    except Exception:
        return ""


def dismiss_popup(page, log=None, wait_s=4.0, settle_s=0.5, rounds=3):
    """把抖音主页的登录弹窗点掉。返回 True=本来有弹窗且已关掉。

    流程：等弹窗出现（最长 wait_s）-> 找 ✕ 点掉 -> 确认文案消失；没成功就 Esc 兜底，
    最多 rounds 轮。**任何失败都不抛异常**（关不掉也照样读抖音号，顶多是留痕）。
    """
    kw = ""
    waited = 0.0
    while waited < wait_s:                       # 弹窗可能比页面慢一拍
        kw = popup_present(page)
        if kw:
            break
        time.sleep(settle_s)
        waited += settle_s
    if not kw:
        return False
    _log(log, "检测到弹窗（命中「%s」）-> 点 X 关闭" % kw)

    for r in range(rounds):
        try:
            cands = page.evaluate(FIND_CLOSE_JS) or []
        except Exception as e:
            _log(log, "找关闭按钮失败: %s" % str(e)[:60])
            cands = []
        if not cands:
            # 取证：把弹窗结构打进日志，下次就知道该点哪儿了
            try:
                d = page.evaluate(POPUP_DUMP_JS) or {}
                _log(log, "  取证: " + json.dumps(d, ensure_ascii=False)[:700])
            except Exception as e:
                _log(log, "  dump 失败: %s" % str(e)[:60])
        # 逐个试（旧版只点第一个就 break，第一个错了整轮白费）；
        # corner-guess 是瞎猜，留到最后一轮再点，免得误点页面 UI
        limit = 6 if r < rounds - 1 else len(cands)
        for c in cands[:limit]:
            if c.get("why") == "corner-guess" and r < rounds - 1:
                continue
            try:
                page.mouse.click(c["x"] + c["w"] / 2.0, c["y"] + c["h"] / 2.0)
                _log(log, "  点 X: tag=%s 依据=%s %s,%s %sx%s txt=%r"
                     % (c["tag"], c["why"], c["x"], c["y"], c["w"], c["h"], c["txt"]))
            except Exception as e:
                _log(log, "  点 X 异常: %s" % str(e)[:50])
                continue
            time.sleep(0.9)
            if not popup_present(page):
                _log(log, "弹窗已关闭（第 %d 轮 / %s）" % (r + 1, c.get("why")))
                return True
        try:                                      # 兜底：Esc 关弹窗
            page.keyboard.press("Escape")
            time.sleep(0.6)
        except Exception:
            pass
        if not popup_present(page):
            _log(log, "弹窗已关闭（Esc 兜底）")
            return True
        time.sleep(settle_s)

    _log(log, "⚠️ 弹窗没关掉（继续读抖音号，顶部区域通常不受影响）")
    return False


def _log(fn, m):
    (fn or print)("[douyin] " + m)


def wait_profile_ready(page, nickname, log=None, tries=8, pause=1.6):
    """等达人主页真的切到 `nickname` 本人（SPA 重渲染要时间）。返回 bool。"""
    want = norm(nickname)
    if not want:
        return True                     # 昵称异常就没法校验，交给调用方重试
    for i in range(tries):
        try:
            ok = page.evaluate(profile_ready_js(want), [want, 60])
        except Exception:
            ok = False
        if ok:
            return True
        time.sleep(pause)
    return False


def _close_douyin_tabs(ctx, keep=None):
    """关掉遗留的抖音标签页，避免读到上一轮的残留（会串号）。"""
    n = 0
    for pg in list(ctx.pages):
        if pg is keep:
            continue
        try:
            u = pg.url or ""
        except Exception:
            continue
        if "douyin.com" in u:
            try:
                pg.close()
                n += 1
            except Exception:
                pass
    return n


def fetch(page, ctx, nickname, log=None, retries=3):
    """读该达人的抖音号。

    返回 (douyin_id, flag)：
      · 成功 -> ("89435391431", "yes"/"no"/"")   flag=抖音页正文是否含该达人昵称（交叉校验证据）
      · 失败/对不上 -> ("", "")   —— 绝不返回可疑值
    调用前请确保 page 已在**该达人**的主页上（本函数内部也会再校验一次）。
    """
    if not wait_profile_ready(page, nickname, log=log):
        _log(log, "主页未确认是「%s」本人 -> 放弃取抖音号（防串号）" % str(nickname)[:16])
        return "", ""

    btns = []
    try:
        btns = page.evaluate(FIND_BTN_JS) or []
    except Exception as e:
        _log(log, "找「达人抖音主页」失败: %s" % str(e)[:60])
    if not btns:
        _log(log, "没找到「达人抖音主页」按钮")
        return "", ""
    b = btns[0]

    for k in range(retries):
        _close_douyin_tabs(ctx)
        try:
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
        except Exception as e:
            _log(log, "点击异常: %s" % str(e)[:60])
            time.sleep(2)
            continue
        # 等抖音标签页出现（最多 ~10 秒）
        tgt = None
        for _ in range(5):
            time.sleep(2)
            cands = []
            for pg in ctx.pages:
                try:
                    if "douyin.com" in (pg.url or ""):
                        cands.append(pg)
                except Exception:
                    pass
            if cands:
                tgt = cands[-1]
                break
        if tgt is None:
            _log(log, "第%d次点击没开出抖音页" % (k + 1))
            continue

        try:
            tgt.bring_to_front()
            time.sleep(2.0)
            # 用户 2026-09-17 要求：进抖音主页先点 X 关掉登录弹窗，再读抖音号
            dismiss_popup(tgt, log=log)
            time.sleep(0.8)
            got = tgt.evaluate(read_douyin_page_js()) or {}
            dno = (got.get("douyin_no") or "").strip()
            inbody = nick_in_body(got.get("body_head") or "", nickname)
            url = (tgt.url or "")[:100]
        except Exception as e:
            _log(log, "读抖音页异常: %s" % str(e)[:60])
            dno, inbody, url = "", None, ""
        finally:
            try:
                tgt.close()
            except Exception:
                pass
            try:
                page.bring_to_front()
            except Exception:
                pass

        if dno:
            _log(log, "第%d次点击成功: 抖音号=%s 页面含该达人昵称=%s" % (k + 1, dno, inbody))
            return dno, ("yes" if inbody else ("" if inbody is None else "no"))
        _log(log, "第%d次点击: 抖音页没读到抖音号（url=%s）" % (k + 1, url))
        time.sleep(2)

    _log(log, "重试 %d 次仍未取到抖音号 -> 留空" % retries)
    return "", ""


def main():
    """独立跑：给 out/collect/darens.json 里缺 douyin_id 的达人补抖音号。"""
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    base = os.path.dirname(os.path.abspath(__file__))   # 本文件就在项目根
    proj = base
    path = os.path.join(proj, "out", "collect", "darens.json")
    profile = os.path.join(proj, ".edge-auto", "profile")
    profile_url = ("https://buyin.jinritemai.com/dashboard/servicehall/"
                   "daren-profile?uid=%s&enter_from=1&scene=1&author_type=1")
    limit = int(os.environ.get("DOUYIN_LIMIT", "0"))
    force = os.environ.get("DOUYIN_FORCE", "") not in ("", "0", "false", "False")

    def log(m):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

    recs = json.load(open(path, encoding="utf-8"))
    todo = [r for r in recs if r.get("contact") and (force or not r.get("douyin_id"))]
    if limit:
        todo = todo[:limit]
    log("待补抖音号 %d 个（总 %d 条，force=%s）" % (len(todo), len(recs), force))
    if not todo:
        log("没有需要补的，结束")
        return

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile, channel="msedge", headless=False, no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ok = 0
        old = {}
        for i, r in enumerate(todo, 1):
            nick = r.get("nickname") or ""
            if force and r.get("douyin_id"):
                old[r["uid"]] = r["douyin_id"]
            try:
                page.goto(profile_url % r["uid"], wait_until="domcontentloaded", timeout=90_000)
                time.sleep(3)
                dno, dnick = fetch(page, ctx, nick, log=log)
            except Exception as e:
                dno, dnick = "", ""
                log("  ! 异常: %s" % str(e)[:120])
            if dno:
                r["douyin_id"] = dno
                r["douyin_nick"] = dnick
                ok += 1
            chg = ""
            if r["uid"] in old:
                chg = "  （原值 %s %s）" % (old[r["uid"]], "一致" if old[r["uid"]] == dno else "★不一致★")
            log("[%d/%d] %-22s 抖音号=%s%s" % (i, len(todo), nick[:20], dno or "✗", chg))
            if i % 5 == 0:
                json.dump(recs, open(path, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                log("  （已回写 darens.json，进度 %d/%d）" % (i, len(todo)))
        json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log("完成：取到 %d/%d，已回写 %s" % (ok, len(todo), path))
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
