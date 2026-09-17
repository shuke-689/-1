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
          双类目分两批跑（见 collect_30.py）：个护家清 + 美妆
          （每批目标有效达人数由 GHQ_TARGET / MZ_TARGET 控制，默认各 30）
          放行的类目组合（用户 2026-09-15 最新口径）：
            个护家清｜个护家清+美妆｜美妆｜个护家清+服饰内衣｜
            个护家清+母婴宠物｜个护家清+运动户外
            且「个护家清/美妆/服饰内衣/母婴宠物/运动户外」命中 >= 2 个时，
            第三个及以后的类目**不做任何限制**
            （如 个护家清/母婴宠物/食品饮料 ✔、个护家清/美妆/食品饮料 ✔）
  【规则2】直播结算总额 = 1w-10w   ← 用户 2026-09-16 由「结算总额」改为「直播结算总额」
          字段 common_range_selection_live_sales_30d_settle
          （口径变化：只认直播带货的结算额；settle_live 为 0 的纯短视频/图文达人会被排除）
          历史：2026-09-15 之前是「视频结算总额」，09-15 改「结算总额」，09-16 改「直播结算总额」
          ⚠️ 用户 09-16 还要求过 5000-10w，但平台下拉只有 6 档、最细是「1w以下」，
             没有 5000 档 -> 用户确认落回 1w-10w
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
  【规则6】达人内容类型(author_tag.author_label_rec_reasons[].reason)：
          6a **白名单优先**（用户 2026-09-17 新增）—— 命中以下任一**直接保留**，
             即使同时命中了 6b 的黑名单：
             亲子 / 剧情 / 时尚 / 情感 / 文化 / 旅行 / 明星 / 母婴 /
             舞蹈 / 音乐 / 颜值 / 体育 / 摄影摄像
          6b 未命中白名单时，命中以下任一项才排除：
             三农 / 公益 / 人文社科 / 二次元 / 医疗健康 / 动物 / 教育校园 / 汽车 /
             游戏 / 生活家居 / 社会时政 / 科技 / 科普 / 美食 / 职场 / 财经
          （改前是纯黑名单「任一命中即排除」，把「时尚+美食」这类误杀了）
  【规则7】昵称命中排除词：国际 / 全球 / 美业 / 供应链 / 折扣 / 厂家 / 大牌 /
          养发 / 集团 / 防晒；或带品牌号特征词（官方/旗舰/专卖/授权/正品/品牌…）
          或命中品牌词表（蜜丝婷、百雀羚、云南白药…）-> 排除
  昵称标准化后去重
数量限制：
  【规则5】取满 TARGET_DAREN 个「有效达人」（成功取到联系方式的）即停止筛选
达人主页：
  跳 /dashboard/servicehall/daren-profile?uid=<uid>
  【规则3】跳达人主页后**必须先点「带货分析」tab**，读「商品信息」+「店铺信息」+「到手价」：
      3a 同品牌：按品牌聚类（店名去店型后缀 -> 公共前缀 >=2 字视为同品牌）
      **同一品牌占比 >= SAME_BRAND_RATIO（默认 50%）且严格过半 -> 跳过该达人**
      多家品牌（最大占比 < 50%，或打平）-> 继续
      3b 禁忌商品：商品名含 假发 / 院线 / 美甲 -> **跳过该达人**
                   用户 2026-09-17 追加：含 充电宝 / 移动电源 / 3C数码 / 数码 /
                   数据线 / 充电器 / 充电头 / 蓝牙耳机 -> **跳过**
      3c 店铺数少：去重后的**店铺家数 <= MIN_SHOP_CNT（默认 2）** -> 跳过
                   （用户 2026-09-17 追加；专营自己一家店的达人一律不要）
      3d 低价铺货：**>= CHEAP_RATIO（默认 90%）的商品到手价 < CHEAP_PRICE（默认 30 元）**
                   -> 跳过（用户 2026-09-17 追加）
      ⚠️ 到手价格式实测为 "￥59.90" / "￥29.90 ￥69.90"（第一个数才是到手价）
      ⚠️ 价格可解析比例 < PRICE_MIN_PARSE（默认 80%）= **未判定 -> 也跳过**
      3e 养发占比：**商品名 或 店铺名**含 YANGFA_KW（默认「养发」）的件数
                   **> YANGFA_RATIO（默认 50%，严格大于）** -> 跳过（用户 2026-09-17 追加）
                   与 3b 的区别：3b 是「任一命中就跳」，3e 要「过半」才跳
      ⚠️ tab 点不到 / 商品数据拿不到 = **未判定 -> 直接跳过该达人**，
         绝不"未判定就进入查微信"（用户 2026-09-15 明确要求的纠错）
      ⚠️ 商品表是分页的（首页约 15 行），3a/3c/3d 都是基于首页样本判定
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
import re
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
# 官方登录页（**候选列表，按顺序试，挑第一个可用的**）
#   ⚠️ 实测 2026-09-16：`https://buyin.jinritemai.com/login` 已经 **404（nginx）**，
#      所以不能硬编码它。`fxg.jinritemai.com/login/common?from=buyin` 实测可用
#      （标题「抖店登录」，含扫码/验证码登录；同域 *.jinritemai.com，cookie 通用）。
# 覆盖方式：export LOGIN_URL=<你的地址>（会排在最前）
LOGIN_URLS = tuple(u for u in (
    os.environ.get("LOGIN_URL", ""),
    "https://fxg.jinritemai.com/login/common?from=buyin",
    "https://buyin.jinritemai.com/login",
) if u)
# 判断「这个页面像不像登录页」：命中 GOOD 且未命中 BAD 才算可用
#   ⚠️ GOOD 里**不要**放「登录」二字 —— 抖音电商 marketing 落地页右上角就有「登录」
#      按钮，会把它误判成登录页；要用「验证码 / 扫码」这类只有真登录页才有的字样。
LOGIN_PAGE_GOOD = ("验证码", "扫码", "二维码", "账号登录", "密码登录")
LOGIN_PAGE_BAD = ("404 Not Found", "not found", "nginx")

