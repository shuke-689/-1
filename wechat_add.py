# -*- coding: utf-8 -*-
"""微信「添加朋友」全自动加好友。

微信 4.x 是 Qt 全自绘窗口（无 UIA 控件树），因此全部走：
    截图 -> RapidOCR 找文字 -> 换算屏幕坐标 -> SendInput 注入鼠标键盘

每个达人的状态机：
  1. 置前「添加朋友」窗口
  2. 清空搜索框 -> 粘贴微信号/手机号 -> 点「搜索」
  3. 读结果页：
       搜不到（该用户不存在/无法找到）  -> not_found  （换下一个）
       结果昵称含「稿费」               -> excluded   （换下一个）
       已是好友（有「发消息」无「添加到通讯录」） -> already
       其他异常                        -> unknown    （换下一个）
  4. 点「添加到通讯录」
  5. 申请页：点「填入」带出常用申请语 -> 备注填达人名字 -> 点「确定」

用法：
  python wechat_add.py probe                   # dump 当前「添加朋友」窗口 OCR
  python wechat_add.py probe-search <微信号>    # 搜一个号并 dump 结果页 OCR
  python wechat_add.py status                   # 看台账与剩余待加数量
  python wechat_add.py run --limit N [--dry]    # 正式跑；--dry 只填不发送（点取消）

多轮台账：结果累积写入 out/wechat/add_results.json（不覆盖）。
已 sent / already / excluded / not_found 的达人下一轮自动跳过，不会重复处理。
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".probe"))
OUT = os.path.join(BASE, "out", "wechat")
STEPS = os.path.join(OUT, "steps")
LOG = os.path.join(BASE, "out", "wechat_add.log")
os.makedirs(STEPS, exist_ok=True)

import win_io as w  # noqa: E402
import ocr  # noqa: E402

NOT_FOUND_KW = ("用户不存在", "无法找到", "没有找到", "找不到相关账号", "找不到相关内容",
                "请检查", "不存在", "找不到")
# 已是好友 -> 结果页是好友资料卡：有「发消息/语音聊天/视频聊天」和「朋友资料/共同群聊」
ALREADY_KW = ("发消息", "发信息", "语音聊天", "视频聊天", "朋友资料", "共同群聊")
EXCLUDE_NICK_KW = ("稿费",)
APPLY_TITLE = "申请添加朋友"
ADD_TITLE = "添加朋友"
# 微信风控提示 —— 一旦出现立即停止整个流程
RISK_KW = ("操作过于频繁", "请稍后再试", "稍后再试", "操作频繁", "过于频繁", "请稍后重试")
# 计入台账「已完成」的状态：这些达人以后不再重试
#   sent=已发申请 / already=已是好友 / excluded=命中排除词(稿费) / not_found=搜不到
# 不计入：unknown(结果页无法识别)、error、risk_control -> 下次会重试
DONE_STATUS = ("sent", "already", "excluded", "not_found")
RESULT_FILE = os.path.join(OUT, "add_results.json")


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_ledger():
    """已处理达人台账：uid -> 结果记录（多轮累积，不覆盖）。"""
    try:
        rows = json.load(open(RESULT_FILE, encoding="utf-8"))
    except Exception:
        return {}
    led = {}
    for r in rows:
        u = r.get("uid")
        if u:
            led[u] = r
    return led


class WeChat:
    def __init__(self):
        self.win = None
        self.main = None
        self.rect = None
        self.refresh()

    # ---------- 窗口 ----------
    def refresh(self):
        wins = w.list_windows(visible_only=True)
        best_area = 0
        for it in wins:
            t = it["title"] or ""
            if t == "添加朋友":
                self.win = it["hwnd"]
            elif t in ("微信", "WeChat") and "Qt" in (it["cls"] or ""):
                r = w.window_rect(it["hwnd"])
                if r[2] * r[3] > best_area:
                    best_area = r[2] * r[3]
                    self.main = it["hwnd"]
        if self.win:
            self.rect = w.window_rect(self.win)
        return self.win

    def ensure_front(self):
        if not self.refresh():
            raise RuntimeError("找不到「添加朋友」窗口（请先在微信里点「+」→「添加朋友」）")
        w.set_foreground(self.win)
        time.sleep(0.7)
        self.rect = w.window_rect(self.win)
        return self.rect

    # ---------- 截图 / OCR / 点击 ----------
    def shot(self, name=None):
        # 2026-09-16 踩到：`cannot write empty image` —— 窗口 rect 取成 0x0
        # （窗口被最小化 / 句柄失效 / 被别的窗口挤掉），截图就是空图，保存时炸。
        # 这里先校验 rect，必要时把窗口重新提到前台并重试，再不行就明确报错。
        for attempt in range(4):
            self.rect = w.window_rect(self.win)
            if self.rect[2] > 10 and self.rect[3] > 10:
                break
            if attempt == 0:
                self.refresh()              # 句柄可能变了
            if attempt <= 1:
                w.set_foreground(self.win)  # 可能被最大化窗口挤到后面
            time.sleep(0.9)
        img = w.screenshot_region(*self.rect)
        if getattr(img, "width", 0) <= 0 or getattr(img, "height", 0) <= 0:
            raise RuntimeError(
                "微信窗口截图失败（rect=%s）——窗口可能被最小化或被其他窗口完全遮挡"
                % (self.rect,))
        if name:
            img.save(os.path.join(STEPS, "%s.png" % name))
        return img

    def items(self):
        return ocr.ocr(self.shot())

    def click_abs(self, ox, oy):
        w.click(self.rect[0] + ox, self.rect[1] + oy)

    def click_item(self, it, dx=0, dy=0):
        w.click(self.rect[0] + it["cx"] + dx, self.rect[1] + it["cy"] + dy)

    def click_text(self, *kw, exact=False, ymin=0, ymax=10 ** 9, dx=0, dy=0):
        it = ocr.find(self.items(), *kw, exact=exact, ymin=ymin, ymax=ymax)
        if not it:
            return None
        self.click_item(it, dx, dy)
        return it

    # ---------- 搜索框 ----------
    def focus_search_box(self):
        items = self.items()
        # 搜索框：窗口顶部 (cy<135) 的输入内容/占位符，取最左边那个
        cand = [i for i in items if i["cy"] < 135 and i["h"] < 45 and i["w"] > 40]
        if cand:
            it = min(cand, key=lambda i: i["cx"])
            self.click_item(it)
        else:
            self.click_abs(self.rect[2] // 3, 62)
        time.sleep(0.4)

    def search(self, text):
        self.focus_search_box()
        w.send_keys(["CTRL", "A"])
        time.sleep(0.2)
        w.send_keys(["DELETE"])
        time.sleep(0.25)
        w.paste_text(text)
        time.sleep(1.0)
        if not self.click_text("搜索", exact=True):
            w.send_keys(["ENTER"])
        time.sleep(3.2)

    # ---------- 读结果页 ----------
    def read_result(self, shot_name=None):
        img = self.shot(shot_name)
        items = ocr.ocr(img)
        rc = ocr.find(items, *RISK_KW)
        if rc:
            return "risk_control", rc["text"], items, img
        nf = ocr.find(items, *NOT_FOUND_KW)
        if nf:
            return "not_found", nf["text"], items, img
        add_btn = ocr.find(items, "添加到通讯录", "加到通讯录")
        if not add_btn:
            if ocr.find(items, *ALREADY_KW):
                return "already", "", items, img
            return "unknown", "", items, img
        # 昵称 = 「添加到通讯录」上方一整段的文字（按 x 拼接，避免 OCR 拆段）
        band = [i for i in items
                if 135 < i["cy"] < add_btn["cy"] - 30 and i["w"] > 8]
        band.sort(key=lambda i: (round(i["cy"] / 22), i["cx"]))
        nick = "".join(i["text"] for i in band).strip()
        return "found", nick, items, img


def probe():
    wx = WeChat()
    log("添加朋友 hwnd=%s rect=%s" % (wx.win, wx.rect))
    wx.ensure_front()
    img = wx.shot("probe_init")
    log("窗口尺寸 %s" % (img.size,))
    log(ocr.dump(ocr.ocr(img), "添加朋友窗口"))


def probe_search(kw):
    wx = WeChat()
    wx.ensure_front()
    log("搜索: %s" % kw)
    wx.search(kw)
    st, nick, items, _ = wx.read_result("probe_search_result")
    log("状态=%s 昵称=%r" % (st, nick))
    log(ocr.dump(items, "结果页"))


# ---------------------------------------------------------------- 申请页
def _find_top(title):
    """按标题精确找可见顶层窗口，返回 hwnd。"""
    for it in w.list_windows(visible_only=True):
        if (it["title"] or "") == title:
            return it["hwnd"]
    return None


def _click_rel(arect, rx, ry):
    """以窗口左上角为原点点击。"""
    w.click(arect[0] + int(rx), arect[1] + int(ry))


def _blue_link_xy(img, ymin=90, ymax=540, margin=30):
    """兜底：找蓝色链接文字「填入」的像素，取最密集的那一行（排除边缘杂散像素）。"""
    px = img.convert("RGB").load()
    W, H = img.size
    W2 = max(1, W - margin)
    buckets = {}
    for y in range(ymin, min(ymax, H)):
        for x in range(W2):
            r, g, b = px[x, y]
            if b > 120 and (b - r) > 45 and (b - g) > 20:
                buckets.setdefault(y // 12, []).append((x, y))
    if not buckets:
        return None
    best = max(buckets.values(), key=len)
    if len(best) < 6:
        return None
    xs = [p[0] for p in best]
    ys = [p[1] for p in best]
    return (sum(xs) // len(xs), sum(ys) // len(ys))


def _find_fill_btn(img, items=None):
    """定位「填入」按钮，返回相对坐标 (x, y)。

    优先用 OCR：它常把「填入」和后面的提示语粘成一行（如
    "55佣金，可以考虑下合作嘛填入"），此时点该行的最右端即可。
    """
    items = items if items is not None else ocr.ocr(img)
    for it in items:
        if "填入" in it["text"]:
            return (it["box"][2] - 9, it["cy"])
    it = ocr.find(items, "填入", exact=True)
    if it:
        return (it["cx"], it["cy"])
    return _blue_link_xy(img)


def dismiss_apply_dialog():
    """关掉遗留的「申请添加朋友」窗口（点取消），避免它挡住后续点击。"""
    ah = _find_top(APPLY_TITLE)
    if not ah:
        return False
    w.set_foreground(ah)
    time.sleep(0.6)
    arect = w.window_rect(ah)
    it = ocr.find(ocr.ocr(w.screenshot_window(ah)), "取消", exact=True)
    if it:
        _click_rel(arect, it["cx"], it["cy"])
    else:
        _click_rel(arect, arect[2] // 2 + 100, arect[3] - 68)
    time.sleep(1.2)
    log("  已关闭遗留的申请页")
    return True


def detect_risk():
    """检查「添加朋友」窗口是否弹出风控提示，返回提示文案或 None。"""
    ah = _find_top(ADD_TITLE)
    if not ah:
        return None
    hit = ocr.find(ocr.ocr(w.screenshot_window(ah)), *RISK_KW)
    return hit["text"] if hit else None


def close_risk_dialog(items=None, wx=None):
    """点掉风控弹窗的「确定」，让界面恢复可读。"""
    if items is None:
        if wx is None:
            return False
        items = wx.items()
    it = ocr.find(items, "确定", exact=True)
    if not it:
        return False
    if wx is not None:
        wx.click_item(it)
    else:
        ah = _find_top(ADD_TITLE)
        if not ah:
            return False
        r = w.window_rect(ah)
        _click_rel(r, it["cx"], it["cy"])
    time.sleep(1.2)
    return True


def fill_apply(nick, shown, idx, dry):
    """申请页三步：点「填入」带出常用申请语 -> 备注填达人名 -> 确定/取消。

    注意：申请页是独立顶层窗口，且布局会随申请语行数上移，所有坐标必须
    在当前截图里重新 OCR 定位，不能写死。
    """
    ah = _find_top(APPLY_TITLE)
    if not ah:
        log("  ! 未出现「申请添加朋友」窗口（点「添加到通讯录」可能没生效）")
        return "no_apply_dialog"
    w.set_foreground(ah)
    time.sleep(1.0)
    arect = w.window_rect(ah)

    # --- 1) 点「填入」带出常用申请语 ---
    img = w.screenshot_window(ah)
    img.save(os.path.join(STEPS, "run_%02d_apply.png" % idx))
    before_items = ocr.ocr(img)
    before_txt = "".join(i["text"] for i in before_items if i["cy"] < 330)
    xy = _find_fill_btn(img, before_items)
    if xy:
        _click_rel(arect, xy[0], xy[1])
        time.sleep(1.6)
        img2 = w.screenshot_window(ah)
        img2.save(os.path.join(STEPS, "run_%02d_filled.png" % idx))
        items2 = ocr.ocr(img2)
        after_txt = "".join(i["text"] for i in items2 if i["cy"] < 320)
        ok = after_txt != before_txt
        log("  点「填入」@(%d,%d) -> %s" % (xy[0], xy[1], "已生效" if ok else "未见变化"))
        if not ok:                      # 再试一次（取更靠字的右端再点一下）
            _click_rel(arect, xy[0], xy[1] + 2)
            time.sleep(1.6)
    else:
        log("  ! 未找到「填入」，保留原申请语")

    # --- 2) 备注 = 达人名字（重新截图，因布局已上移）---
    img = w.screenshot_window(ah)
    img.save(os.path.join(STEPS, "run_%02d_filled.png" % idx))
    lab = ocr.find(ocr.ocr(img), "备注")
    remark = (shown or nick).strip()
    if lab and remark:
        _click_rel(arect, arect[2] // 2, lab["cy"] + 62)
        time.sleep(0.6)
        w.send_keys(["CTRL", "A"])
        time.sleep(0.2)
        w.send_keys(["DELETE"])
        time.sleep(0.15)
        w.paste_text(remark)
        time.sleep(0.8)
        log("  备注已填: %s" % remark[:24])
    elif not lab:
        log("  ! 未找到备注框")

    # --- 3) 确定 / 取消 ---
    img = w.screenshot_window(ah)
    img.save(os.path.join(STEPS, "run_%02d_ready.png" % idx))
    items = ocr.ocr(img)
    if dry:
        it = ocr.find(items, "取消", exact=True)
        if it:
            _click_rel(arect, it["cx"], it["cy"])
        time.sleep(1.5)
        try:
            w.screenshot_window(ah).save(os.path.join(STEPS, "run_%02d_after_cancel.png" % idx))
        except Exception:
            pass
        return "dry_stop"
    it = ocr.find(items, "确定", exact=True) or ocr.find(items, "发送", exact=True)
    if not it:
        log("  ! 未找到「确定」按钮")
        return "confirm_missing"
    _click_rel(arect, it["cx"], it["cy"])
    time.sleep(2.2)
    try:
        w.screenshot_window(ah).save(os.path.join(STEPS, "run_%02d_after_ok.png" % idx))
    except Exception:
        pass
    return "sent"


def run(limit=0, dry=False):
    open(LOG, "w", encoding="utf-8").close()
    src = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
    ledger = load_ledger()
    cand = [d for d in src if d.get("contact")]
    todo = [d for d in cand
            if (ledger.get(d.get("uid")) or {}).get("add_status") not in DONE_STATUS]
    skipped = len(cand) - len(todo)
    if limit:
        todo = todo[:limit]
    log("候选 %d 个（已处理跳过 %d 个）-> 本轮待加 %d 个%s" % (
        len(cand), skipped, len(todo), "（dry 模式）" if dry else ""))
    if not todo:
        log("没有待加好友了（全部已处理）")
        return

    wx = WeChat()
    wx.ensure_front()
    log("添加朋友窗口 rect=%s" % (wx.rect,))

    results = []
    stop_reason = ""
    for idx, d in enumerate(todo, 1):
        nick, contact = d["nickname"], d["contact"]
        st, note = "unknown", ""
        try:
            dismiss_apply_dialog()          # 清掉上一轮遗留的申请页
            wx.ensure_front()
            wx.search(contact)
            st, shown, items, _ = wx.read_result("run_%02d_search" % idx)

            if st == "risk_control":
                # 微信风控 —— 立即停止整个流程
                note = shown
                log("  [%d/%d] %-18s 微信风控「%s」-> 停止操作" % (
                    idx, len(todo), nick[:16], shown))
                close_risk_dialog(items, wx)
            elif st == "not_found":
                log("  [%d/%d] %-18s 搜不到（%s）-> 换下一个" % (idx, len(todo), nick[:16], shown))
            elif st == "already":
                log("  [%d/%d] %-18s 已是好友 -> 跳过" % (idx, len(todo), nick[:16]))
            elif st == "unknown":
                log("  [%d/%d] %-18s 结果页无法识别 -> 换下一个" % (idx, len(todo), nick[:16]))
            elif any(k in shown for k in EXCLUDE_NICK_KW):
                st = "excluded"
                note = shown
                log("  [%d/%d] %-18s 结果昵称「%s」命中排除词 -> 换下一个" % (
                    idx, len(todo), nick[:16], shown))
            else:
                note = shown
                log("  [%d/%d] %-18s 结果昵称「%s」-> 添加到通讯录" % (
                    idx, len(todo), nick[:16], shown))
                btn = ocr.find(items, "添加到通讯录", "加到通讯录")
                wx.click_item(btn)
                time.sleep(3.2)             # 等独立申请页窗口弹出
                st = fill_apply(nick, shown, idx, dry)
                if st == "no_apply_dialog":
                    hit = detect_risk()     # 可能被风控弹窗挡住了
                    if hit:
                        st, note = "risk_control", hit
                log("  [%d/%d] %-18s -> %s" % (idx, len(todo), nick[:16], st))
        except Exception as e:
            st, note = "error", str(e)[:120]
            log("  [%d/%d] %-18s 异常: %s" % (idx, len(todo), nick[:16], note))
        results.append({**d, "add_status": st, "add_note": note})

        if st == "risk_control":
            stop_reason = "微信触发频率限制：%s" % (note or "操作过于频繁，请稍后再试。")
            log("=" * 60)
            log("!! 检测到微信风控，已停止后续所有操作（已处理 %d/%d）" % (idx, len(todo)))
            break
        time.sleep(1.2)

    # 结果合并写入台账（不覆盖历史，多轮可累积）
    merged = dict(ledger)
    for r in results:
        merged[r["uid"]] = r
    json.dump(list(merged.values()),
              open(os.path.join(OUT, "add_results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    if stop_reason:
        log("停止原因：%s" % stop_reason)
    from collections import Counter
    log("=" * 60)
    log("结果统计: %s" % dict(Counter(r["add_status"] for r in results)))
    left = [d for d in cand if (merged.get(d.get("uid")) or {}).get("add_status")
            not in DONE_STATUS]
    log("累计台账 %d 条；剩余待加 %d 个" % (len(merged), len(left)))


def status():
    """打印台账与剩余待加数量。"""
    src = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
    ledger = load_ledger()
    cand = [d for d in src if d.get("contact")]
    left = [d for d in cand if (ledger.get(d.get("uid")) or {}).get("add_status")
            not in DONE_STATUS]
    from collections import Counter
    log("候选达人 %d 个 / 台账 %d 条 / 剩余待加 %d 个" % (len(cand), len(ledger), len(left)))
    log("台账状态分布: %s" % dict(Counter(
        (r.get("add_status") or "?") for r in ledger.values())))
    for d in left:
        log("  待加: %-22s %-8s %s" % ((d["nickname"] or "")[:20],
                                       d.get("contact_type") or "", d.get("contact")))


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else "probe"
    if mode == "probe":
        probe()
    elif mode == "probe-search":
        probe_search(args[1])
    elif mode == "run":
        lim = int(args[args.index("--limit") + 1]) if "--limit" in args else 0
        run(lim, dry="--dry" in args)
    elif mode == "status":
        status()
    else:
        print(__doc__)
