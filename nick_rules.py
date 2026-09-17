# -*- coding: utf-8 -*-
"""昵称排除词（**无副作用**的独立模块）—— 阶段 A / B / C 共用同一份词表。

为什么要单独一个文件：
  · `collect.py` 在 import 时就会 `sys.stdout = io.TextIOWrapper(...)`，
    别的脚本 import 它会把 stdout 换掉（踩过：「I/O operation on closed file」）。
  · 但「昵称命中排除词就跳过」这条规则**必须三个阶段一致**：
    A 阶段用它筛人，B 阶段（微信加好友）和 C 阶段（登记飞书）也要再挡一道，
    否则改规则前跑出来的旧名单会把不该要的达人带进微信和飞书表。
  → 所以把纯数据 + 纯函数放这里，谁都能安全 import。

词表可用环境变量 `NICK_EXCLUDE_KW`（逗号分隔）整体覆盖。
"""
import os

# 【规则7】昵称命中以下词 -> 排除（渠道 / 供应链 / 机构 / 品牌号特征）
#   用户 2026-09-17 追加 10 个：「如果达人名字含 香港、工厂直销、找工作、智慧服务、
#   假发、美甲、酒、染发、男士、妇炎洁，都跳过」
#   用户 2026-09-17 再追加 3 个：「睫毛、香水、源头」任意一个也排除
#     · 睫毛 / 香水 —— 属**禁忌品类关键词**（睫毛增长液、香水均非目标类目），
#       名字里直接带这些词的号基本是垂直铺货号，挡在入口最省事。
#     · 源头 —— 「源头工厂 / 源头直供 / 源头好货」= 供应链号特征词。
#   ⚠️ 两个词偏宽，误伤风险已知并接受（用户明确要求）：
#      · 「酒」—— 也会命中「酒精」「酒店」（如「XX酒精湿巾」会被排除）
#      · 「男士」—— 女性达人做男士品类的号也会被排除（如「男士护肤严选」）
NICK_EXCLUDE_KW = tuple(
    x.strip() for x in os.environ.get(
        "NICK_EXCLUDE_KW",
        "国际,全球,美业,供应链,折扣,厂家,大牌,养发,集团,防晒,"
        "香港,工厂直销,找工作,智慧服务,假发,美甲,酒,染发,男士,妇炎洁,"
        "睫毛,香水,源头",
    ).split(",") if x.strip()
)


def norm_name(n):
    """昵称归一化：只留中英文数字并转小写（去 emoji / 空格 / 符号）。"""
    return "".join(ch for ch in (n or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff").lower()


def nick_exclude_kw_hit(nick):
    """昵称是否命中排除词；命中返回该词，否则返回 ''。"""
    n = norm_name(nick)
    if not n:
        return ""
    return next((kw for kw in NICK_EXCLUDE_KW if norm_name(kw) in n), "")