# 【筛选】直播结算总额 —— 用户 2026-09-16 由「结算总额」改为「直播结算总额」
# 口径沿革：视频结算总额 -> 结算总额(09-15) -> 直播结算总额(09-16)
# 字段名（实测自 /square_pc_api/square/filter）：
#   结算总额       common_range_selection_author_sale_gmv_30d_settle  （近30天所有带货来源的总结算额）
#   直播结算总额   common_range_selection_live_sales_30d_settle   ← 当前在用
#   视频结算总额   common_range_selection_video_sales_30d_settle
#   图文结算总额   common_range_selection_picture_sales_30d_settle
#   橱窗结算总额   common_range_selection_window_sales_30d_settle
#   场均结算额     common_range_selection_author_square_average_gmv_settle
# 注意：FIND_FORMITEM_JS 是**精确匹配**，所以「结算总额」不会误撞到「直播结算总额」。
# 区间选项（6 档，实测自 out/stage5/filter.json 的 children）：
#   全部 / 1w以下=1 / 1w-10w=2 / 10w-100w=3 / 100w-500w=4 / 500w-1000w=5 / 1000w以上=6
#   ⚠️ 没有 5000 档；「5000-10w」无法直接选（数据侧虽是数值区间，但平台侧不支持）
#   ✅ 该下拉是**多选**（探针 .probe/probe_sale_multiselect.py 实测：
#      同时勾 1w以下+1w-10w 会发出 ['1','2']）—— 以后若真要拼区间，可以多选凑超集
SALE_LABEL = os.environ.get("SALE_LABEL", "直播结算总额")
SALE_OPTION = os.environ.get("SALE_OPTION", "1w-10w")

# 区间选项文本 -> 接口 value（位置就是 value，1~6；结算类与粉丝量共用这套）
RANGE_VALUE = {"1w以下": "1", "1w-10w": "2", "10w-100w": "3", "100w-500w": "4",
               "500w-1000w": "5", "1000w以上": "6",
               "10w以下": "1", "10w-100w": "2", "100w-300w": "3",
               "300w-500w": "4"}
# 高级筛选界面名 -> 接口字段名（用于 payload 端到端校验）
SALE_FIELD_BY_LABEL = {
    "结算总额": "common_range_selection_author_sale_gmv_30d_settle",
    "直播结算总额": "common_range_selection_live_sales_30d_settle",
    "视频结算总额": "common_range_selection_video_sales_30d_settle",
    "图文结算总额": "common_range_selection_picture_sales_30d_settle",
    "橱窗结算总额": "common_range_selection_window_sales_30d_settle",
}
FANS_LABEL = "粉丝量"
FANS_OPTION = "10w以下"
FANS_FIELD = "fans_num"
CONTACT_FIELD = "has_contact"
CATE_FIELD = "main_cate_new"
# 类目名 -> 接口 id（实测自 payload，仅用于校验；选类目本身仍走 UI 级联）
CATE_ID_BY_NAME = {"个护家清": "5", "美妆": "9"}

# 【规则1】主推类目 = 「个护家清」（级联菜单里选「不限」= 整个个护家清大类）
# 如需只取某个子类目，设 CATE_CHILD=个人护理 / 家清纸品
# 用户 2026-09-15 追加：类目再加「美妆」（同样选「不限」）
# 每批目标有效达人数见 collect_30.py 的 GHQ_TARGET / MZ_TARGET（默认各 30）
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

# 【规则3b】带货**商品名称**命中以下词 -> 排除该达人
#   3b 用户 2026-09-15 追加：假发 / 院线 / 美甲
#   3b 用户 2026-09-17 追加：「商品中带充电宝类的，3C数码产品的，进行跳过」
#      ⚠️ 刻意**不**用裸 "3C" —— 它是美妆品牌「3CE」的子串，会把正规美妆达人误杀；
#         要覆盖 3C 就写全 "3C数码"。
#      可用环境变量覆盖：export PRODUCT_EXCLUDE_KW="假发,院线,美甲,充电宝"
PRODUCT_EXCLUDE_KW = tuple(
    x.strip() for x in os.environ.get(
        "PRODUCT_EXCLUDE_KW",
        "假发,院线,美甲,充电宝,移动电源,3C数码,数码,数据线,充电器,充电头,蓝牙耳机",
    ).split(",") if x.strip()
)

# 【规则6】达人内容类型（author_tag.author_label_rec_reasons[].reason，覆盖率 100%）
#        不得属于以下类型（任一带命中即排除）
#        注意：用户口语「人文」= 平台正式名「人文社科」
# 【规则6】内容类型
# 6a 白名单（用户 2026-09-17 新增）：命中以下任一 -> **直接保留**，
#    即使同时命中下面的 CONTENT_EXCLUDE。
#    用户原话：「达人内容类型中，保留 亲子、剧情、时尚、情感、文化、旅行、明星、母婴、
#              舞蹈、音乐、颜值、体育、摄影摄像」
#    背景：以前是纯黑名单「任一命中即排除」，导致「时尚+美食」这类被误杀，
#          用户观察到「有很多时尚的、符合类目的，均未筛选到」。
CONTENT_KEEP = (
    "亲子", "剧情", "时尚", "情感", "文化", "旅行", "明星", "母婴",
    "舞蹈", "音乐", "颜值", "体育", "摄影摄像",
)
# 6b 黑名单：**没有**命中白名单时，命中以下任一项才排除
CONTENT_EXCLUDE = (
    "三农", "公益", "人文社科", "二次元", "医疗健康", "动物", "教育校园", "汽车",
    "游戏", "生活家居", "社会时政", "科技", "科普", "美食", "职场", "财经",
)

# 【规则7】昵称命中以下词 -> 排除（渠道 / 供应链 / 机构 / 品牌号特征）
#   ⚠️ 词表已抽到**无副作用的独立模块** `nick_rules.py`（在文件上方统一 import），
#      因为阶段 B（微信加好友）和阶段 C（登记飞书）也必须用同一份词表再挡一道
#      （旧名单不会自动重筛）。追加/修改词表请改 `nick_rules.py`，别在这里重复定义。

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
import douyin_id as DID   # noqa: E402  （点「达人抖音主页」取抖音号，登记飞书要用）
import nick_rules         # noqa: E402  （昵称排除词，A/B/C 三阶段共用）
NICK_EXCLUDE_KW = nick_rules.NICK_EXCLUDE_KW


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
    // 优先精确匹配；选中后 innerText 会变成「名称+已选值」，所以退化为前缀匹配。
    // （前缀匹配在本页是安全的：结算总额/直播结算总额/视频结算总额互不为前缀）
    let exact = null, prefix = null;
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        const t = (e.innerText||'').trim();
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        if (t === name) exact = e;
        else if (!prefix && t.startsWith(name)) prefix = e;
    });
    const hit = exact || prefix;
    if (!hit) return null;
    const r = hit.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
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

