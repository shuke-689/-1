# -*- coding: utf-8 -*-
"""阶段 A 正式采集：抖音精选联盟「找达人」按条件采集达人 + 联系方式。

【已实测的页面交互】
  主推类目：直接可见的多选按钮 a.auxo-btn.auxo-btn-tertiary（点父项弹 auxo-cascader 面板，
            面板第一项「不限」= 整个大类）
  结算总额 / 粉丝量：点击 div.auxo-form-item → 弹 .auxo-select-dropdown
                    → 点 .auxo-select-item-option-content（FIND_FORMITEM_JS 精确匹配）
  有联系方式：点击 div.auxo-form-item 直接切换

筛选条件：
  【规则1】主推类目 = 个护家清 / 美妆（级联面板里选「不限」）
          双类目分两批跑（见 collect_30.py）：15 个个护家清 + 15 个美妆
          放行的类目组合（用户 2026-09-15 最新口径）：
            个护家清｜个护家清+美妆｜美妆｜个护家清+服饰内衣｜
            个护家清+母婴宠物｜个护家清+运动户外
            且「个护家清/美妆/服饰内衣/母婴宠物/运动户外」命中 >= 2 个时，
            第三个及以后的类目**不做任何限制**
            （如 个护家清/母婴宠物/食品饮料 ✔、个护家清/美妆/食品饮料 ✔）
  【规则2】结算总额 = 1w-10w   ← 用户 2026-09-15 由「视频结算总额」改为「结算总额」
          字段 common_range_selection_author_sale_gmv_30d_settle
          （近30天所有带货来源，不限定直播/短视频）
  粉丝量 = 10w以下
  有联系方式 = 勾选
本地过滤：
  性别 = 女(gender==2)
  排除地区：海南 / 新疆 / 西藏 / 境外
  【规则4】主推类目(author_tag.main_cate)必须命中「个护家清」或「美妆」其一；
          目标词条（个护家清/美妆/服饰内衣/母婴宠物/运动户外）命中 >= 2 个 -> 第三个不限；
          只命中 1 个时，带以下 18 个搭档类目之一即排除：
          食品饮料 / 滋补保健 / 宠物 / 图书教育 / 生鲜 / 本地生活 / 酒 /
          智能家居 / 玩具乐器 / 鲜花园艺 / 3C数码家电 / 鞋靴箱包 / 虚拟充值 /
          钟表配饰 / 珠宝文玩 / 医疗健康 / 原料包装 / 餐饮外卖
  【规则6】达人内容类型(author_tag.author_label_rec_reasons[].reason)不得命中：
          三农 / 公益 / 人文社科 / 二次元 / 医疗健康 / 动物 / 教育校园 / 汽车 /
          游戏 / 生活家居 / 社会时政 / 科技 / 科普 / 美食 / 职场 / 财经
  【规则7】昵称命中排除词：国际 / 全球 / 美业 / 供应链 / 折扣 / 厂家 / 大牌 /
          养发 / 集团 / 防晒；或带品牌号特征词（官方/旗舰/专卖/授权/正品/品牌…）
          或命中品牌词表（蜜丝婷、百雀羚、云南白药…）-> 排除
  昵称标准化后去重
数量限制：
  【规则5】取满 TARGET_DAREN 个「有效达人」（成功取到联系方式的）即停止筛选
达人主页：
  跳 /dashboard/servicehall/daren-profile?uid=<uid>
  【规则3】**必须先点「带货分析」tab**，读「商品信息」+「店铺信息」两列：
      3a 同品牌：按品牌聚类（店名去店型后缀 -> 公共前缀 >=2 字视为同品牌）
      **同一品牌占比 >= SAME_BRAND_RATIO（默认 50%）且严格过半 -> 跳过该达人**
      多家品牌（最大占比 < 50%，或打平）-> 继续
      3b 禁忌商品：商品名含 假发 / 院线 / 美甲 -> **跳过该达人**
      ⚠️ tab 点不到 / 商品数据拿不到 = **未判定 -> 直接跳过该达人**，
         绝不"未判定就进入查微信"（用户 2026-09-15 明确要求的纠错）
  【规则7b】若昵称命中该达人自己的带货品牌名 -> 跳过（动态品牌判定，不依赖静态词表）
  取「达人微信号」行（无则退「达人手机号」行）→ 点眼睛 → 取值

产出（OUT_TAG 为空时即 darens.json / darens.csv / darens.xlsx）：
  out/collect/darens<tag>.json   全字段明细
  out/collect/darens<tag>.csv    清洗后可读表
  out/collect/darens<tag>.xlsx   **Excel 登记表**（用户要求的 7 列）：
      达人名称 / 达人微信 / 达人粉丝 / 销售总额 / 直播结算总额 / 视频结算总额 / 图文结算总额
日志 out/collect<tag>.log
"""
import csv
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out", "collect")
PROFILE = os.path.join(BASE, ".edge-auto", "profile")
# 双类目分批采集（15 个护家清 + 15 美妆）时用 OUT_TAG 区分输出，避免互相覆盖
OUT_TAG = os.environ.get("OUT_TAG", "")
LOG = os.path.join(BASE, "out", "collect%s.log" % OUT_TAG)
os.makedirs(OUT, exist_ok=True)

DAREN = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
PROFILE_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=%s&enter_from=1&scene=1&author_type=1"

MAX_CANDIDATE = int(os.environ.get("MAX_CANDIDATE", "150"))  # 候选达人的安全上限
MAX_SCROLL = int(os.environ.get("MAX_SCROLL", "16"))         # 每轮最多翻几屏
# 调试开关：把列表接口的原始响应 dump 成 out/collect/apis<tag>.json
DUMP_APIS = os.environ.get("DUMP_APIS", "") not in ("", "0", "false", "False")
# 请求降速 / 限流退避（抖音精选联盟 square_pc_api 过密会返回 11001 请求过于频繁）
DAREN_PAUSE = float(os.environ.get("DAREN_PAUSE", "2.0"))      # 每个达人主页之间的间隔秒
RATE_BACKOFF = int(os.environ.get("RATE_BACKOFF", "90"))       # 命中限流后的退避秒数
SCROLL_PAUSE = float(os.environ.get("SCROLL_PAUSE", "2.8"))    # 每屏滚动后的等待秒
# 【规则5】取满多少个「有效达人」（成功取到联系方式）即停止筛选
TARGET_DAREN = int(os.environ.get("TARGET_DAREN", "30"))

# 【登录策略】用户 2026-09-16 定：**跳过自动登录环节**。
# 达人广场检测到未登录时**不中止**，而是在原地等待使用者在**已打开的 Edge 窗口**里
# 手动登录（会话持久化在 .edge-auto/profile，下次无需重复），检测到即自动继续。
#   LOGIN_WAIT_SEC=600   等待上限（秒）；设 0 = 不等待，检测到未登录立刻按退出码 3 退出
#   LOGIN_POLL_SEC=5     轮询间隔（秒）
LOGIN_WAIT_SEC = int(os.environ.get("LOGIN_WAIT_SEC", "600"))
LOGIN_POLL_SEC = float(os.environ.get("LOGIN_POLL_SEC", "5"))
# 登录后达人广场才会出现的字样（与 login.py 保持一致）
LOGGED_IN_MARK = ("主推类目", "找达人", "按商品找达人")
# 官方登录页：实测在抖音电商 marketing 落地页上点「登录」**不出二维码**，
# 所以未登录时直接把使用者送到这个地址（与 login.py 的兜底一致）
LOGIN_URL = os.environ.get("LOGIN_URL", "https://buyin.jinritemai.com/login")

# 【筛选】结算总额 —— 用户 2026-09-15 由「视频结算总额」改为「结算总额」
# 字段名（实测自 /square_pc_api/square/filter）：
#   结算总额       common_range_selection_author_sale_gmv_30d_settle  （tooltip: 近30天达人所有带货来源的总结算额）
#   直播结算总额   common_range_selection_live_sales_30d_settle
#   视频结算总额   common_range_selection_video_sales_30d_settle
#   图文结算总额   common_range_selection_picture_sales_30d_settle
#   橱窗结算总额   common_range_selection_window_sales_30d_settle
#   场均结算额     common_range_selection_author_square_average_gmv_settle
# 注意：FIND_FORMITEM_JS 是**精确匹配**，所以「结算总额」不会误撞到「视频结算总额」。
# 区间选项文本：1w以下 / 1w-10w / 10w-100w / 100w-500w / 500w-1000w / 1000w以上
SALE_LABEL = os.environ.get("SALE_LABEL", "结算总额")
SALE_OPTION = os.environ.get("SALE_OPTION", "1w-10w")

