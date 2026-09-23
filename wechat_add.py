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
  python wechat_add.py csv                      # 把台账重新导出成 add_results.csv

多轮台账：结果累积写入 out/wechat/add_results.json（不覆盖），
并在每轮结束时同步刷新 out/wechat/add_results.csv（给人看的版本）。
已 sent / already / excluded / not_found 的达人下一轮自动跳过，不会重复处理。
"""
import csv
import hashlib
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, ".probe"))
OUT = os.path.join(BASE, "out", "wechat")
STEPS = os.path.join(OUT, "steps")
LOG = os.path.join(BASE, "out", "wechat_add.log")
os.makedirs(STEPS, exist_ok=True)

import win_io as w  # noqa: E402
import ocr  # noqa: E402
import nick_rules  # noqa: E402  规则7 词表（与 A / C 阶段共用，无副作用模块）

NOT_FOUND_KW = ("用户不存在", "无法找到", "没有找到", "找不到相关账号", "找不到相关内容",
                "请检查", "不存在", "找不到")
# 「被搜账号状态异常，无法显示」（2026-09-23 用户截图确认，要求**跳过**）
#   ≠ 找不到该用户：账号存在但处于异常状态（封禁/注销中/隐私限制等），微信不给结果页，
#   以前落进 unknown 会**每轮无限重试**（实测 LYW00736 反复重试 5+ 次）。
ABNORMAL_KW = ("被搜账号状态异常", "账号状态异常")
# 已是好友 -> 结果页是好友资料卡：有「发消息/语音聊天/视频聊天」和「朋友资料/共同群聊」
ALREADY_KW = ("发消息", "发信息", "语音聊天", "视频聊天", "朋友资料", "共同群聊")
EXCLUDE_NICK_KW = ("稿费",)
APPLY_TITLE = "申请添加朋友"
ADD_TITLE = "添加朋友"
# 微信风控提示 —— 一旦出现立即停止整个流程
RISK_KW = ("操作过于频繁", "请稍后再试", "稍后再试", "操作频繁", "过于频繁", "请稍后重试")
# 计入台账「已完成」的状态：这些达人以后不再重试
#   sent=已发申请 / already=已是好友 / excluded=命中排除词(稿费) / not_found=搜不到
#   abnormal=被搜账号状态异常（2026-09-23 用户要求：跳过）
# 不计入：unknown(结果页无法识别)、error、risk_control -> 下次会重试
DONE_STATUS = ("sent", "already", "excluded", "not_found", "abnormal")

# 【截图来源】2026-09-22 晚 **修正版**（此前的 auto 兜底是错的，已撤）
#   screen（默认）：只用屏幕级 BitBlt —— 正常路径
#   print         ：强制走窗口级 PrintWindow —— **仅手动**用于「屏幕已解锁但窗口被完全遮挡」
#
# 🔴 2026-09-22 21:13 实测翻车记录（勿走回头路）：
#   会话锁屏时屏幕级截图全黑，当时加了「全黑就自动改用 PrintWindow」的兜底；
#   结果 PrintWindow 返回的是**冻结帧** —— 该轮 10 张搜索截图 **8 张逐像素完全相同**
#   （md5 一致；9 分钟内 10 次不同搜索，窗口内容纹丝不动），10 个达人被**误判 not_found**
#   并写进台账（其中 6 个是本该能搜到的微信号）。
#   ⇒ 结论：**桌面全黑 = 锁屏/息屏 = 硬阻断，不绕**（见 precheck_desktop()）。
#     PrintWindow 在锁屏下「看起来有内容」，比「读不到」危险得多。
SHOT_MODE = (os.environ.get("WX_SHOT") or "screen").strip().lower()


def _is_blank(img):
    """整幅近黑 = 什么都没抓到（锁屏 / 无桌面 / 窗口没渲染）。"""
    try:
        lo, hi = img.convert("L").getextrema()
        return hi <= 8
    except Exception:
        return False


def norm_text(s):
    """OCR 文本归一化：转小写、只留字母数字（用于「搜索框写入校验」比对）。

    OCR 对下划线/点/连字符时好时坏，所以比对前先去掉非字母数字字符。
    """
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


FREEZE_LIMIT = 2      # 连续相同几次即判定冻结（含本次共 3 张结果图）


def freeze_step(cur_md5, last_md5, streak):
    """冻结帧检测的一步。返回 (新 streak, 是否判定为冻结)。

    连续 3 张结果图逐像素相同 ⇒ 窗口根本没在渲染（streak >= FREEZE_LIMIT）。
    纯函数、单机可测，见 .probe/test_wechat_guard.py。
    """
    if cur_md5 and cur_md5 == last_md5:
        streak += 1
    else:
        streak = 0
    return streak, streak >= FREEZE_LIMIT


MULTI_FRAME_MIN_IDX = 5      # 同轮至少处理这么多个才做「多帧」判定


def multi_frame_frozen(idx, seen_md5):
    """同轮「多帧交替」守卫（2026-09-23 新增）。

    背景：当天 10 个**不同**微信号的搜索结果图只出现 **2 种**指纹（两帧交替），
    `freeze_step()` 要求的「连续 3 张完全相同」**正好抓不到**。
    同一轮里不同微信号的结果页不可能只有一两种指纹 ⇒ 同样按冻结帧处理。

    纯函数、单机可测，见 .probe/test_wechat_guard.py。
    """
    return idx >= MULTI_FRAME_MIN_IDX and len(seen_md5) <= 2


def precheck_desktop(hwnd):
    """跑 B 之前的硬体检。返回 (ok, reason)。

    桌面截图全黑 ⇒ 锁屏 / 息屏 ⇒ **拒绝执行**（ok=False，run() 必须直接退出、
    不写任何台账）。理由是上面的翻车记录：锁屏下 PrintWindow 会返回冻结帧。
    """
    try:
        img = w.screenshot_window(hwnd)
    except Exception as e:
        return False, "屏幕截图异常：%s" % str(e)[:80]
    if img is None or getattr(img, "width", 0) < 10:
        return False, "屏幕截图失败（窗口句柄可能已失效），请确认微信窗口还在"
    if _is_blank(img):
        return False, ("桌面截图**全黑** —— 会话已锁屏/息屏，微信窗口不渲染。"
                       "此时任何抓图都可能是冻结帧，宁可不开跑。请**解锁屏幕**后重跑。")
    return True, ""


def grab_window(hwnd):
    """抓窗口画面，返回 (PIL.Image, 来源)。

    默认只走屏幕级 BitBlt。`WX_SHOT=print` 才强制 PrintWindow
    （手动场景：屏幕已解锁、但窗口被其它窗口**完全遮挡**时）。
    """
    if SHOT_MODE == "print":
        try:
            pi, ok = w.print_window(hwnd, 2)
            if ok and getattr(pi, "width", 0) > 10:
                return pi, "print"
        except Exception:
            pass
    return w.screenshot_window(hwnd), "screen"
RESULT_FILE = os.path.join(OUT, "add_results.json")
CSV_FILE = os.path.join(OUT, "add_results.csv")
# 台账状态 -> 给人看的中文标签（csv 用）
STATUS_LABEL = {
    "sent": "已发送",
    "already": "已是好友",
    "excluded": "命中排除词(跳过)",
    "not_found": "搜不到(跳过)",
    "abnormal": "账号状态异常(跳过)",
    "risk_control": "风控(停手)",
    "error": "出错(下轮重试)",
    "unknown": "无法识别(下轮重试)",
}
CSV_HEADER = ["状态", "达人名(备注)", "抖音达人", "联系方式", "类型", "地区", "粉丝"]


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


def export_csv(records=None):
    """把台账导出成给人看的 csv（utf-8-sig，Excel 双击打开不乱码）。

    历史坑：09-15 那份 add_results.csv 是旧版本一次性生成的，
    后来重构只写 json -> csv 悄悄过期（09-16 时它还停在 09-15 的数据），
    协作者会读到旧名单。现在 run() 里一并刷新，别让 csv 再变成陷阱。
    """
    if records is None:
        records = list(load_ledger().values())
    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(CSV_HEADER)
        for r in records:
            st = r.get("add_status") or "?"
            note = r.get("add_note") or ""
            # not_found/error 的 add_note 是报错文案，不是昵称 -> 不填「达人名(备注)」
            shown = note if st in ("sent", "already", "excluded") else ""
            wr.writerow([STATUS_LABEL.get(st, st), shown,
                         r.get("nickname") or "", r.get("contact") or "",
                         r.get("contact_type") or "", r.get("city") or "",
                         r.get("fans") or ""])
    return CSV_FILE


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
        # 截图来源见 grab_window()：默认屏幕级；`WX_SHOT=print` 才走 PrintWindow。
        # ⚠️ 锁屏下的全黑**不做兜底**（冻帧陷阱），由 precheck_desktop() 硬阻断。
        img, src = grab_window(self.win)
        if img is None:
            raise RuntimeError(
                "微信窗口截图失败（rect=%s）——窗口可能被最小化或被其他窗口完全遮挡"
                % (self.rect,))
        if getattr(img, "width", 0) <= 0 or getattr(img, "height", 0) <= 0:
            raise RuntimeError(
                "微信窗口截图失败（rect=%s）——窗口可能被最小化或被其他窗口完全遮挡"
                % (self.rect,))
        if src != getattr(self, "_last_src", None):
            self._last_src = src
            log("（截图来源切换为 %s）" % (
                "窗口级 PrintWindow（WX_SHOT=print 手动指定）" if src == "print"
                else "屏幕级 BitBlt"))
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
    # 标题 / 按钮等**非输入框**文字，绝不能被当成搜索框点击
    BOX_LABELS = ("添加朋友", "搜索", "搜素", "取消", "关闭")

    def search_row(self, items=None):
        """搜索框所在水平行 —— 与「搜索」按钮同一中线。返回 (cy, 按钮item)。

        🔴 2026-09-23 事故（务必保留这段历史）：
        原来挑搜索框用「cy<135 且 w>40，取最左」。
        当天窗口里残留了短文本「18」（OCR 宽 31px < 40）→ 被过滤掉 →
        候选只剩**标题「添加朋友」**→ 点到标题栏 → Ctrl+A/DELETE/粘贴全进不了输入框 →
        搜索框内容 10 次纹丝不动 → 读到的一直是上一次的旧结果页 →
        10 个达人被逐条判 `not_found` 写进台账（not_found 属 DONE_STATUS = **永久跳过**）。
        当时的取证：10 张 `run_NN_search.png` 只有 2 种 md5，`run_10` 与 `run_01` 逐字节相同，
        且截图里搜索框内容仍是「18」；而单独 probe-search 一个**已知存在**的微信号也报搜不到。
        改用「与搜索按钮同高」定位后，与框内文字长短完全无关。
        """
        items = self.items() if items is None else items
        btn = ocr.find(items, "搜索", "搜素")
        return (btn["cy"] if btn else 113), btn

    def focus_search_box(self):
        items = self.items()
        cy, btn = self.search_row(items)
        right = (btn["cx"] - 40) if btn else 10 ** 9
        cand = [i for i in items
                if abs(i["cy"] - cy) <= 30 and i["cx"] < right
                and i["h"] < 50 and i["w"] > 8
                and not any(L in i["text"] for L in self.BOX_LABELS)]
        if cand:
            it = min(cand, key=lambda i: i["cx"])
            self.click_item(it)
        else:
            # 兜底：点搜索框几何位置，不依赖 OCR 是否读到框内文字
            self.click_abs(self.rect[2] // 3, cy)
        time.sleep(0.4)

    def box_text(self):
        """读回搜索框里当前的文字（用于校验输入是否真的写进去了）。"""
        items = self.items()
        cy, btn = self.search_row(items)
        right = (btn["cx"] - 40) if btn else 10 ** 9
        seg = [i for i in items
               if abs(i["cy"] - cy) <= 30 and i["cx"] < right
               and not any(L in i["text"] for L in self.BOX_LABELS)]
        seg.sort(key=lambda i: i["cx"])
        return "".join(i["text"] for i in seg).strip()

    def search(self, text):
        """清框 -> 粘贴 -> **轮询校验文字真的进了框** -> 点「搜索」。

        返回 True = 已发起搜索；False = 输入没写进搜索框
        （此时结果页毫无意义，调用方只能判 unknown，**绝不能判 not_found**）。
        """
        want = norm_text(text)
        for attempt in (1, 2):
            self.focus_search_box()
            w.send_keys(["CTRL", "A"])
            time.sleep(0.3)
            w.send_keys(["DELETE"])
            time.sleep(0.5)
            w.paste_text(text)
            # ⚠️ 2026-09-23：本机（远程桌面 3840x2160）输入/重绘延迟可达 1~2 秒，
            #    固定 sleep(1.0) 会把「其实写进去了」误判成失败；改成轮询最多等 6 秒。
            got = ""
            for _ in range(12):
                time.sleep(0.5)
                got = self.box_text()
                if want and want in norm_text(got):
                    break
            if want and want in norm_text(got):
                break
            log("  ! 搜索框写入校验失败（期望 %s / 框内实际 %r）第 %d 次"
                % (text, got, attempt))
            if attempt == 2:
                return False
        if not self.click_text("搜索", exact=True):
            w.send_keys(["ENTER"])
        time.sleep(3.2)
        return True

    # ---------- 读结果页 ----------
    def read_result(self, shot_name=None):
        img = self.shot(shot_name)
        items = ocr.ocr(img)
        rc = ocr.find(items, *RISK_KW)
        if rc:
            return "risk_control", rc["text"], items, img
        # 「被搜账号状态异常，无法显示」要在 not_found 之前判（用户要求：跳过、不重试）
        ab = ocr.find(items, *ABNORMAL_KW)
        if ab:
            return "abnormal", ab["text"], items, img
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
    it = ocr.find(ocr.ocr(grab_window(ah)[0]), "取消", exact=True)
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
    hit = ocr.find(ocr.ocr(grab_window(ah)[0]), *RISK_KW)
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
    img = grab_window(ah)[0]
    img.save(os.path.join(STEPS, "run_%02d_apply.png" % idx))
    before_items = ocr.ocr(img)
    before_txt = "".join(i["text"] for i in before_items if i["cy"] < 330)
    xy = _find_fill_btn(img, before_items)
    if xy:
        _click_rel(arect, xy[0], xy[1])
        time.sleep(1.6)
        img2 = grab_window(ah)[0]
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
    img = grab_window(ah)[0]
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
    img = grab_window(ah)[0]
    img.save(os.path.join(STEPS, "run_%02d_ready.png" % idx))
    items = ocr.ocr(img)
    if dry:
        it = ocr.find(items, "取消", exact=True)
        if it:
            _click_rel(arect, it["cx"], it["cy"])
        time.sleep(1.5)
        try:
            grab_window(ah)[0].save(os.path.join(STEPS, "run_%02d_after_cancel.png" % idx))
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
        grab_window(ah)[0].save(os.path.join(STEPS, "run_%02d_after_ok.png" % idx))
    except Exception:
        pass
    return "sent"


def _drop_nick_excluded(cand):
    """【规则7 复核】把「昵称命中排除词」的候选剔除，返回 (保留, [(昵称, 命中词), ...])。

    为什么不靠 A 阶段一次筛干净：
      · 词表是**会长**的（2026-09-17 用户又加了 香港/假发/美甲/酒/染发/男士… 10 个），
        而 `darens.json` 是上一次 A 阶段跑出来的**旧名单**，不会自动重筛；
      · B 阶段的好友申请**发出去就撤不回**，所以宁可在这一步多挡一道。
    词表实体在 `nick_rules.py`（纯数据+纯函数），A/B/C 三个阶段共用同一份。
    走的是 `nick_rules.nick_exclude_reason()` —— 它包含**排除词 + 纯数字昵称**两个维度；
    别单独调 `nick_exclude_kw_hit()`，否则新维度会漏掉 B 阶段。
    """
    keep, out = [], []
    for d in cand:
        why = nick_rules.nick_exclude_reason(d.get("nickname") or "")
        if why:
            out.append((d.get("nickname") or "", why))
        else:
            keep.append(d)
    return keep, out


# 【手机号达人】2026-09-22 新增：`contact_type == "手机"` 的候选人**默认跳过**。
#   实测台账里手机号 **23/23 全部 not_found**（微信不支持按手机号精确搜好友），
#   而且飞书只登记微信号（`feishu_sync` 只收 `contact_type == "微信"`）——
#   跑它们是纯浪费（每个约 10 秒）并污染 not_found 统计。
#   想照旧硬试：`SKIP_PHONE=0`。
SKIP_PHONE = os.environ.get("SKIP_PHONE", "1").lower() not in ("0", "false", "no", "off", "")


def _drop_phone(cand):
    """把手机号候选人剔除，返回 (保留, [昵称...])。`SKIP_PHONE=0` 时原样返回。"""
    if not SKIP_PHONE:
        return cand, []
    keep = [d for d in cand if (d.get("contact_type") or "") != "手机"]
    out = [d.get("nickname") or "" for d in cand
           if (d.get("contact_type") or "") == "手机"]
    return keep, out


def run(limit=0, dry=False):
    open(LOG, "w", encoding="utf-8").close()
    src = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
    ledger = load_ledger()
    cand = [d for d in src if d.get("contact")]
    # 手机号达人默认跳过（见 _drop_phone 注释；SKIP_PHONE=0 可关）
    cand, phone_out = _drop_phone(cand)
    if phone_out:
        log("跳过 %d 个手机号达人（手机号一律搜不到、飞书也只登微信号）：%s" % (
            len(phone_out), " | ".join(n[:14] for n in phone_out[:8])))
    # 【规则7 复核】昵称命中排除词的直接丢掉 ——
    #   词表可能是在 A 阶段跑完之后才追加的（如 2026-09-17 加的那 10 个），
    #   旧名单不会自动重筛，所以 B 阶段必须再用**现行**词表挡一道，
    #   否则不该加的达人照样会被发出好友申请（不可撤销）。
    cand, nick_out = _drop_nick_excluded(cand)
    todo = [d for d in cand
            if (ledger.get(d.get("uid")) or {}).get("add_status") not in DONE_STATUS]
    skipped = len(cand) - len(todo)
    if limit:
        todo = todo[:limit]
    log("候选 %d 个（已处理跳过 %d 个）-> 本轮待加 %d 个%s" % (
        len(cand), skipped, len(todo), "（dry 模式）" if dry else ""))
    if nick_out:
        log("其中 %d 个因**昵称命中排除词**被剔除：%s" % (
            len(nick_out), " | ".join("%s(%s)" % (n[:16], h) for n, h in nick_out[:10])))
    if not todo:
        log("没有待加好友了（全部已处理）")
        return

    wx = WeChat()
    wx.ensure_front()
    log("添加朋友窗口 rect=%s" % (wx.rect,))

    # 🔴 前置体检（2026-09-22 21:13 教训）：桌面全黑 = 锁屏/息屏 ⇒ 直接不跑，
    #    且**不写任何台账**。锁屏时窗口"存在"但根本不渲染，硬跑会写出错误的
    #    sent/not_found（比不跑更糟）。
    ok, why = precheck_desktop(wx.win)
    if not ok:
        log("!! 前置体检未通过：%s" % why)
        log("!! 本轮**未执行任何操作、未写台账**。解锁屏幕（并让微信窗口可见）后重跑即可。")
        return
    log("前置体检通过：桌面截图正常（非全黑）")

    results = []
    stop_reason = ""
    last_md5 = ""
    frozen_streak = 0
    seen_md5 = set()        # 本轮出现过的结果图指纹（见下面「多帧交替」守卫）
    for idx, d in enumerate(todo, 1):
        nick, contact = d["nickname"], d["contact"]
        st, note = "unknown", ""
        try:
            dismiss_apply_dialog()          # 清掉上一轮遗留的申请页
            wx.ensure_front()
            if not wx.search(contact):
                # 2026-09-23：输入没写进搜索框 -> 读到的必然是旧画面，只能判 unknown
                st, note = "unknown", "搜索框写入失败"
                log("  [%d/%d] %-18s 搜索框写入失败 -> 判 unknown（不写 not_found，下轮重试）"
                    % (idx, len(todo), nick[:16]))
                results.append({**d, "add_status": st, "add_note": note})
                time.sleep(1.2)
                continue
            st, shown, items, res_img = wx.read_result("run_%02d_search" % idx)

            # 🔴 冻结帧守卫（2026-09-22 21:13 教训）：窗口没在渲染时，抓到的图可能
            #    完全不动 —— 连续 3 张搜索结果图逐像素相同 ⇒ 判定冻结，本轮结果全部作废。
            #    真实场景下不同微信号的搜索结果页**不可能**逐像素一致。
            try:
                cur_md5 = hashlib.md5(res_img.tobytes()).hexdigest()
            except Exception:
                cur_md5 = ""
            frozen_streak, is_frozen = freeze_step(cur_md5, last_md5, frozen_streak)
            if cur_md5:
                last_md5 = cur_md5
                seen_md5.add(cur_md5)
            if is_frozen:
                log("!! 连续 %d 张搜索结果图**逐像素完全相同** -> 判定为冻结帧（窗口未渲染）"
                    % (frozen_streak + 1))
                log("!! 冻结帧会把 sent/not_found 判错（比不跑更糟）-> 本轮结果**全部作废、不写台账**")
                log("!! 请检查：屏幕是否已解锁/亮屏、微信窗口是否正常显示；修好后重跑。")
                return

            # 🔴 2026-09-23 事故补充守卫：当天 10 个**不同**微信号的搜索结果图只出现 2 种
            #    （两帧交替）—— 上面「连续 3 张相同」的守卫**正好抓不到**。
            #    同一轮里不同微信号的结果页不可能只有一两种指纹，所以再兜一道。
            if multi_frame_frozen(idx, seen_md5):
                log("!! 本轮 %d 个不同微信号的搜索结果图只出现 %d 种 -> 判定冻结帧（多帧交替）"
                    % (idx, len(seen_md5)))
                log("!! 本轮结果**全部作废、不写台账**；先查搜索框是否真的写进去了（search() 已加校验）")
                return

            if st == "risk_control":
                # 微信风控 —— 立即停止整个流程
                note = shown
                log("  [%d/%d] %-18s 微信风控「%s」-> 停止操作" % (
                    idx, len(todo), nick[:16], shown))
                close_risk_dialog(items, wx)
            elif st == "abnormal":
                # 「被搜账号状态异常，无法显示」—— 账号存在但异常，重试也不会变，直接跳过
                note = shown
                log("  [%d/%d] %-18s 被搜账号状态异常 -> 跳过（不再重试）" % (
                    idx, len(todo), nick[:16]))
            elif st == "not_found":
                # 🔴 2026-09-23：本机微信搜索**不稳定** —— 同一个微信号在不同时刻会给出
                #    found / not_found / unknown 三种答案。当天两次实测各误判 10 条 / 5 条
                #    「搜不到」（其中 ifeelgrace 等 7 条单独复测均能找到），而 not_found
                #    属 DONE_STATUS = **永久跳过**，误判代价极大。
                #    ⇒ not_found 必须**独立复核一次**：两次都搜不到才认定，否则判 unknown 下轮重试。
                log("  [%d/%d] %-18s 搜不到 -> 独立复核一次（防误判）" % (idx, len(todo), nick[:16]))
                time.sleep(1.2)
                if wx.search(contact):
                    st2, _shown2, _it2, _img2 = wx.read_result(None)
                else:
                    st2 = "search_failed"
                if st2 == "not_found":
                    log("  [%d/%d] %-18s 复核确认搜不到 -> not_found" % (idx, len(todo), nick[:16]))
                else:
                    log("  [%d/%d] %-18s 复核不一致（%s）-> 判 unknown，不写 not_found"
                        % (idx, len(todo), nick[:16], st2))
                    st, note = "unknown", "复核不一致: %s" % st2
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
    export_csv(list(merged.values()))
    if stop_reason:
        log("停止原因：%s" % stop_reason)
    from collections import Counter
    log("=" * 60)
    log("结果统计: %s" % dict(Counter(r["add_status"] for r in results)))
    left = [d for d in cand if (merged.get(d.get("uid")) or {}).get("add_status")
            not in DONE_STATUS]
    log("累计台账 %d 条；剩余待加 %d 个" % (len(merged), len(left)))
    # 固定收尾提醒（用户 2026-09-17 定：跑完 B 必须把信息登记到飞书）
    log("👉 收尾：请跑 feishu_sync.py 把本轮结果登记到飞书多维表格（更新「状态」列）")


def status():
    """打印台账与剩余待加数量。"""
    src = json.load(open(os.path.join(BASE, "out", "collect", "darens.json"), encoding="utf-8"))
    ledger = load_ledger()
    cand = [d for d in src if d.get("contact")]
    # 与 run() 保持一致：手机号默认跳过
    cand, phone_out = _drop_phone(cand)
    # 与 run() 保持一致：先过一遍规则7，否则 status 会列出**实际不会加**的人
    # （曾出现「status 说待加 25 个，run 只加 22 个」的迷惑现象）
    cand, nick_out = _drop_nick_excluded(cand)
    left = [d for d in cand if (ledger.get(d.get("uid")) or {}).get("add_status")
            not in DONE_STATUS]
    from collections import Counter
    log("候选达人 %d 个 / 台账 %d 条 / 剩余待加 %d 个" % (len(cand), len(ledger), len(left)))
    if phone_out:
        log("（另有 %d 个手机号达人默认不计入待加，如需硬试：SKIP_PHONE=0）" % len(phone_out))
    if nick_out:
        log("（另有 %d 个因昵称命中排除词不计入待加：%s）" % (
            len(nick_out), " | ".join("%s(%s)" % (n[:14], h) for n, h in nick_out[:10])))
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
    elif mode == "csv":
        log("已导出 %s（%d 条）" % (export_csv(), len(load_ledger())))
    else:
        print(__doc__)