# 列出**所有**可见下拉（DROPDOWN_JS 只取最后一个，多个浮层同时存在时会串字段）
ALL_DROPDOWNS_JS = """() => {
    const dds = Array.from(document.querySelectorAll('.auxo-select-dropdown'))
        .filter(e => e.getBoundingClientRect().height > 10);
    return dds.map(dd => {
        const dr = dd.getBoundingClientRect();
        const items = Array.from(dd.querySelectorAll('.auxo-select-item-option-content')).map(e => {
            const r = e.getBoundingClientRect();
            return {t:(e.innerText||'').trim(), x:Math.round(r.x), y:Math.round(r.y),
                    w:Math.round(r.width), h:Math.round(r.height),
                    selected: !!e.closest('.auxo-select-item-option-selected')};
        });
        return {box:{x:Math.round(dr.x), y:Math.round(dr.y),
                     w:Math.round(dr.width), h:Math.round(dr.height)},
                items: items};
    });
}"""

# 关浮层：auxo 的**多选**下拉按 Escape 关不掉（2026-09-17 实测），
# 改用「在 body 上派发一次外侧点击」触发它自己的 outside-click 关闭逻辑。
CLOSE_DROPDOWN_JS = """() => {
    ['mousedown','mouseup','click'].forEach(t => {
        document.body.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true}));
    });
    return Array.from(document.querySelectorAll('.auxo-select-dropdown'))
        .filter(e => e.getBoundingClientRect().height > 10).length;
}"""

# 用 JS 直接点 form-item —— 绕过「鼠标点落在浮层上被吞掉」的问题
CLICK_FORMITEM_JS = """(name) => {
    let hit = null;
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        if ((e.innerText||'').trim() !== name) return;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) return;
        hit = e;
    });
    if (!hit) return false;
    const target = hit.querySelector('.auxo-select, button, .auxo-form-item-control') || hit;
    target.click();
    return true;
}"""