# 【规则1】主推类目 = 「个护家清」（级联菜单里选「不限」= 整个个护家清大类）
# 如需只取某个子类目，设 CATE_CHILD=个人护理 / 家清纸品
# 用户 2026-09-15 追加：类目再加「美妆」（同样选「不限」），最终 15 个护家清 + 15 美妆
CATE_PARENT = os.environ.get("CATE_PARENT", "个护家清")
CATE_CHILD = os.environ.get("CATE_CHILD", "不限")
CATES = ((CATE_PARENT, CATE_CHILD),)

# 规则3：带货商品全部来自同一家 -> 跳过该达人
# 店铺名归一化后缀（用于取品牌名做同源判断）
SHOP_SUFFIX = ("官方海外旗舰店", "官方旗舰店", "旗舰店", "专卖店", "专营店", "企业店",
               "个体店", "自营店", "官方店", "工厂店", "选品店", "优品", "好物",
               "优选", "严选", "精选", "专柜", "名品", "小店", "店")

# 【规则4】主推类目（author_tag.main_cate 是**顶级类目数组**，
#        实测形如 ["个护家清","服饰内衣","美妆"]）
#   —— 用户 2026-09-15 最新口径：
#     ① 必须命中「个护家清」或「美妆」之一；
#     ② 目标类目词条 = 个护家清 / 美妆 / 服饰内衣 / 母婴宠物 / 运动户外：
#        · 命中 >= 2 个 -> 直接通过，**第三个及以后的类目不做任何限制**
#          （例：个护家清/母婴宠物/食品饮料 ✔，个护家清/美妆/食品饮料 ✔）
#        · 只命中 1 个 -> 再查是否带下方 18 个被排除的搭档类目，带了就排除
#          （例：个护家清 ✔；美妆 ✔；个护家清/食品饮料 ✘）
#     最终放行组合：个护家清｜个护家清+美妆｜美妆｜个护家清+服饰内衣｜
#                  个护家清+母婴宠物｜个护家清+运动户外
CATE_TARGETS = ("个护家清", "美妆", "服饰内衣", "母婴宠物", "运动户外")
CATE_MUST_ANY = ("个护家清", "美妆")
# 只命中 1 个目标类目时，出现以下任一类目即排除（18 项）
CATE_EXCLUDE_PARTNER = (
    "食品饮料", "滋补保健", "宠物", "图书教育", "生鲜", "本地生活", "酒",
    "智能家居", "玩具乐器", "鲜花园艺", "3C数码家电", "鞋靴箱包", "虚拟充值",
    "钟表配饰", "珠宝文玩", "医疗健康", "原料包装", "餐饮外卖",
)

# 【规则3b】带货商品名称命中以下词 -> 排除该达人（用户 2026-09-15 追加）
PRODUCT_EXCLUDE_KW = ("假发", "院线", "美甲")

# 【规则6】达人内容类型（author_tag.author_label_rec_reasons[].reason，覆盖率 100%）
#        不得属于以下类型（任一带命中即排除）
#        注意：用户口语「人文」= 平台正式名「人文社科」
CONTENT_EXCLUDE = (
    "三农", "公益", "人文社科", "二次元", "医疗健康", "动物", "教育校园", "汽车",
    "游戏", "生活家居", "社会时政", "科技", "科普", "美食", "职场", "财经",
)

# 【规则7】昵称命中以下词 -> 排除（渠道 / 供应链 / 机构 / 品牌号特征）
NICK_EXCLUDE_KW = ("国际", "全球", "美业", "供应链", "折扣", "厂家",
                   "大牌", "养发", "集团", "防晒")

# 【规则7b】昵称带品牌名 -> 排除
#   ① 号名里出现这些词，基本可判定是「品牌号 / 店铺号 / 渠道号」
NICK_BRAND_HINT = ("官方", "旗舰", "专卖", "专营", "授权", "正品", "品牌",
                   "总代", "总经销", "企业号", "官方号", "品牌店")
#   ② 常见 个护家清 / 美妆 / 日化 品牌词表（命中即排除；可持续补充）
BRAND_KW = (
    # 洗护发 / 身体护理
    "蜜丝婷", "海飞丝", "潘婷", "飘柔", "沙宣", "清扬", "力士", "多芬", "舒肤佳",
    "六神", "蜂花", "阿道夫", "滋源", "拉芳", "蒂花之秀", "隆力奇", "雨洁",
    "美涛", "章华", "迪彩", "半亩花田", "蔻斯汀", "卡诗", "施华蔻", "资生堂",
    "丝蓓绮", "水之密语", "惠润", "植观", "三谷", "睿嫣", "吕牌", "欧莱雅",
    "凡士林", "妮维雅", "旁氏", "玉兰油", "olay", "强生", "舒蕾", "索芙特",
    "澳雪", "京润珍珠", "所望", "蔻姬", "蔻赛", "阿蜜浓", "高姿", "水密码",
    # 口腔
    "云南白药", "黑人", "好来", "高露洁", "佳洁士", "狮王", "皓乐齿", "参半",
    "usmile", "舒客", "冷酸灵", "竹盐", "中华牙膏", "六必治", "齿研", "贝医生",
    # 女性护理 / 纸品
    "苏菲", "护舒宝", "七度空间", "高洁丝", "洁婷", "花王", "乐而雅", "自由点",
    "薇尔", "奈丝公主", "全棉时代", "心相印", "维达", "洁柔", "得宝",
    "斑布", "五月花", "洁云", "植护", "润本",
    # 家清
    "蓝月亮", "立白", "超能", "威露士", "滴露", "威猛先生", "威王", "妙洁",
    "家安", "白猫", "亮净", "净安", "奥妙", "汰渍", "碧浪", "花木星球", "当妮",
    "金纺", "开米", "妈妈壹选", "好爸爸", "蔬果园", "绿伞", "优洁士",
    # 美妆 / 护肤
    "完美日记", "花西子", "毛戈平", "珀莱雅", "可复美", "敷尔佳", "韩束",
    "一叶子", "自然堂", "伽蓝", "丸美", "佰草集", "相宜本草", "百雀羚",
    "郁美净", "薇诺娜", "玉泽", "理肤泉", "雅漾", "修丽可", "兰蔻", "雅诗兰黛",
    "倩碧", "科颜氏", "sk-ii", "悦诗风吟", "雪花秀", "兰芝", "迪奥", "圣罗兰",
    "香奈儿", "卡姿兰", "玛丽黛佳", "橘朵", "酵色", "稚优泉", "彩棠", "烙色",
    "方里", "蜜丝佛陀", "露华浓", "美宝莲", "欧诗漫", "养生堂", "森田", "肌司研",
    "芙丽芳丝", "珂润", "优色林", "至本", "米蓓尔", "溪木源", "逐本", "芳珂",
    "绽妍", "可丽金", "斐思妮", "创尔美", "御泥坊", "膜法世家", "美即", "韩后",
    "春纪", "温碧泉", "京润", "片仔癀", "马应龙", "南京同仁堂", "同仁堂",
    "unny", "veve", "novo", "funnyelves", "akf", "bob", "ushine",
)

# 地区过滤：这些地区直接排除
EXCLUDE_REGION = ("海南", "新疆", "西藏", "香港", "澳门", "台湾", "海外", "国外")
CN_PROVINCE = ("北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
               "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
               "湖北", "湖南", "广东", "广西", "重庆", "四川", "贵州", "云南",
               "陕西", "甘肃", "青海", "宁夏")


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


sys.path.insert(0, BASE)
import darens_io          # noqa: E402  （输出 json/csv/xlsx 的公共模块）


def write_outputs(records, tag=""):
    return darens_io.write_outputs(records, OUT, tag, log=log)