# 读某筛选项当前的回显文本（选中后 innerText 会变成「名称+已选值」，所以用 startsWith）
FORMITEM_TEXT_JS = """(name) => {
    let out = null;
    document.querySelectorAll('div.auxo-form-item').forEach(e => {
        const t = (e.innerText||'').trim().replace(/\\s+/g, ' ');
        if (t === name || t.startsWith(name)) out = t.slice(0, 80);
    });
    return out;
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
# 一次把「商品名 + 店铺名 + 到手价」都取回来：
#   店铺名 -> 规则3（同一品牌占比 >= 50% 则跳过）
#             规则3a（去重店铺家数 <= 2 则跳过）
#   商品名 -> 规则3b/3c（含 假发/院线/美甲/充电宝/3C数码… -> 跳过）
#   到手价 -> 规则3d（>= 90% 商品价格 < 30 元 -> 跳过）
#   ⚠️ 表格是**分页**的，首页只渲染约 15 行（表头旁边会写「共 N 个带货商品」），
#      所以这三条规则都是在「首页样本」上判定，不是全量。
SHOP_ROWS_JS = """() => {
    const tables = Array.from(document.querySelectorAll('table'));
    for (const tb of tables) {
        const r = tb.getBoundingClientRect();
        if (r.width < 300 || r.height < 50) continue;
        const heads = Array.from(tb.querySelectorAll('th')).map(e => (e.innerText||'').trim());
        const ti = heads.findIndex(h => h.indexOf('商品') >= 0);
        const si = heads.findIndex(h => h.indexOf('店铺') >= 0);
        if (si < 0) continue;
        let pi = heads.findIndex(h => h.indexOf('到手价') >= 0);
        if (pi < 0) pi = heads.findIndex(h => h.indexOf('价格') >= 0);
        const out = [];
        tb.querySelectorAll('tbody tr').forEach(tr => {
            const tds = tr.querySelectorAll('td');
            const title = (ti >= 0 && tds[ti])
                ? (tds[ti].innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 80) : '';
            const shop = tds[si]
                ? (tds[si].innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 40) : '';
            const price = (pi >= 0 && tds[pi])
                ? (tds[pi].innerText||'').trim().replace(/\\s+/g, ' ').slice(0, 40) : '';
            if (title || shop) out.push({title: title, shop: shop, price: price});
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
# 坑C（2026-09-17 15:19 踩到，整轮采集空转报废）：
#      当天 A 阶段：登录态正常、四项筛选接口校验全过，但容器连续 20 次 + 滚动 20 屏
#      都判「容器始终未出现」，而这期间截图 out/collect/nocontainer_ghq.png 里
#      **达人列表明明已经渲染出来了**（有数据、有行、有滚动条）。
#      同一天用探针 `.probe/probe_scroller_dump.py` 连测 3 次，容器都**正常选得到**
#      （div.auxo-table-body ch=1135 sh≈1860 gap≈730 ovY=scroll @(565,614)）。
#      ⚠️ **根因未完全定位**：最后一次「复现 null」是探针自身的 bug
#      （把已是 `() => {...}` 的 LIST_SCROLLER_JS 又包了一层，evaluate 返回函数 →
#        序列化不了 → 假 null），不是线上代码的问题。所以**不能断言**就是 gap<=50 卡掉的。
#      仍保留「按类名认得出的容器放宽 gap 限制」这条改动：
#      它是**纯放宽**，只会让判定更早成功、不会选错（table-body/virtual-list 是确定的容器），
#      作为对这类间歇性失败的钝化处理。若再遇到，看下面 DUMP_OVERFLOW_JS 打出的
#      「溢出候选」清单即可一眼分辨「真没渲染」还是「条件卡太严」。
# 对策：优先 table-body（打分加权）；每轮把鼠标移到容器中心 + JS 推进 scrollTop 双保险。
_PICK_SCROLLER = """
    let best = null, bestScore = -1;
    document.querySelectorAll('*').forEach(e => {
        if (e.clientHeight < 120) return;
        const gap = e.scrollHeight - e.clientHeight;
        const cls = (e.className || '').toString();
        const isTB = cls.indexOf('table-body') >= 0;
        const isVL = cls.indexOf('virtual-list') >= 0;
        // 常规容器必须真有溢出；按类名认得出的容器放宽（见上方「坑C」）
        if (gap <= 50 && !isTB && !isVL) return;
        let score = gap > 0 ? gap : 0;
        if (isTB) score += 1000000;
        else if (isVL) score += 500000;
        if (score > bestScore) { bestScore = score; best = e; }
    });
    if (!best) return null;
"""

# 容器死活找不到时的取证：把页面上「有溢出的元素」前几名 dump 出来，
# 下次一眼就能看出是「没有溢出元素」（真没渲染）还是「条件卡太严」（渲染了但被判掉）。
DUMP_OVERFLOW_JS = """() => {
    const out = [];
    document.querySelectorAll('*').forEach(e => {
        const gap = e.scrollHeight - e.clientHeight;
        if (gap <= 0) return;
        const r = e.getBoundingClientRect();
        out.push({tag: e.tagName, cls: (e.className || '').toString().slice(0, 48),
                  gap: gap, ch: e.clientHeight, sh: e.scrollHeight,
                  h: Math.round(r.height)});
    });
    out.sort((a, b) => b.gap - a.gap);
    return out.slice(0, 6);
}"""

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

# ===== 用户 2026-09-17 追加的三条带货规则 =====
# 【规则3c】所带商品的**店铺数** <= 该值 -> 跳过（专卖自己一家店的达人）
#   注意：这是**去重后的店铺家数**，不是商品件数（商品件数见 r["shop_rows"]）。
#   实测样本：嬉笑闫开护肤品批发，15 件商品全部来自「嬉笑闫开护肤」1 家店 -> 命中
MIN_SHOP_CNT = int(os.environ.get("MIN_SHOP_CNT", "2"))
# 【规则3d】所带商品中**价格 < CHEAP_PRICE 的比例** >= CHEAP_RATIO -> 跳过（低价铺货型）
#   用户原话：「带人所带商品，价格90%以上小于30元，进行跳过」
CHEAP_PRICE = float(os.environ.get("CHEAP_PRICE", "30"))
CHEAP_RATIO = float(os.environ.get("CHEAP_RATIO", "0.90"))
#   价格可解析的最低比例：解析不出来就当「未判定」-> 跳过（绝不未判定就查微信）
#   实测到手价单元格形如 "￥59.90" / "￥29.90 ￥69.90"（**第一个数才是到手价**，
#   后面那个是划线原价），空值/异常给 "-"。
PRICE_MIN_PARSE = float(os.environ.get("PRICE_MIN_PARSE", "0.80"))

# 【规则3e】带货**商品名或店铺名**含 YANGFA_KW，且占比 **> YANGFA_RATIO** -> 跳过
#   用户原话（2026-09-17）：「达人所带货商品及商品店铺带养发，且占比超过50%的，也进行剔除」
#   · 两条命中路径：商品标题含「养发」 **或** 商品所属店铺名含「养发」
#   · 「超过 50%」按**严格大于**实现（8/15=53.3% 命中；7/15=46.7%、8/16=50.0% 都不算）
#   · 分母 = 抓到的商品行数（和 3a/3c/3d 同一份首页样本，约 15 行，已知会低估）
#   · 与 3b 的区别：3b 是**任一命中就跳**，本条要**过半**才跳
YANGFA_KW = tuple(
    x.strip() for x in os.environ.get("YANGFA_KW", "养发").split(",") if x.strip()
)
YANGFA_RATIO = float(os.environ.get("YANGFA_RATIO", "0.50"))


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


# 到手价格式（2026-09-17 实测 dump 自 out/probe_price/dump_*.json）：
#   "￥59.90"                -> 59.90
#   "￥29.90 ￥69.90"        -> 29.90   ← **第一个数是到手价**，第二个是划线原价
#   "￥1,299.00"             -> 1299.0  （千分位）
#   "-" / "" / "暂无"        -> None
#   注意符号是全角 ￥(U+FFE5)，也可能出现半角 ¥，这里只认数字，符号随意。
_PRICE_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_price(text):
    """从「到手价」单元格文本里取出到手价数字；取不到返回 None。"""
    if not text:
        return None
    m = _PRICE_NUM_RE.search(str(text))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def cheap_verdict(prows):
    """【规则3d】所带商品「价格 < CHEAP_PRICE 的比例」>= CHEAP_RATIO -> 跳过。

    返回 (是否跳过, 低价占比, 可解析数, 总行数, 原因)
      原因取值："cheap"（命中）/ "fewprice"（价格样本不足·未判定）/ ""
    ⚠️ 未判定 -> 也跳过，遵循项目既有铁律「绝不未判定就查微信」。
    """
    n_all = len(prows or [])
    prices = [p for p in (parse_price(x.get("price")) for x in (prows or []))
              if p is not None]
    n_ok = len(prices)
    if not n_all or n_ok < max(3, int(n_all * PRICE_MIN_PARSE)):
        return False, 0.0, n_ok, n_all, "fewprice"
    cheap = sum(1 for p in prices if p < CHEAP_PRICE)
    ratio = cheap / float(n_ok)
    if ratio >= CHEAP_RATIO:
        return True, ratio, n_ok, n_all, "cheap"
    return False, ratio, n_ok, n_all, ""


def shopcnt_verdict(shops):
    """【规则3c】去重后的带货店铺家数 <= MIN_SHOP_CNT -> 跳过。

    返回 (是否跳过, 店铺家数, 店铺名列表)
    只认店铺名本身；同一家店写法有差异会算成两家（宁可漏杀，不可错杀）。
    """
    uniq = sorted({s.strip() for s in (shops or []) if s and s.strip()})
    return len(uniq) <= MIN_SHOP_CNT, len(uniq), uniq


def yangfa_verdict(prows):
    """【规则3e】商品名或店铺名含 YANGFA_KW 的行数占比 > YANGFA_RATIO -> 跳过。

    返回 (是否跳过, 命中占比, 命中件数, 总件数, 样例商品名)
    第 5 项是给日志/排查用的：列出 1~2 个命中的商品或店铺，方便人工复核。
    "占比超过 50%" 取**严格大于**（等于 50% 不跳）。
    """
    rows = prows or []
    n_all = len(rows)
    if not n_all:
        return False, 0.0, 0, 0, ""
    hits, sample = 0, ""
    for x in rows:
        title = (x.get("title") or "")
        shop = (x.get("shop") or "")
        if any(kw in title or kw in shop for kw in YANGFA_KW):
            hits += 1
            if not sample:
                sample = (title or shop).strip()[:28]
    ratio = hits / float(n_all)
    return ratio > YANGFA_RATIO, ratio, hits, n_all, sample


def nick_exclude_hit(nick):
    """昵称是否该排除；命中则返回原因（数字/词/号/牌:xxx），否则 None。"""
    n = norm_name(nick)
    if not n:
        return None
    # 【规则7c】纯数字昵称（用户 2026-09-17 追加：「名字是一堆阿拉伯数字的」
    #   如「86567278365」）-> 无辨识度，直接排除。判定在 nick_rules.py 里统一维护。
    if nick_rules.is_digit_nick(nick):
        return "纯数字"
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

        # 记录 search_feed_author 的**请求 payload** —— 用来做「筛选是否真生效」的端到端校验。
        # （之前只看 UI 日志，粉丝量静默失效了一整批才发现，见 apply_formitem 的坑）
        reqs = []

        def on_request(req):
            try:
                if "search_feed_author" in req.url and req.method == "POST":
                    reqs.append(req.post_data or "")
            except Exception:
                pass

        page.on("request", on_request)

        # ---------- 交互工具 ----------
        def click_box(b, tag=""):
            page.mouse.click(b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)
            time.sleep(1.4)

        def dropdown():
            return page.evaluate(DROPDOWN_JS)

        def all_dropdowns():
            try:
                return page.evaluate(ALL_DROPDOWNS_JS) or []
            except Exception:
                return []

        def close_dropdowns(max_round=3):
            """把所有可见下拉关干净，返回是否已关干净。

            🔴 坑（2026-09-17 实跑踩到，导致「粉丝量」筛选静默失效）：
              auxo 的**多选**下拉按 Escape **关不掉**，会一直浮在页面下方。
              而「粉丝量」正好排在「直播结算总额」**正下方**（x 相同 752、y 差 40）：
                直播结算总额 item: x752~880 y359~384
                粉丝量       item: x752~838 y399~424
                结算下拉浮层     : x752~901 y388~629   <- 把粉丝量整个盖住
              于是鼠标点「粉丝量」中心 (795,411) 落在浮层里被吞掉 -> 它的下拉从没打开
              -> 读到的还是结算的下拉 -> 「下拉里没有 10w以下」连试 3 次全败。
              （旧口径点「结算总额」浮层是 x644~793，粉丝量中心 x795 刚好超出 2px，
                所以侥幸能点到 —— 这次换成「直播结算总额」才暴露。）
            """
            for _ in range(max_round):
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                time.sleep(0.3)
                if not all_dropdowns():
                    return True
                try:
                    if not page.evaluate(CLOSE_DROPDOWN_JS):
                        return True
                except Exception:
                    pass
                time.sleep(0.3)
            return not all_dropdowns()

        def pick_option(dds, option, item_box):
            """在所有可见下拉里找 option；优先「几何上就在被点项正下方」的那个下拉。

            不能无脑取 dds[-1]：多个浮层同时存在时那个可能属于别的字段。
            """
            cands = []
            for d in dds:
                it = next((i for i in d["items"] if i["t"] == option), None)
                if not it:
                    it = next((i for i in d["items"] if option in i["t"]), None)
                if not it:
                    continue
                b = d["box"]
                dy = abs(b["y"] - (item_box["y"] + item_box["h"]))
                aligned = (b["x"] <= item_box["x"] + item_box["w"]
                           and b["x"] + b["w"] >= item_box["x"])
                cands.append((0 if aligned else 1, dy, it))
            if not cands:
                return None
            cands.sort(key=lambda t: (t[0], t[1]))
            return cands[0][2]

        def apply_formitem(name, option, tag):
            """点击 form-item，若弹出下拉则选 option。"""
            for attempt in range(3):
                # 1) 先把残留浮层清干净（否则浮层会盖住下一行的筛选项）
                if not close_dropdowns():
                    log("  [%s] 警告：仍有下拉没关掉，继续尝试" % tag)
                box = page.evaluate(FIND_FORMITEM_JS, name)
                if not box:
                    log("  [%s] 未找到筛选项 %s" % (tag, name))
                    time.sleep(1.0)
                    continue
                click_box(box)
                dds = all_dropdowns()
                if not dds or not any(d["items"] for d in dds):
                    # 无下拉 => 开关型，点击即生效
                    log("  [%s] %s -> 直接切换 OK" % (tag, name))
                    return True
                log("  [%s] %s 下拉选项: %s" % (
                    tag, name, " | ".join(i["t"] for d in dds for i in d["items"])))
                if option is None:
                    close_dropdowns()
                    log("  [%s] %s -> 无目标选项，跳过" % (tag, name))
                    return True
                hit = pick_option(dds, option, box)
                if not hit:
                    # 大概率是点击被浮层吞了 -> 用 JS 直接触发一次，再找
                    log("  [%s] 可见下拉里没有 %s，改用 JS 直接点击该项重试" % (tag, option))
                    close_dropdowns()
                    try:
                        page.evaluate(CLICK_FORMITEM_JS, name)
                    except Exception as e:
                        log("  [%s] JS 点击失败: %s" % (tag, str(e)[:60]))
                    time.sleep(1.6)
                    dds = all_dropdowns()
                    hit = pick_option(dds, option, box)
                if not hit:
                    log("  [%s] 还是找不到 %s；当前可见下拉=%s" % (
                        tag, option, [[i["t"] for i in d["items"]] for d in dds]))
                    close_dropdowns()
                    time.sleep(0.6)
                    continue
                click_box(hit)
                close_dropdowns()
                shown = page.evaluate(FORMITEM_TEXT_JS, name)
                log("  [%s] %s -> %s OK（回显: %s）" % (tag, name, option, shown))
                return True
            return False

        def _filt_bad(filt):
            """检查一份 payload filters 是否满足当前全部筛选要求，返回问题列表。"""
            bad = []
            fld = SALE_FIELD_BY_LABEL.get(SALE_LABEL, SALE_LABEL)
            want_sale = sorted(RANGE_VALUE[o] for o in
                               [x.strip() for x in SALE_OPTION.split("|") if x.strip()]
                               if o in RANGE_VALUE)
            got_sale = sorted(str(x) for x in (filt.get(fld) or []))
            if got_sale != want_sale:
                bad.append("%s=%s(期望%s)" % (fld, got_sale, want_sale))
            want_fans = RANGE_VALUE.get(FANS_OPTION)
            got_fans = [str(x) for x in (filt.get(FANS_FIELD) or [])]
            if got_fans != [want_fans]:
                bad.append("%s=%s(期望['%s'])" % (FANS_FIELD, got_fans, want_fans))
            if not filt.get(CONTACT_FIELD):
                bad.append("%s=%s(期望非空)" % (CONTACT_FIELD, filt.get(CONTACT_FIELD)))
            want_cate = CATE_ID_BY_NAME.get(CATE_PARENT)
            got_cate = [str(x) for x in (filt.get(CATE_FIELD) or [])]
            if want_cate and (not got_cate or got_cate[0] != want_cate):
                bad.append("%s=%s(期望%s)" % (CATE_FIELD, got_cate, want_cate))
            return bad

        def verify_filters():
            """用接口 payload 端到端校验筛选是否真的生效 —— 最可靠的校验。

            UI 上「选没选中」看不出来，但发出去的 filters 不会骗人。
            只要有任意一条请求满足全部条件就算通过。
            """
            last = None
            for q in reversed(reqs):
                try:
                    j = json.loads(q)
                except Exception:
                    continue
                f = j.get("filters")
                if isinstance(f, dict) and f:
                    last = f
                    if not _filt_bad(f):
                        log("  [verify] 接口校验通过：%s" % json.dumps(
                            {k: v for k, v in f.items() if v}, ensure_ascii=False)[:220])
                        return []
            if last is None:
                return ["没抓到带 filters 的 search_feed_author 请求"]
            bad = _filt_bad(last)
            log("  [verify] 最近一次 payload filters=%s" % json.dumps(
                {k: v for k, v in last.items() if v}, ensure_ascii=False)[:260])
            return bad

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
            nonlocal page       # 主页面可能被站点/用户关掉，需要改指向
            # 首次检查：**遍历所有标签页**（主页面可能已被关掉，只看它会误判未登录）
            hitpg, hit = _scan_pages()
            if hit:
                try:
                    alive = (page is not None) and (not page.is_closed())
                except Exception:
                    alive = False
                if not alive and hitpg is not None:
                    # 主页面没了 -> 把主页面改指向那个活着且已登录的页面
                    try:
                        hitpg.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
                        time.sleep(6)
                    except Exception as e:
                        log("   ⚠️ 回到达人广场失败：%s" % str(e)[:80])
                    page = hitpg
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

            # 主动把**可用的登录页**开出来：对着 marketing 落地页使用者找不到入口，
            # 而 buyin.jinritemai.com/login 已 404 —— 所以逐个候选试。
            try:
                lp = ctx.new_page()
                picked = ""
                for u in LOGIN_URLS:
                    try:
                        lp.goto(u, wait_until="domcontentloaded", timeout=60_000)
                    except Exception as e:
                        log("   ⚠️ 打开 %s 失败：%s" % (u, str(e)[:70]))
                        continue
                    bb = _body_of(lp, tries=3)
                    bad = any(m in bb for m in LOGIN_PAGE_BAD)
                    good = any(m in bb for m in LOGIN_PAGE_GOOD)
                    if good and not bad:
                        picked = u
                        break
                    log("   ⚠️ %s 不可用（%s），换下一个…"
                        % (u, "404/错误页" if bad else "未见登录表单"))
                if picked:
                    log("   ✅ 已在浏览器里打开登录页：%s" % picked)
                    log("      请在**那个 Edge 窗口**里登录（扫码 / 验证码都行），"
                        "本脚本不用管。")
                else:
                    log("   ⚠️ 候选登录页都不可用，请在 Edge 地址栏手动打开登录页。")
                try:
                    lp.bring_to_front()
                except Exception:
                    pass
            except Exception as e:
                log("   ⚠️ 自动打开登录页失败：%s" % str(e)[:100])
                log("      请在 Edge 地址栏手动打开登录页。")

            t0 = time.time()
            n = 0
            fails = 0                   # 连续复核失败次数
            while time.time() - t0 < LOGIN_WAIT_SEC:
                time.sleep(LOGIN_POLL_SEC)
                n += 1
                hitpg, hit = _scan_pages()
                if not hit:
                    if n % 12 == 0:         # 约每分钟报一次
                        log("   …仍在等待手动登录（已等 %d/%d 秒）"
                            % (int(time.time() - t0), LOGIN_WAIT_SEC))
                    continue
                log("✅ 检测到已登录（命中 %s），等了 %d 秒，继续采集。"
                    % ("/".join(hit), int(time.time() - t0)))
                # 登录常在新标签页完成 -> 回到达人广场复核一次再往下走。
                # ⚠️ 复核必须用「**刚检测到登录的那个页面 hitpg**」，
                #    不能用主页面 page —— 它可能已经被站点/用户关掉了。
                #    踩过：page 已关闭 -> goto 报 "Target page ... has been closed"
                #    -> 每 5 秒重来一次，**空转十几分钟不出结果**。
                vp = hitpg
                if vp is not None:
                    try:
                        vp.goto(DAREN, wait_until="domcontentloaded", timeout=90_000)
                        time.sleep(6)
                        b2 = _body_of(vp)
                        if any(m in b2 for m in LOGGED_IN_MARK):
                            log("   已回到达人广场，复核通过。")
                            try:
                                if page.is_closed():
                                    page = vp
                            except Exception:
                                page = vp
                            return True, "已登录"
                        log("   ⚠️ 达人广场复核未通过（第 %d 次），继续等待……" % (fails + 1))
                    except Exception as e:
                        log("   复核时出错（第 %d 次）：%s" % (fails + 1, str(e)[:90]))
                fails += 1
                if fails >= 5:
                    # 登录标记反复出现却复核不了（页面被关/被站点接管）：
                    # **绝不能再空转** —— 直接把主页面改指向那个活着的页面继续；
                    # 万一页面内容不对，后面类目筛选会走退出码 2 让驱动层重试
                    # （那时登录态已持久化，重试用的是同一个 profile）。
                    log("   ⚠️ 连续 %d 次复核失败，但登录标记反复出现 -> 直接继续" % fails)
                    try:
                        if page.is_closed():
                            page = vp
                    except Exception:
                        page = vp
                    return True, "已登录（复核未通过，直接继续）"
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
        # 用户 2026-09-16 改：结算总额 -> **直播结算总额 = 1w-10w**
        # 字段 common_range_selection_live_sales_30d_settle（只认直播带货的结算额）。
        # 单一选项，单选即可；要拼多档用 `|` 分隔（该下拉支持多选）。
        ok_sale = True
        for _opt in [o.strip() for o in SALE_OPTION.split("|") if o.strip()]:
            ok_sale = apply_formitem(SALE_LABEL, _opt, "sale") and ok_sale
        ok_fans = apply_formitem(FANS_LABEL, FANS_OPTION, "fans")
        ok_contact = apply_formitem("有联系方式", None, "contact")
        time.sleep(4)

        # 🔴 筛选项只要有一个没应用成功，就**直接中止**，绝不继续采。
        #    踩过（2026-09-17）：「粉丝量」的点击被上一个字段的下拉浮层盖住，
        #    3 次尝试全失败，但脚本照样跑完，采出一批**没有粉丝量约束**的名单。
        if not (ok_sale and ok_fans and ok_contact):
            log("!! 筛选应用失败（sale=%s fans=%s contact=%s）-> 中止本次采集"
                % (ok_sale, ok_fans, ok_contact))
            try:
                page.screenshot(path=os.path.join(OUT, "filter_fail.png"))
            except Exception:
                pass
            time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
            sys.exit(2)

        # 再用接口 payload 复核一次（UI 说成功不代表真的生效）
        bad = verify_filters()
        if bad:
            log("!! 接口校验：筛选未生效 %s -> 中止本次采集（避免采到错误名单）" % bad)
            try:
                page.screenshot(path=os.path.join(OUT, "filter_fail.png"))
            except Exception:
                pass
            time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
            sys.exit(2)

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
            # 取证：列出页面上有溢出的元素 —— 一眼分辨「真没渲染」vs「条件卡太严」
            try:
                for _h in (page.evaluate(DUMP_OVERFLOW_JS) or [])[:6]:
                    log("    · 溢出候选 gap=%-7d ch=%-6d sh=%-7d h=%-5d %s%s" % (
                        _h["gap"], _h["ch"], _h["sh"], _h["h"], _h["tag"],
                        ("." + _h["cls"]) if _h["cls"] else ""))
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
        # 护栏：容器一直找不到时别空转满 MAX_SCROLL 屏（2026-09-17 实测空转 50 屏、约 2 分钟）
        no_cont, NO_CONT_LIMIT = 0, 12
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
                no_cont += 1
                log("  滚动第 %d 屏：容器还没出现，等待中…（%d/%d）"
                    % (s + 1, no_cont, NO_CONT_LIMIT))
                if no_cont >= NO_CONT_LIMIT:
                    log("  !! 连续 %d 屏都定位不到滚动容器 -> 放弃本批翻页"
                        "（多半是表格没渲染出来；看上面「溢出候选」和截图判断）")
                    break
                time.sleep(2.5)
                continue                                        # 不计入 stall
            no_cont = 0
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
                    # 总额（保留：Excel/调试用，不是当前筛选口径）
                    "sale_low": (sinfo.get("total_sales_settle") or {}).get("sale_low"),
                    "sale_high": (sinfo.get("total_sales_settle") or {}).get("sale_high"),
                    # 当前筛选用：直播结算总额（2026-09-16 起）
                    "live_low": (sinfo.get("live_total_sales_settle") or {}).get("sale_low"),
                    "live_high": (sinfo.get("live_total_sales_settle") or {}).get("sale_high"),
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
                # 当前口径：直播结算总额 = 1w-10w（10000 ~ 100000）
                try:
                    return int(r["live_low"]) < 10000 or int(r["live_high"]) > 100000
                except Exception:
                    return False
            nf = sum(1 for r in rows if bad_fans(r))
            ns = sum(1 for r in rows if bad_settle(r))
            log("  校验：粉丝超10w %d 个 / 直播结算总额不在1w-10w %d 个" % (nf, ns))
            for r in rows[:8]:
                log("     %-20s fans=%-8s live=%s-%s gender=%s city=%s" % (
                    (r["nickname"] or "")[:18], r["fans"], r["live_low"], r["live_high"],
                    r["gender"], r["city"]))

        # ---------- 本地过滤 ----------
        seen, picked = set(), []
        stat = {"dup": 0, "male": 0, "region": 0, "noprov": 0, "nocate": 0,
                "catecombo": 0, "content": 0, "contentkeep": 0,
                "nickkw": 0, "nickbrand": 0}
        nick_drop = []                  # 记录被昵称规则剔除的样本，便于核对
        content_drop = []               # 记录被内容类型剔除的样本（新规则上线后要能核对）
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
            # 规则6：内容类型 —— **白名单优先**（用户 2026-09-17 改）
            #   命中 CONTENT_KEEP 任一项 -> 直接保留，不再看黑名单。
            #   例：「时尚+美食」以前被「美食」误杀，现在因为含「时尚」而保留。
            ct = r.get("content_type") or []
            if any(c in CONTENT_KEEP for c in ct):
                stat["contentkeep"] += 1
            elif any(c in CONTENT_EXCLUDE for c in ct):
                stat["content"] += 1
                if len(content_drop) < 40:
                    content_drop.append("%s(%s)" % ((r["nickname"] or "")[:14], "/".join(ct)))
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
        log("  内容类型白名单（%s）另有 %d 个达人被明确保留"
            % ("/".join(CONTENT_KEEP), stat["contentkeep"]))
        if nick_drop:
            log("  昵称被剔除样本：%s" % " | ".join(nick_drop))
        if content_drop:
            log("  内容类型被剔除样本：%s" % " | ".join(content_drop))

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
                            # 规则3b：带货商品名命中禁忌词（假发/院线/美甲/充电宝/3C数码…）-> 跳过
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
                            # 规则3e：商品名 **或** 店铺名含「养发」，且占比 > 50% -> 跳过
                            yskip, yratio, yhits, yall, ysample = yangfa_verdict(prows)
                            if yskip:
                                r["shop_rows"] = len(prows)
                                r["titles"] = [t for t in titles if t][:12]
                                r["yangfa_ratio"] = round(yratio, 3)
                                r["skip_reason"] = "带货含养发%.0f%%(%d/%d)" % (
                                    yratio * 100, yhits, yall)
                                verdict_cache[r["uid"]] = "skip"
                                log("   [%d/%d] %-20s 商品/店铺含「%s」%d/%d 件占 %.0f%%"
                                    " (>%.0f%%) -> 跳过该达人%s" % (
                                        i, cand_n, nick18, "/".join(YANGFA_KW),
                                        yhits, yall, yratio * 100, YANGFA_RATIO * 100,
                                        ("：" + ysample) if ysample else ""))
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
                                # --- 规则3d：低价铺货型（>=90% 商品 < 30 元）---
                                cskip, cratio, cn_ok, cn_all, cwhy = cheap_verdict(prows)
                                r["price_cheap_ratio"] = round(cratio, 3)
                                r["price_n"] = cn_ok
                                r["price_rows"] = cn_all
                                log("   [%d/%d] %-20s 带货 %d 件，最大品牌「%s」%d 件占 %.0f%% "
                                    "（Top3: %s）" % (
                                        i, cand_n, nick18, total, brand, top_cnt, ratio * 100,
                                        " / ".join("%s×%d" % (g[0], g[1]) for g in grp)))
                                log("   [%d/%d] %-20s 到手价：%d/%d 件可解析，<%.0f元 占 %.0f%%" % (
                                    i, cand_n, nick18, cn_ok, cn_all, CHEAP_PRICE, cratio * 100))
                                if cwhy == "fewprice":
                                    r["skip_reason"] = "价格样本不足·未判定(%d/%d)" % (cn_ok, cn_all)
                                    verdict_cache[r["uid"]] = "skip"
                                    log("   [%d/%d] %-20s ! 到手价只解析出 %d/%d 件"
                                        " -> 未判定，跳过该达人（不进入查微信）" % (
                                            i, cand_n, nick18, cn_ok, cn_all))
                                    break
                                if cskip:
                                    r["skip_reason"] = "低价铺货%.0f%%<%.0f元" % (cratio * 100, CHEAP_PRICE)
                                    verdict_cache[r["uid"]] = "skip"
                                    log("   [%d/%d] %-20s %.0f%% 的商品到手价 < %.0f 元"
                                        " (>=%.0f%%) -> 跳过该达人" % (
                                            i, cand_n, nick18, cratio * 100, CHEAP_PRICE,
                                            CHEAP_RATIO * 100))
                                    break
                                # --- 规则3c：去重店铺家数 <= 2 -> 跳过（专卖自己店的达人）---
                                sskip, scnt, slist = shopcnt_verdict(shops)
                                r["shop_cnt"] = scnt
                                if sskip:
                                    r["skip_reason"] = "带货店铺仅%d家" % scnt
                                    verdict_cache[r["uid"]] = "skip"
                                    log("   [%d/%d] %-20s 带货店铺仅 %d 家（<=%d）%s"
                                        " -> 跳过该达人" % (
                                            i, cand_n, nick18, scnt, MIN_SHOP_CNT,
                                            "：" + "/".join(slist[:3])))
                                    break
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
                                log("   [%d/%d] %-20s 店铺 %d 家 / 多家品牌（最大仅 %.0f%%）"
                                    " -> 继续查联系方式" % (
                                        i, cand_n, nick18, scnt, ratio * 100))
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
            # 【登记飞书用】取达人抖音号：点「达人抖音主页」→ 读抖音主页上的「抖音号」
            #   只对**取到联系方式的**达人取（省时间；没联系方式的也不会登记）
            #   ⚠️ 内部有防串号校验（点击前先确认主页是本人），失败返回空串，绝不写可疑值
            if got_val and not r.get("douyin_id"):
                try:
                    r["douyin_id"], r["douyin_nick"] = DID.fetch(
                        page, ctx, r["nickname"], log=log)
                except Exception as e:
                    log("   [%d/%d] %s 取抖音号异常: %s" % (
                        i, cand_n, r["nickname"], str(e)[:70]))
                log("   [%d/%d] %-22s 抖音号=%s" % (
                    i, cand_n, (r["nickname"] or "")[:20], r.get("douyin_id") or "✗ 未取到"))
            done.append(r)
            tail = ("跳过·" + r["skip_reason"]) if r.get("skip_reason") else (got_val or "✗ 未取到")
            log("   [%d/%d] %-22s %-12s 粉丝=%-7s %s=%s  (有效 %d/%d)" % (
                i, cand_n, (r["nickname"] or "")[:20], r["city"], r["fans"],
                got_type or "联系", tail, valid_n, TARGET_DAREN))

        picked = done

        # ---------- 带货规则跳过原因汇总（用户 2026-09-17 新增三条规则后要能一眼核对） ----------
        sk = {}
        for r in picked:
            sr = r.get("skip_reason") or ""
            if not sr:
                continue
            head = sr.split(":")[0].split("%")[0].split("(")[0]
            sk[head] = sk.get(head, 0) + 1
        if sk:
            log("  带货规则跳过汇总：" + " / ".join(
                "%s=%d" % (k, v) for k, v in sorted(sk.items(), key=lambda x: -x[1])))

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