# ---------------- 页面扫描 / 交互 JS ----------------
SCAN_JS = """() => {
    const rect = e => { const r = e.getBoundingClientRect();
        return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
    const out = {rows: [], icons: []};
    document.querySelectorAll('*').forEach(e => {
        const t = (e.innerText||'').trim();
        if (!t || t.length > 60 || t.includes('\\n')) return;
        if (!/达人微信号|达人手机号/.test(t)) return;
        const r = e.getBoundingClientRect();
        if (r.width < 5 || r.height < 5) return;
        out.rows.push({cls:(e.className||'').toString().slice(0,110), text:t, rect:rect(e)});
    });
    document.querySelectorAll('span, i, div, svg, img, button').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 6 || r.height < 6 || r.width > 70 || r.height > 70) return;
        const cls = (e.className||'').toString();
        if (!/contact-item-btn|index__copy|icon-copy|copy|Copy|eye|Eye/.test(cls)) return;
        out.icons.push({tag:e.tagName, cls:cls.slice(0,110), rect:rect(e)});
    });
    return out;
}"""

FIND_FORMITEM_JS = """(name) => {
    let out = null;
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        out = {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
    });
    return out;
}"""

FIND_CATE_JS = """(name) => {
    // 坑：早先用固定 y 区间 [240,350] 圈定筛选栏，页面布局一变
    //（引导条 / 已选行出现与否）按钮就落到了区间外 -> 报「未找到类目按钮」。
    // 改法：只认 button/a.auxo-btn 的精确文本，**排除表格内的后代**（避免撞到达人列表里
    // 的类目文本），再按 y 从上到下排序，取最上面那个（筛选栏一定在顶部）。
    const out = [];
    document.querySelectorAll('button.auxo-btn, a.auxo-btn').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        let p = e, inTable = false;
        while (p && p !== document.body) {
            const t = p.tagName;
            if (t === 'TABLE' || t === 'THEAD' || t === 'TBODY' || t === 'TR' || t === 'TD') {
                inTable = true; break;
            }
            p = p.parentElement;
        }
        if (inTable) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 80) return;
        if (r.y < 0 || r.y > 1200) return;
        out.push({x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width),
                  h:Math.round(r.height), cls:(e.className||'').toString()});
    });
    out.sort((a, b) => a.y - b.y);
    return out;
}"""

# 诊断：列出所有可见的 auxo-btn 文本（类目按钮找不到时用来判断页面到底渲染成什么样）
LIST_CATE_BTNS_JS = """() => {
    const out = [];
    document.querySelectorAll('button.auxo-btn, a.auxo-btn').forEach(e => {
        const t = (e.innerText||'').trim();
        const r = e.getBoundingClientRect();
        if (!t || t.length > 20 || r.width < 20 || r.height < 10) return;
        out.push({t: t, x: Math.round(r.x), y: Math.round(r.y)});
    });
    return out.slice(0, 40);
}"""

DROPDOWN_JS = """() => {
    const dds = Array.from(document.querySelectorAll('.auxo-select-dropdown'))
        .filter(e => e.getBoundingClientRect().height > 10);
    if (!dds.length) return null;
    const dd = dds[dds.length - 1];
    const items = Array.from(dd.querySelectorAll('.auxo-select-item-option-content')).map(e => {
        const r = e.getBoundingClientRect();
        return {t:(e.innerText||'').trim(), x:Math.round(r.x), y:Math.round(r.y),
                w:Math.round(r.width), h:Math.round(r.height),
                selected: !!e.closest('.auxo-select-item-option-selected')};
    });
    const dr = dd.getBoundingClientRect();
    return {box:{x:Math.round(dr.x), y:Math.round(dr.y), w:Math.round(dr.width), h:Math.round(dr.height)},
            items: items};
}"""

# 级联菜单里的子类目（如「个护家清 -> 个人护理」）
FIND_CASCADER_JS = """(name) => {
    let out = null;
    document.querySelectorAll('li.auxo-cascader-menu-item, .auxo-cascader-menu-item').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 120) return;
        out = {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
               cls:(e.className||'').toString().slice(0,110)};
    });
    return out;
}"""

# 列出当前可见的级联菜单项（诊断用）
LIST_CASCADER_JS = """() => {
    const out = [];
    document.querySelectorAll('li.auxo-cascader-menu-item, .auxo-cascader-menu-item').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        out.push({t:(e.innerText||'').trim(), x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height)});
    });
    return out;
}"""

# 达人主页顶部 tab（概览 / 场景分析 / 粉丝分析 / 带货分析 / 评价详情）
# 主选择器 + 兜底：有些版本 tab 不是 auxo-tabs-tab 结构，就按「文本精确匹配 + 尺寸合理」找
FIND_TAB_JS = """(name) => {
    const out = [];
    const push = e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10 || r.height > 90) return;
        if (r.y < 0 || r.y > 1200) return;
        out.push({x:Math.round(r.x), y:Math.round(r.y),
                  w:Math.round(r.width), h:Math.round(r.height)});
    };
    document.querySelectorAll('div.auxo-tabs-tab-btn, div.auxo-tabs-tab').forEach(e => {
        if ((e.innerText||'').trim() === name) push(e);
    });
    if (out.length) return out;
    document.querySelectorAll('div,span,a,li').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        if (e.children.length > 1) return;
        push(e);
    });
    return out;
}"""

# 带货分析表格：实测列头 = 商品信息 | 店铺信息 | 到手价 | 结算额区间 |
#               销量区间 | 关联直播场次 | 关联短视频数
# 一次把「商品名 + 店铺名」都取回来：
#   店铺名 -> 规则3（同一品牌占比 >= 50% 则跳过）
#   商品名 -> 规则3b（含 假发 / 院线 / 美甲 -> 跳过）
SHOP_ROWS_JS = """() => {
    const tables = Array.from(document.querySelectorAll('table'));
    for (const tb of tables) {
        const r = tb.getBoundingClientRect();
        if (r.width < 300 || r.height < 50) continue;
        const heads = Array.from(tb.querySelectorAll('th')).map(e => (e.innerText||'').trim());
        const ti = heads.findIndex(h => h.indexOf('商品') >= 0);
        const si = heads.findIndex(h => h.indexOf('店铺') >= 0);
        if (si < 0) continue;
        const out = [];
        tb.querySelectorAll('tbody tr').forEach(tr => {
            const tds = tr.querySelectorAll('td');
            const title = (ti >= 0 && tds[ti])
                ? (tds[ti].innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 80) : '';
            const shop = tds[si]
                ? (tds[si].innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 40) : '';
            if (title || shop) out.push({title: title, shop: shop});
        });
        if (out.length) return out;
    }
    return [];
}"""


# ---------------- 列表滚动（翻页） ----------------
# 实测坑：达人列表的可滚动容器是 div.auxo-table-body（约 1615x1150 @ (565,614)）。
# 坑A：若鼠标停在顶部筛选栏，page.mouse.wheel 完全无效（滚的是外层窗口）——
#      这就是"有时翻 17 屏拿到 246 个，有时翻 70 屏只拿到 7 个"的原因。
# 坑B：只按"gap 最大"挑容器会误选到小面板（曾选到 276px 高的元素）→ 必须优先 table-body。
# 对策：优先 table-body（打分加权）；每轮把鼠标移到容器中心 + JS 推进 scrollTop 双保险。
_PICK_SCROLLER = """
    let best = null, bestScore = -1;
    document.querySelectorAll('*').forEach(e => {
        const gap = e.scrollHeight - e.clientHeight;
        if (gap <= 50 || e.clientHeight < 120) return;
        const cls = (e.className || '').toString();
        let score = gap;
        if (cls.indexOf('table-body') >= 0) score += 1000000;
        if (score > bestScore) { bestScore = score; best = e; }
    });
    if (!best) return null;
"""

LIST_SCROLLER_JS = "() => {" + _PICK_SCROLLER + """
    const r = best.getBoundingClientRect();
    return {cls: (best.className || '').toString(),
            ch: best.clientHeight, sh: best.scrollHeight, top: best.scrollTop,
            cx: Math.round(r.x + r.width / 2), cy: Math.round(r.y + r.height / 2)};
}"""

SCROLL_LIST_JS = "(dy) => {" + _PICK_SCROLLER + """
    best.scrollTop = best.scrollTop + dy;
    best.dispatchEvent(new WheelEvent('wheel', {deltaY: dy, bubbles: true}));
    best.dispatchEvent(new Event('scroll', {bubbles: true}));
    const r = best.getBoundingClientRect();
    return {found: true, top: best.scrollTop, sh: best.scrollHeight,
            cx: Math.round(r.x + r.width / 2), cy: Math.round(r.y + r.height / 2)};
}"""


# 【规则3】带货分析：同一品牌占比达到该阈值 -> 跳过该达人
# 用户 2026-09-15 定：先 70%，随后上调为 **50%**
SAME_BRAND_RATIO = float(os.environ.get("SAME_BRAND_RATIO", "0.50"))


def _common_prefix(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return a[:i]


def brand_groups(shops):
    """把带货店铺按「品牌」聚类，返回 [(品牌代表词, 数量)]，按数量降序。

    同品牌判定：店名去掉店型后缀后，与已有簇代表词有 >= 2 字公共前缀。
    例：明希精选 / 明希个护严选 / 明希优品优选 -> 同一簇「明希」
        谷本日记 / 钙尔奇 / Yep / 诺特兰德        -> 四个独立簇
    """
    bases = [b for b in (_strip_shop(s) for s in (shops or []) if s and s.strip()) if b]
    clusters = []                       # [代表词, 数量]
    for b in bases:
        placed = False
        for i, (rep, cnt) in enumerate(clusters):
            if len(_common_prefix(b, rep)) >= 2:
                clusters[i] = [b if len(b) < len(rep) else rep, cnt + 1]
                placed = True
                break
        if not placed:
            clusters.append([b, 1])
    clusters.sort(key=lambda x: -x[1])
    return [(c[0], c[1]) for c in clusters]


def brand_ratio(shops):
    """返回 (最大品牌占比, 品牌名, 商品总件数)。无数据 -> (0.0, '', 0)。"""
    total = len([s for s in (shops or []) if s and s.strip()])
    if not total:
        return 0.0, "", 0
    grp = brand_groups(shops)
    if not grp:
        return 0.0, "", total
    rep, cnt = grp[0]
    return cnt / float(total), rep, total


def brand_verdict(shops):
    """规则3 判定：返回 (是否跳过, 占比, 品牌, 总件数, 最大品牌件数)。

    跳过条件（两个都要满足）：
      ① 最大品牌占比 >= SAME_BRAND_RATIO（默认 50%）
      ② 该品牌件数**严格过半**（cnt*2 > total）
    加条件②是为了防小样本误判：2 件商品来自 2 个不同品牌时各占 50%，
    字面满足阈值，但显然不是"同一家"。
    """
    grp = brand_groups(shops)
    total = len([s for s in (shops or []) if s and s.strip()])
    if not total or not grp:
        return False, 0.0, "", total, 0
    rep, cnt = grp[0]
    ratio = cnt / float(total)
    skip = (ratio >= SAME_BRAND_RATIO) and (cnt * 2 > total)
    return skip, ratio, rep, total, cnt


def norm_name(n):
    return "".join(ch for ch in (n or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff").lower()


def _strip_shop(s):
    t = (s or "").strip()
    for suf in SHOP_SUFFIX:
        if t.endswith(suf) and len(t) > len(suf):
            t = t[:-len(suf)]
    return t or (s or "").strip()


def same_brand(shops):
    """带货店铺是否全部同源（同一家）。

    如「明希精选 / 明希个护严选 / 明希优品优选 / 明希个护名品专柜」去掉店型后缀后
    公共前缀为「明希」-> 判定为同一家（跳过该达人）；
    而「谷本日记官方旗舰店 / 钙尔奇官方旗舰店 / …」公共前缀为空 -> 多家，继续查微信。
    """
    norm = [_strip_shop(s) for s in (shops or []) if s and s.strip()]
    if not norm:
        return False                    # 无带货数据 -> 不跳过
    if len(set(norm)) == 1:
        return True
    pre = norm[0]
    for s in norm[1:]:
        while pre and not s.startswith(pre):
            pre = pre[:-1]
        if not pre:
            return False
    return len(pre) >= 2


def shop_brand_tokens(shops):
    """从带货店铺名提取品牌候选词（去掉店型后缀，长度 >= 2 字）。"""
    return {t for t in (_strip_shop(s) for s in (shops or []) if s) if len(t) >= 2}


def cate_verdict(mc):
    """【规则4】主推类目判定。

    返回 (是否通过, 命中的目标词条列表, 未通过原因)。
      · 必须命中 CATE_MUST_ANY（个护家清 / 美妆）之一，否则 "nocate"
      · 目标词条（个护家清/美妆/服饰内衣/母婴宠物/运动户外）命中 >= 2 个
        -> 通过，第三个及以后的类目不做任何限制
      · 只命中 1 个 -> 带 CATE_EXCLUDE_PARTNER 任一项则 "catecombo"
    """
    mc = mc or []
    if not any(c in CATE_MUST_ANY for c in mc):
        return False, [], "nocate"
    hits = [c for c in mc if c in CATE_TARGETS]
    if len(hits) >= 2:
        return True, hits, ""
    if any(x in CATE_EXCLUDE_PARTNER for x in mc):
        return False, hits, "catecombo"
    return True, hits, ""


def product_exclude_hit(titles):
    """【规则3b】带货商品名命中禁忌词 -> 返回命中的词，否则 ''。"""
    blob = " ".join(t for t in (titles or []) if t)
    return next((kw for kw in PRODUCT_EXCLUDE_KW if kw in blob), "")


def nick_exclude_hit(nick):
    """昵称是否该排除；命中则返回原因（词/号/牌:xxx），否则 None。"""
    n = norm_name(nick)
    if not n:
        return None
    for kw in NICK_EXCLUDE_KW:          # 规则7：渠道/供应链特征词
        if norm_name(kw) in n:
            return "词:" + kw
    for kw in NICK_BRAND_HINT:          # 规则7b①：品牌号特征词
        if norm_name(kw) in n:
            return "号:" + kw
    for kw in BRAND_KW:                 # 规则7b②：品牌词表
        if norm_name(kw) in n:
            return "牌:" + kw
    return None


def wechat_icon(scan, label_kw="达人微信号"):
    """在指定标签行右侧选图标：y 就近；两个闭眼时取下方那个。"""
    label = next((r for r in scan["rows"] if label_kw in r["text"]), None)
    if not label:
        return None
    ly, lx = label["rect"]["y"], label["rect"]["x"]
    for tol in (22, 32, 45):
        cand = [i for i in scan["icons"]
                if i["rect"]["x"] > lx and abs(i["rect"]["y"] - ly) <= tol]
        if cand:
            cand.sort(key=lambda c: (abs(c["rect"]["y"] - ly), -c["rect"]["y"]))
            return cand[0]
    return None


def main():
    open(LOG, "w", encoding="utf-8").close()
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.join(BASE, ".probe"))
    import win_io as w

    apis = []
    # 限流状态：抖音精选联盟的 square_pc_api 在请求过密时返回
    #   {"code":11001,"msg":"请求过于频繁，请稍后再试"}
    # 这时列表会渲染成「未找到相关达人」，看起来像"没数据"，其实是**被限流**。
    # （踩过：美妆批次因此一直拿 0 个）
    rl = {"hit": False, "code": 0, "msg": ""}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="msedge", headless=False,
            no_viewport=True,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                if "search_feed_author" in resp.url:
                    b = resp.text()
                    if b:
                        obj = json.loads(b)
                        if obj.get("code") not in (0, None):
                            rl["hit"] = True
                            rl["code"] = obj.get("code")
                            rl["msg"] = (obj.get("msg") or "")[:80]
                        apis.append(obj)
                elif "square_pc_api" in resp.url:
                    # 其余接口（达人详情 / 带货分析）也会返回 11001
                    b = resp.text()
                    if b:
                        obj = json.loads(b)
                        if obj.get("code") == 11001:
                            rl["hit"] = True
                            rl["code"] = 11001
                            rl["msg"] = (obj.get("msg") or "")[:80]
            except Exception:
                pass

        page.on("response", on_response)

        # ---------- 交互工具 ----------
        def click_box(b, tag=""):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(1.4)

        def dropdown():
            return page.evaluate(DROPDOWN_JS)

        def apply_formitem(name, option, tag):
            """点击 form-item，若弹出下拉则选 option"""
            for attempt in range(3):
                page.keyboard.press("Escape")
                time.sleep(0.5)
                box = page.evaluate(FIND_FORMITEM_JS, name)
                if not box:
                    log("  [%s] 未找到筛选项 %s" % (tag, name))
                    time.sleep(1.0)
                    continue
                click_box(box)
                dd = dropdown()
                if not dd or not dd["items"]:
                    # 无下拉 => 开关型，点击即生效
                    log("  [%s] %s -> 直接切换 OK" % (tag, name))
                    return True
                log("  [%s] %s 下拉选项: %s" % (
                    tag, name, " | ".join(i["t"] for i in dd["items"])))
                if option is None:
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
                    log("  [%s] %s -> 无目标选项，跳过" % (tag, name))
                    return True
                hit = next((i for i in dd["items"] if i["t"] == option), None)
                if not hit:
                    hit = next((i for i in dd["items"] if option in i["t"]), None)
                if not hit:
                    log("  [%s] 下拉里没有 %s" % (tag, option))
                    page.keyboard.press("Escape")
                    time.sleep(0.8)
                    continue
                click_box(hit)
                page.keyboard.press("Escape")
                time.sleep(0.8)
                now = page.evaluate(FIND_FORMITEM_JS, name)
                log("  [%s] %s -> %s OK" % (tag, name, option))
                return True
            return False

        def apply_cate_cascade(parent, child):
            """规则1：点开父类目的级联面板 -> 选中子类目（如 个护家清 > 个人护理）。"""
            for attempt in range(6):
                page.keyboard.press("Escape")
                time.sleep(0.7)
                hits = page.evaluate(FIND_CATE_JS, parent)
                if not hits:
                    log("  [cat] 未找到类目按钮 %s（第%d/6次）" % (parent, attempt + 1))
                    if attempt == 0:
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=15_000)
                        except Exception:
                            pass
                    if attempt == 2:
                        btns = page.evaluate(LIST_CATE_BTNS_JS) or []
                        log("  [cat] 当前可见按钮: %s" % (
                            " | ".join("%s@y%d" % (b["t"], b["y"]) for b in btns[:20])
                            or "(空)"))
                    time.sleep(2.2)
                    continue
                click_box(hits[0])                      # 展开级联面板
                time.sleep(2.4)
                sub = page.evaluate(FIND_CASCADER_JS, child)
                if not sub:
                    opts = page.evaluate(LIST_CASCADER_JS) or []
                    log("  [cat] 级联面板里没找到子类目 %s（第%d次）；可见项: %s" % (
                        child, attempt + 1, " | ".join(o["t"] for o in opts) or "(空)"))
                    page.keyboard.press("Escape")
                    time.sleep(1.2)
                    continue
                log("  [cat] %s 面板已展开，子项 %s @(%d,%d) %s" % (
                    parent, child, sub["x"], sub["y"], sub["cls"][:44]))
                click_box(sub)                          # 选中子类目
                time.sleep(2.6)
                page.keyboard.press("Escape")
                time.sleep(0.8)
                shown = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('*').forEach(e => {
                        const t = (e.innerText||'').trim();
                        if (t.startsWith('主推类目') && t.length < 80) out.push(t);
                    });
                    return out.slice(0, 3);
                }""")
                log("  [cat] 已选回显: %s" % (" | ".join(shown) if shown else "(未捕获)"))
                if any(child in s for s in shown) or \
                   (child == "不限" and any(parent in s for s in shown)):
                    log("  [cat] %s > %s 已生效" % (parent, child))
                    return True
                if not page.evaluate(FIND_CASCADER_JS, child):
                    log("  [cat] %s > %s 已选中（面板已收起）" % (parent, child))
                    return True
            return False

        # ---------- 一轮筛选 ----------
        log("=" * 66)
        log("打开达人广场")
        page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(9)

        # ---------- 登录态检查（用户 2026-09-16：跳过自动登录，等使用者自己登） ----------
        # 登录过期后 daren-square 会跳到抖音电商公开落地页（右上角「登录」），
        # 后续只会表现为「未找到类目按钮」——很容易误判成选择器坏了。
        # 策略：**不自动登录、不立刻中止** —— 主动把**官方登录页**在浏览器里打开，
        # 让使用者在那个 Edge 窗口里自己登录（会话持久化在 .edge-auto/profile），
        # 本脚本轮询**所有标签页**，检测到登录就自动继续。

        def _body_of(pg, tries=1):
            for _t in range(tries):
                try:
                    b = pg.evaluate(
                        "() => (document.body.innerText || '').slice(0, 4000)")
                    if b and b.strip():
                        return b
                except Exception:
                    pass
                if tries > 1:
                    time.sleep(2.5)     # 页面可能正在跳转（落地页 -> 登录页）
            return ""

        def _scan_pages():
            """遍历所有标签页找登录标记，返回 (命中的页面, 命中的标记)。"""
            for pg in list(ctx.pages):
                hit = [m for m in LOGGED_IN_MARK if m in _body_of(pg)]
                if hit:
                    return pg, hit
            return None, []

        def _shot_all(tag):
            """把每个标签页都截一张（登录常发生在新标签页，只截主页面会漏证据）。"""
            for i, pg in enumerate(list(ctx.pages)):
                name = "%s%s_%d.png" % (tag, OUT_TAG, i)
                fp = os.path.join(OUT, name)
                try:
                    pg.screenshot(path=fp)
                    log("   （已截图 out/collect/%s）" % name)
                except Exception as e:
                    # 之前这里写的是 except: pass，导致出问题时**没有任何线索**
                    log("   （截图 %s 失败：%s）" % (name, str(e)[:90]))

        def wait_manual_login():
            """检测到未登录时打开登录页并原地等使用者手动登录。

            返回 (是否已登录, 诊断串)。
            """
            b = _body_of(page, tries=5)
            hit = [m for m in LOGGED_IN_MARK if m in b]
            if hit:
                return True, "已登录（命中 %s）" % "/".join(hit)
            if LOGIN_WAIT_SEC <= 0:
                return False, "未登录，且 LOGIN_WAIT_SEC=0（按设置不等待）"

            log("!" * 66)
            log("!! 当前未登录精选联盟（达人广场被跳到了公开落地页）")
            log("!! 按你的设置：**跳过自动登录环节** —— 你自己在浏览器里登录即可；")
            log("!!   本脚本只负责把登录页打开，然后停在这里等你。")
            log("!! 最多等 %d 秒（约 %d 分钟）。" % (LOGIN_WAIT_SEC, LOGIN_WAIT_SEC // 60))
            log("!" * 66)
            _shot_all("need_login")

            # 主动把官方登录页开出来：对着 marketing 落地页使用者会找不到登录入口
            try:
                lp = ctx.new_page()
                lp.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
                try:
                    lp.bring_to_front()
                except Exception:
                    pass
                log("   ✅ 已在浏览器里打开登录页：%s" % LOGIN_URL)
                log("      请在**那个 Edge 窗口**里登录（扫码 / 账号密码都行），"
                    "本脚本不用管。")
            except Exception as e:
                log("   ⚠️ 自动打开登录页失败：%s" % str(e)[:100])
                log("      请在 Edge 地址栏手动输入：%s" % LOGIN_URL)

            t0 = time.time()
            n = 0
            while time.time() - t0 < LOGIN_WAIT_SEC:
                time.sleep(LOGIN_POLL_SEC)
                n += 1
                _hitpg, hit = _scan_pages()
                if not hit:
                    if n % 12 == 0:         # 约每分钟报一次
                        log("   …仍在等待手动登录（已等 %d/%d 秒）"
                            % (int(time.time() - t0), LOGIN_WAIT_SEC))
                    continue
                log("✅ 检测到已登录（命中 %s），等了 %d 秒，继续采集。"
                    % ("/".join(hit), int(time.time() - t0)))
                # 登录常在新标签页完成 -> 回到达人广场复核一次再往下走
                try:
                    page.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
                    time.sleep(6)
                    b2 = _body_of(page)
                    if any(m in b2 for m in LOGGED_IN_MARK):
                        log("   已回到达人广场，复核通过。")
                        return True, "已登录"
                    log("   ⚠️ 达人广场复核未通过，继续等待……")
                except Exception as e:
                    log("   复核时出错（忽略，继续等）：%s" % str(e)[:100])
                t0 = time.time()        # 复核没过 -> 重新计时
            _shot_all("login_timeout")
            return False, "等待 %d 秒仍未检测到登录" % LOGIN_WAIT_SEC

        login_ok, login_why = wait_manual_login()
        if not login_ok:
            log("!! %s" % login_why)
            log("!! 想给更长的登录时间就设大 LOGIN_WAIT_SEC，例如：")
            log("!!   LOGIN_WAIT_SEC=7200 python collect_30.py")
            log("!! 也可以先在另一个终端跑  python login.py  扫码，再重跑本脚本。")
            time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
            sys.exit(3)          # 退出码 3 = 一直没登录上（驱动层应整体中止）
        log("登录态正常：%s" % login_why)

        log("应用筛选：类目 = %s" % " > ".join("/".join(c) for c in CATES))
        cate_ok = False
        for parent, child in CATES:
            cate_ok = apply_cate_cascade(parent, child) or cate_ok
        if not cate_ok:
            log("!! 类目筛选未生效 -> 中止本次采集（避免采到无关类目）")
            try:
                page.screenshot(path=os.path.join(OUT, "cate_fail.png"))
            except Exception:
                pass
            time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
            sys.exit(2)          # 退出码 2 = 类目没选中（驱动层可重试）
        # 用户 2026-09-15 改：视频结算总额 -> **结算总额**（近30天所有带货来源的总结算额，
        # 不限定直播/短视频）。对应接口字段 common_range_selection_author_sale_gmv_30d_settle。
        apply_formitem(SALE_LABEL, SALE_OPTION, "sale")
        apply_formitem("粉丝量", "10w以下", "fans")
        apply_formitem("有联系方式", None, "contact")
        time.sleep(4)

        # 筛选回显
        try:
            applied = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('div.auxo-form-item').forEach(e => {
                    const t = (e.innerText||'').trim();
                    if (t && t.length < 30) out.push(t);
                });
                return out.slice(0, 20);
            }""")
            log("  筛选项当前显示: %s" % " , ".join(applied))
        except Exception:
            pass

        apis.clear()
        # ---------- 翻页收割（懒加载 + 滚动容器定位，两处坑都踩过） ----------
        # 坑1：只翻一屏无新增就判到底 -> 被懒加载延迟骗到（少了 200+ 个达人）
        # 坑2：鼠标停在筛选栏时 wheel 无效 -> 必须先定位到 div.auxo-table-body 中心
        # 坑3（19:06 踩到）：选完类目后站点有时会**整页导航**一下，
        #      此时 evaluate 直接抛 "Execution context was destroyed"，
        #      或容器迟迟不渲染。对策：等网络静默 + 每次 evaluate 包 try。
        # 对策：鼠标定位 + JS scrollTop 双保险；连续 STALL_LIMIT 屏无新增才判到底。
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        time.sleep(2.5)
        sc = None
        for k in range(20):
            try:
                sc = page.evaluate(LIST_SCROLLER_JS)
            except Exception as e:
                log("  等容器时页面在导航/重载（%s），稍后重试…(%d/20)" % (str(e)[:40], k + 1))
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                time.sleep(2.5)
                continue
            if sc:
                break
            log("  等达人列表容器渲染…(%d/20)" % (k + 1))
            time.sleep(2.0)
        if not sc:
            # 诊断：把当前页面状态留下来，便于判断是不是被登录/验证页拦住
            try:
                log("  ! 容器始终未出现 | url=%s | title=%s" % (page.url, page.title()))
                page.screenshot(path=os.path.join(OUT, "nocontainer%s.png" % OUT_TAG))
                log("  ! 已截图 out/collect/nocontainer%s.png" % OUT_TAG)
            except Exception:
                pass
        if sc:
            log("  列表滚动容器: %s（高 %d / 内容 %d）@(%d,%d)" % (
                (sc["cls"] or "")[:40], sc["ch"], sc["sh"], sc["cx"], sc["cy"]))
            try:
                page.mouse.move(sc["cx"], sc["cy"])
                time.sleep(0.4)
            except Exception:
                pass
        else:
            log("  ! 一直没等到滚动容器（继续尝试滚动，容器出现后会自动生效）")
        last_n, stall = -1, 0
        STALL_LIMIT = 5
        for s in range(MAX_SCROLL):
            info = None
            try:
                info = page.evaluate(SCROLL_LIST_JS, 3600)      # ① JS 推进 scrollTop
                if info:
                    page.mouse.move(info["cx"], info["cy"])     # ② 鼠标跟进容器中心
                    time.sleep(0.15)
                    page.mouse.wheel(0, 3600)                   # ③ 再补一次真实滚轮
            except Exception:
                pass
            if info is None:
                log("  滚动第 %d 屏：容器还没出现，等待中…" % (s + 1))
                time.sleep(2.5)
                continue                                        # 不计入 stall
            time.sleep(SCROLL_PAUSE)
            got = sum(len((d.get("data") or {}).get("list") or []) for d in apis)
            stall = stall + 1 if got == last_n else 0
            log("  滚动第 %d 屏，累计接口响应 %d 条 / 达人 %d 个%s" % (
                s + 1, len(apis), got,
                ("（连续无新增 %d/%d）" % (stall, STALL_LIMIT)) if stall else ""))
            if rl["hit"] and not got:
                log("  !! 接口返回 %s「%s」-> 平台限流，立即停止采集" % (
                    rl["code"], rl["msg"]))
                break
            if stall >= STALL_LIMIT and len(apis) > 2:
                log("  连续 %d 屏无新增 -> 判定已到底" % stall)
                break
            # 兜底：接口一条都没回（列表接口异常 / 被限流），
            # 别再把 MAX_SCROLL 屏空转完（踩过：美妆批次空转 60 屏 ~3 分钟）
            if stall >= 15 and len(apis) <= 2:
                log("  连续 %d 屏无新增且接口仅 %d 条 -> 判定列表加载异常，提前结束" % (
                    stall, len(apis)))
                break
            last_n = got

        if DUMP_APIS:
            try:
                dp = os.path.join(OUT, "apis%s.json" % OUT_TAG)
                with open(dp, "w", encoding="utf-8") as f:
                    json.dump(apis, f, ensure_ascii=False)
                log("  [debug] 原始接口响应 %d 条已存 %s" % (len(apis), dp))
            except Exception as e:
                log("  [debug] dump 接口响应失败: %s" % e)

        # ---------- 解析 ----------
        log("=" * 66)
        log("解析接口数据")
        dumped_any = any((d.get("data") or {}).get("list") for d in apis)
        if rl["hit"] and not dumped_any:
            # 限流时**不要**用空名单覆盖已有产出，只留一个标记文件让驱动层重试
            log("!! 本次采集被平台限流（code=%s %s）-> 列表为空，不覆盖已有名单" % (
                rl["code"], rl["msg"]))
            try:
                with open(os.path.join(OUT, "ratelimit%s.txt" % OUT_TAG), "w",
                          encoding="utf-8") as f:
                    f.write("%s %s\n" % (rl["code"], rl["msg"]))
                log("!! 已写标记 out/collect/ratelimit%s.txt（供 collect_30.py 冷却后重试）"
                    % OUT_TAG)
            except Exception:
                pass
            time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
            return

        if not dumped_any:
            try:
                log("  ! 列表接口没回任何达人 | url=%s | 响应 %d 条" % (page.url, len(apis)))
                page.screenshot(path=os.path.join(OUT, "nodata%s.png" % OUT_TAG))
                log("  ! 已截图 out/collect/nodata%s.png" % OUT_TAG)
            except Exception:
                pass
        raw = {}
        keys_dumped = False
        for d in apis:
            for a in (d.get("data") or {}).get("list") or []:
                ab = a.get("author_base") or {}
                uid = ab.get("uid")
                if not uid:
                    continue
                if not keys_dumped:
                    keys_dumped = True
                    try:
                        json.dump(a, open(os.path.join(OUT, "sample_item.json"), "w",
                                          encoding="utf-8"), ensure_ascii=False, indent=2)
                        log("  样本字段已存 sample_item.json")
                    except Exception:
                        pass
                at = a.get("author_tag") or {}
                al = at.get("author_label_rec_reasons") or []
                sinfo = a.get("sale_info") or {}

                def rng(key):
                    d = sinfo.get(key) or {}
                    return {"low": d.get("sale_low"), "high": d.get("sale_high")}

                raw[uid] = {
                    "nickname": ab.get("nickname"),
                    "uid": uid,
                    "fans": ab.get("fans_num"),
                    "gender": ab.get("gender"),
                    "city": ab.get("city"),
                    "level": ab.get("author_level"),
                    "main_cate": at.get("main_cate") or [],
                    "content_type": [x.get("reason") for x in al if x.get("reason")],
                    # 筛选用：结算总额（原为视频结算总额）
                    "sale_low": (sinfo.get("total_sales_settle") or {}).get("sale_low"),
                    "sale_high": (sinfo.get("total_sales_settle") or {}).get("sale_high"),
                    # Excel 用：四个结算区间
                    "settle_total": rng("total_sales_settle"),            # 销售总额
                    "settle_live": rng("live_total_sales_settle"),         # 直播结算总额
                    "settle_video": rng("video_total_sales_settle"),       # 视频结算总额
                    "settle_image_text": rng("image_text_total_sales_settle"),  # 图文结算总额
                    "has_contact": a.get("has_contact"),
                    "src_cate": CATE_PARENT,
                }
        rows = list(raw.values())
        log("  去重后 %d 个达人" % len(rows))

        # 抽样校验筛选是否生效
        if rows:
            def bad_fans(r):
                try:
                    return int(r["fans"]) > 100000
                except Exception:
                    return False

            def bad_settle(r):
                try:
                    return int(r["sale_low"]) < 10000 or int(r["sale_high"]) > 100000
                except Exception:
                    return False
            nf = sum(1 for r in rows if bad_fans(r))
            ns = sum(1 for r in rows if bad_settle(r))
            log("  校验：粉丝超10w %d 个 / 结算总额不在1w-10w %d 个" % (nf, ns))
            for r in rows[:8]:
                log("     %-20s fans=%-8s video=%s-%s gender=%s city=%s" % (
                    (r["nickname"] or "")[:18], r["fans"], r["sale_low"], r["sale_high"],
                    r["gender"], r["city"]))

        # ---------- 本地过滤 ----------
        seen, picked = set(), []
        stat = {"dup": 0, "male": 0, "region": 0, "noprov": 0, "nocate": 0,
                "catecombo": 0, "content": 0, "nickkw": 0, "nickbrand": 0}
        nick_drop = []                  # 记录被昵称规则剔除的样本，便于核对
        for r in rows:
            k = norm_name(r["nickname"])
            if not k or k in seen:
                stat["dup"] += 1
                continue
            if str(r["gender"]) != "2":
                stat["male"] += 1
                continue
            city = r["city"] or ""
            if any(x in city for x in EXCLUDE_REGION):
                stat["region"] += 1
                continue
            if not any(p in city for p in CN_PROVINCE):
                stat["noprov"] += 1
                continue
            # 规则4：主推类目 —— 命中「个护家清/美妆」其一；
            #        目标词条命中 >=2 个 -> 第三个及以后的类目不做限制；
            #        仅命中 1 个 -> 才查 18 项搭档排除表
            mc = r.get("main_cate") or []
            ok_cate, cate_hits, why = cate_verdict(mc)
            if not ok_cate:
                stat[why] += 1
                continue
            r["cate_hits"] = cate_hits
            # 规则6：达人内容类型不得命中排除表
            ct = r.get("content_type") or []
            if any(c in CONTENT_EXCLUDE for c in ct):
                stat["content"] += 1
                continue
            # 规则7：昵称命中渠道词 / 品牌号特征 / 品牌词表 -> 排除
            hit = nick_exclude_hit(r["nickname"])
            if hit:
                if hit.startswith("词:"):
                    stat["nickkw"] += 1
                else:
                    stat["nickbrand"] += 1
                if len(nick_drop) < 40:
                    nick_drop.append("%s(%s)" % ((r["nickname"] or "")[:16], hit))
                continue
            seen.add(k)
            picked.append(r)
        log("  本地过滤：重复 %d / 非女性 %d / 敏感地区 %d / 非大陆 %d "
            "/ 无目标类目 %d / 排除类目组合 %d / 排除内容类型 %d "
            "/ 昵称排除词 %d / 昵称品牌 %d -> 保留 %d" % (
                stat["dup"], stat["male"], stat["region"], stat["noprov"],
                stat["nocate"], stat["catecombo"], stat["content"],
                stat["nickkw"], stat["nickbrand"], len(picked)))
        if nick_drop:
            log("  昵称被剔除样本：%s" % " | ".join(nick_drop))

        picked = picked[:MAX_CANDIDATE]
        log("  候选池 %d 个达人" % len(picked))

        # ---------- 逐个取联系方式（取满 TARGET_DAREN 个有效达人就停） ----------
        log("=" * 66)
        log("逐个打开达人主页取联系方式（目标：%d 个有效达人）" % TARGET_DAREN)
        done = []                   # 已处理的达人（含被跳过/取不到的）
        verdict_cache = {}          # uid -> "skip"/"go"，重试时不重复判带货
        valid_n = 0                 # 已取到联系方式的「有效达人」数
        cand_n = len(picked)
        err_streak = 0              # 连续「页面上下文损坏」计数 -> 触发浏览器重启

        def restart_browser():
            """浏览器假死（系统休眠/崩溃后）自动重启并重新挂响应监听。

            症状：每个达人主页都抛
              Page.evaluate: Execution context was destroyed, most likely because of a navigation
              Page.goto: Navigation to "..." interrupted by another navigation
            此时继续跑只会把候选池烧完却拿不到任何数据（踩过：休眠 4.5 小时后
            整个批次空转 40 个候选人、0 收获）。
            """
            nonlocal page, ctx
            log("  ~~ 检测到浏览器上下文损坏，正在重启浏览器…")
            try:
                ctx.close()
            except Exception:
                pass
            time.sleep(4)
            for _try in range(3):
                try:
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=PROFILE, channel="msedge", headless=False,
                        no_viewport=True,
                        args=["--start-maximized", "--no-first-run",
                              "--no-default-browser-check"],
                    )
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.on("response", on_response)
                    log("  ~~ 浏览器已重启")
                    return True
                except Exception as e:
                    log("  ~~ 重启失败(%d/3)：%s" % (_try + 1, str(e)[:60]))
                    time.sleep(6)
            return False

        for i, r in enumerate(picked, 1):
            if valid_n >= TARGET_DAREN:
                log("  已取满 %d 个有效达人 -> 停止筛选，准备进入下一步" % TARGET_DAREN)
                break
            # 限流退避：达人详情 / 带货分析 接口返回 11001 时先歇一会儿再继续
            if rl["hit"]:
                log("  ~~ 检测到平台限流（%s %s），退避 %d 秒…" % (
                    rl["code"], rl["msg"], RATE_BACKOFF))
                time.sleep(RATE_BACKOFF)
                rl["hit"] = False
            got_val, got_type = "", ""
            time.sleep(DAREN_PAUSE)
            for attempt in range(3):
                try:
                    page.goto(PROFILE_URL % r["uid"], wait_until="domcontentloaded", timeout=60_000)
                    time.sleep(4)

                    # ---- 规则3：先点「带货分析」看商品来源，同一品牌占比过高则跳过 ----
                    nick18 = (r["nickname"] or "")[:18]
                    if verdict_cache.get(r["uid"]) == "skip":
                        break
                    if r["uid"] not in verdict_cache:
                        # ① tab 可能还没渲染出来 -> 回到顶部重试（最多 3 次）
                        tab = None
                        for k in range(3):
                            tab = page.evaluate(FIND_TAB_JS, "带货分析")
                            if tab:
                                break
                            log("   [%d/%d] %-20s 等「带货分析」tab…(%d/3)" % (
                                i, cand_n, nick18, k + 1))
                            try:
                                page.evaluate("() => window.scrollTo(0, 0)")
                            except Exception:
                                pass
                            time.sleep(2.5)
                        if tab:
                            t0 = tab[0]
                            page.mouse.click(t0["x"] + t0["w"] / 2.0, t0["y"] + t0["h"] / 2.0)
                            time.sleep(3.6)
                            # ② 商品表格是异步加载的 -> 拿不到就再等
                            prows = []
                            for k in range(4):
                                prows = page.evaluate(SHOP_ROWS_JS) or []
                                if prows:
                                    break
                                time.sleep(2.2)
                            # 规则3b：带货商品名命中禁忌词（假发/院线/美甲）-> 跳过
                            titles = [(x.get("title") or "").strip() for x in prows]
                            bad_kw = product_exclude_hit(titles)
                            if bad_kw:
                                r["shop_rows"] = len(prows)
                                r["titles"] = [t for t in titles if t][:12]
                                r["skip_reason"] = "带货含禁忌品:" + bad_kw
                                verdict_cache[r["uid"]] = "skip"
                                log("   [%d/%d] %-20s 带货商品含「%s」-> 跳过该达人" % (
                                    i, cand_n, nick18, bad_kw))
                                break
                            shops = [x.get("shop") for x in prows
                                     if (x.get("shop") or "").strip()]
                            if shops:
                                skip, ratio, brand, total, top_cnt = brand_verdict(shops)
                                grp = brand_groups(shops)[:3]
                                r["shops"] = sorted(set(shops))[:12]
                                r["titles"] = [t for t in titles if t][:12]
                                r["shop_rows"] = total
                                r["top_brand"] = brand
                                r["top_brand_ratio"] = round(ratio, 3)
                                log("   [%d/%d] %-20s 带货 %d 件，最大品牌「%s」%d 件占 %.0f%% "
                                    "（Top3: %s）" % (
                                        i, cand_n, nick18, total, brand, top_cnt, ratio * 100,
                                        " / ".join("%s×%d" % (g[0], g[1]) for g in grp)))
                                if skip:
                                    r["skip_reason"] = "带货同源%.0f%%:%s" % (ratio * 100, brand)
                                    verdict_cache[r["uid"]] = "skip"
                                    log("   [%d/%d] %-20s 同一品牌占 %.0f%% (>=%.0f%%)"
                                        " -> 跳过该达人" % (
                                            i, cand_n, nick18, ratio * 100,
                                            SAME_BRAND_RATIO * 100))
                                    break
                                # 规则7b（动态层）：昵称命中该达人自己的带货品牌 -> 跳过
                                nn = norm_name(r["nickname"])
                                bhit = next((g[0] for g in brand_groups(shops)
                                             if norm_name(g[0]) and norm_name(g[0]) in nn), None)
                                if bhit:
                                    r["skip_reason"] = "昵称含品牌:" + bhit
                                    verdict_cache[r["uid"]] = "skip"
                                    log("   [%d/%d] %-20s 昵称含带货品牌「%s」-> 跳过" % (
                                        i, cand_n, nick18, bhit))
                                    break
                                log("   [%d/%d] %-20s 多家品牌（最大仅 %.0f%%）"
                                    " -> 继续查联系方式" % (i, cand_n, nick18, ratio * 100))
                            else:
                                # 用户要求：带货分析这一步必须真正执行 ——
                                # 拿不到商品数据就无法判定，不能直接进入下一步，只能换人
                                r["skip_reason"] = "带货分析无数据·未判定"
                                verdict_cache[r["uid"]] = "skip"
                                log("   [%d/%d] %-20s ! 带货分析未拿到商品数据"
                                    " -> 跳过该达人（不进入查微信）" % (i, cand_n, nick18))
                                break
                            verdict_cache[r["uid"]] = "go"
                            back = page.evaluate(FIND_TAB_JS, "概览")   # 切回概览
                            if back:
                                page.mouse.click(back[0]["x"] + back[0]["w"] / 2.0,
                                                 back[0]["y"] + back[0]["h"] / 2.0)
                                time.sleep(2.0)
                        else:
                            # 用户要求：点不到「带货分析」就换下一个，绝不能不判定就往下走
                            r["skip_reason"] = "带货分析tab未点到·未判定"
                            verdict_cache[r["uid"]] = "skip"
                            log("   [%d/%d] %-20s ! 重试 3 次仍未点到「带货分析」tab"
                                " -> 跳过该达人（不进入查微信）" % (i, cand_n, nick18))
                            break

                    # 让联系方式区渲染出来
                    for _ in range(3):
                        page.mouse.wheel(0, 1500)
                        time.sleep(0.9)
                    page.mouse.wheel(0, -8000)
                    time.sleep(1.2)
                    scan = page.evaluate(SCAN_JS)

                    def valid(v):
                        v = (v or "").strip()
                        return bool(v) and len(v) >= 3 and len(v) <= 40 and "*" not in v

                    for kw, ctype in (("达人微信号", "微信"), ("达人手机号", "手机")):
                        row = next((x for x in scan["rows"] if kw in x["text"]), None)
                        if not row:
                            continue
                        icon = wechat_icon(scan, kw)
                        if not icon:
                            log("   [%d/%d] %s 有「%s」行但没找到眼睛图标" % (
                                i, cand_n, r["nickname"], kw))
                            continue
                        # 最多点 3 轮：点眼睛揭开 -> 揭不开就点复制图标读剪贴板
                        for _rnd in range(3):
                            page.mouse.click(icon["rect"]["x"] + icon["rect"]["w"] / 2,
                                             icon["rect"]["y"] + icon["rect"]["h"] / 2)
                            time.sleep(2.4)
                            scan2 = page.evaluate(SCAN_JS)
                            txt = next((x["text"] for x in scan2["rows"] if kw in x["text"]), "")
                            val = txt.split("：")[-1].strip() if "：" in txt else ""
                            if valid(val):
                                got_val, got_type = val, ctype
                                break
                            icon2 = wechat_icon(scan2, kw)
                            if not icon2:
                                break
                            before = (w.get_clipboard() or "").strip()
                            page.mouse.click(icon2["rect"]["x"] + icon2["rect"]["w"] / 2,
                                             icon2["rect"]["y"] + icon2["rect"]["h"] / 2)
                            time.sleep(1.9)
                            clip = (w.get_clipboard() or "").strip()
                            if valid(clip) and clip != before:
                                got_val, got_type = clip, ctype
                                break
                            icon = icon2
                        if got_val:
                            break
                    if got_val:
                        break
                    no_row = not any(kw in x["text"] for x in scan["rows"]
                                     for kw in ("达人微信号", "达人手机号"))
                    if no_row:
                        log("   [%d/%d] %s 主页无联系方式行" % (i, cand_n, r["nickname"]))
                        break
                except Exception as e:
                    msg = str(e).replace("\n", " ")
                    log("   [%d/%d] %s 第%d次异常: %s" % (i, cand_n, r["nickname"],
                                                          attempt + 1, msg[:70]))
                    if "Execution context was destroyed" in msg or \
                       "interrupted by another navigation" in msg or \
                       "Target page, context or browser has been closed" in msg:
                        err_streak += 1
                        if err_streak >= 4 and restart_browser():
                            err_streak = 0      # 后面的达人会用新浏览器继续
                    else:
                        err_streak = 0
                    time.sleep(2)
            r["contact"] = got_val
            r["contact_type"] = got_type
            if got_val:
                valid_n += 1
            done.append(r)
            tail = "跳过·带货同源" if r.get("skip_reason") else (got_val or "✗ 未取到")
            log("   [%d/%d] %-22s %-12s 粉丝=%-7s %s=%s  (有效 %d/%d)" % (
                i, cand_n, (r["nickname"] or "")[:20], r["city"], r["fans"],
                got_type or "联系", tail, valid_n, TARGET_DAREN))

        picked = done

        # ---------- 输出 ----------
        # 覆盖前先归档上一版，避免小批量测试把正式名单冲掉
        old = os.path.join(OUT, "darens%s.json" % OUT_TAG)
        if os.path.exists(old):
            try:
                with open(old, encoding="utf-8") as f:
                    prev = f.read()
                if len(json.loads(prev)) > len(picked):
                    arc = os.path.join(OUT, "archive")
                    os.makedirs(arc, exist_ok=True)
                    stamp = time.strftime("%Y%m%d_%H%M%S")
                    dst = os.path.join(arc, "darens%s_%s.json" % (OUT_TAG, stamp))
                    open(dst, "w", encoding="utf-8").write(prev)
                    log("  上一版 %d 条已归档 -> %s" % (len(json.loads(prev)), dst))
            except Exception as e:
                log("  ! 归档失败：%s" % e)

        write_outputs(picked, OUT_TAG)

        ok = sum(1 for r in picked if r.get("contact"))
        okw = sum(1 for r in picked if r.get("contact_type") == "微信")
        log("=" * 66)
        log("完成：处理 %d 个达人，%d 个取到联系方式（其中微信号 %d 个）" % (len(picked), ok, okw))
        if ok >= TARGET_DAREN:
            log("目标达成：有效达人 %d/%d -> 停止筛选，可进入下一步（微信加好友）" % (ok, TARGET_DAREN))
        else:
            log("提示：仅取到 %d/%d 个有效达人（候选池已遍历完）" % (ok, TARGET_DAREN))

        time.sleep(4)
        try:
            ctx.close()
        except Exception:
            pass
    log("结束")


if __name__ == "__main__":
    main()
