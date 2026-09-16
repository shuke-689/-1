# 抖音精选联盟 → 微信加达人 · 操作手册 (RUNBOOK)

> 本文件记录完整可复用的自动化链路。**新会话里看到「开始帮我添加微信」这类指令，
> 直接按本文第 3 节执行即可。**

---

## 0. 任务全景（用户的 7 步原始需求）

| # | 步骤 | 归属 |
|---|---|---|
| 1 | 打开 Edge，进精选联盟 | 阶段A |
| 2 | 筛选 个护家清/美妆 + 视频结算 1w-10w + 有联系方式 + 女性中小主播 + 排除海南/新疆/西藏/境外 | 阶段A |
| 3 | 点开达人 → 达人主页 | 阶段A |
| 4 | 点微信号右侧「眼睛」→ 再点「复制」→ 取到微信号 | 阶段A |
| 5 | 打开微信「添加朋友」，粘贴微信号搜索 | 阶段B |
| 6 | 昵称含「稿费」→ 跳过换下一个；搜不到 → 换下一个 | 阶段B |
| 7 | 点「添加到通讯录」→ 申请页点「填入」常用申请语 → 备注填达人名 → 点「确定」 | 阶段B |

---

## 1. 环境准备（每条 Bash 命令都必须带）

```bash
export PATH="/c/Users/Administrator/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"
cd /c/Users/Administrator/WorkBuddy/抖音
export PYTHONPATH='C:\Users\Administrator\WorkBuddy\抖音\.probe\libs'
PY="/c/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe"
```

**环境坑（务必记住）**
- Git Bash 默认 PATH 缺 `usr/bin`（`ls`/`head`/`dirname` 全部找不到）→ 必须上面的 `export PATH`。
- PowerShell 工具在此环境**无 stdout 输出** → 一律用 Bash。
- `reg.exe` 被安全策略黑名单拦截。
- **Bash 命令结束时其派生的后台进程会被回收** → 长流程必须放进**一个** `run_in_background` 任务里跑。
- 屏幕 3840x2160 单屏，坐标 = 物理像素。

---

## 2. 阶段A：精选联盟筛选采集 —— `collect.py`

**入口页面**：`https://buyin.jinritemai.com/dashboard/merchant/home`（商家版精选联盟）
→ 找达人：`https://buyin.jinritemai.com/dashboard/servicehall/daren-square`

**登录**：独立 Edge 配置 `.edge-auto/`，登录态持久化，**不随 git 分享**。

**⚠️ 登录策略 —— 跳过自动登录（用户 2026-09-16 定）**

**不再把 `login.py` 作为流程前置。** 采集器自己判断登录态：
- 已登录 → 直接开筛；
- 未登录 → **不中止**，会**主动 `ctx.new_page()` 打开可用登录页并
  `bring_to_front()`**，然后**停在原地等使用者自己在那个 Edge 窗口里登录**；
  轮询是**遍历所有标签页**的（登录常在新标签页完成），
  命中后会 `goto` 回 `daren-square` 复核一次再往下走。

🔴 **登录地址必须走候选列表（2026-09-16 踩到）**
`https://buyin.jinritemai.com/login` **已经 404（nginx/1.14.1）**。
当时未登录时把它打开，使用者看到的是一个 **404 白页**，自然登不进去
（表现为傻等 30 分钟超时）。现在按顺序试，挑第一个「像登录页」的：

```python
LOGIN_URLS = (os.environ.get("LOGIN_URL",""),
              "https://fxg.jinritemai.com/login/common?from=buyin",   # ✅ 实测可用
              "https://buyin.jinritemai.com/login")                   # ❌ 已 404
```
- 可用地址：`https://fxg.jinritemai.com/login/common?from=buyin`
  → 标题「抖店登录-抖店后台-抖音电商后台」，含**手机登录（手机号+验证码）/ 邮箱登录**。
  同域 `*.jinritemai.com`，cookie 与 `buyin` 通用（`stage1_login_probe.py` 用的就是它）。
- 判定「像不像登录页」：命中 `LOGIN_PAGE_GOOD` 且未命中 `LOGIN_PAGE_BAD`。
  ⚠️ `LOGIN_PAGE_GOOD` 里**绝不能放「登录」二字** —— 抖音电商 marketing 落地页
  右上角就有「登录」按钮，会把它误判成登录页。要用 `验证码 / 扫码 / 二维码` 这类
  只有真登录页才有的字样。

```bash
export LOGIN_WAIT_SEC=7200      # 等待上限（秒），默认 600；设 0 = 不等待，直接退出码 3
export LOGIN_POLL_SEC=5         # 轮询间隔（秒）
export LOGIN_URL=https://...    # 覆盖登录地址（会排到候选列表最前）
```

- 判定依据：登录后页面正文必含「主推类目」「找达人」「按商品找达人」。
- 登录过期后 `daren-square` 会跳到**抖音电商公开落地页**（右上角「登录」），
  采集器只表现为「**未找到类目按钮 个护家清**」——极容易误判成选择器坏了。
  现在这条判断已内置，不再需要人工先验。
- 等满 `LOGIN_WAIT_SEC` 仍未登录 → 截图 `out/collect/need_login<tag>_<i>.png`
  与 `login_timeout<tag>_<i>.png`（**每个标签页一张**）+ `sys.exit(3)`（驱动层中止全流程）。
- ⚠️ 不要在这里写 `except Exception: pass` 吞掉截图异常 —— 曾经因此**没有任何诊断线索**。
- `login.py` **保留但降级为可选辅助**（想在另一个终端先扫码时用）：
  ```bash
  "$PY" login.py --check     # 只检查，输出「已登录 / 需要重新登录」
  "$PY" login.py             # 打开浏览器调出二维码，等用户扫码（默认最长 900 秒）
  ```
  - `WAIT_SEC` 可调等待秒数（默认 900）；`POLL_SEC` 轮询间隔（默认 5）。
  - **`login.py` 两条加固（00:57 实测补上）**：
    1. 登录态判定**遍历所有标签页**（登录常在新标签页完成），命中后自动回
       `daren-square` 复核；
    2. 若当前页没出二维码（既无「扫码」字样也无 ≥120px 大图）→ **兜底新开标签页
       直开 `https://buyin.jinritemai.com/login`**。
       ⚠️ 实测在抖音电商 marketing 落地页上**点「登录」是不出二维码的**，所以必须有这条兜底。
  - 二维码/超时都落多张截图 `login_qr_*.png` / `login_timeout_*.png`。
  - ⚠️ `login.py` 等待期间**不会反复刷新页面**（否则会把二维码刷掉）；
    在浏览器里**干净关闭**才能把 cookie 落盘。
- ⚠️ 用户不在机器旁时别干等：`screenshot_desktop()`（`.probe/win_io.py`）全黑 = 屏幕锁定/息屏。

**退出码约定**
| 退出码 | 含义 | 驱动层动作 |
|---|---|---|
| 0 | 正常结束 | 读取 `darens_<tag>.json` |
| 2 | **类目按钮没点到**（页面布局/渲染抖动） | 冷却 `CATE_RETRY_WAIT`（45s）后重试 |
| 3 | **等满 `LOGIN_WAIT_SEC` 仍未登录** | 中止整个流程；调大 `LOGIN_WAIT_SEC` 或先跑可选辅助 `login.py` |

**运行（双类目：15 个个护家清 + 15 个美妆）**
```bash
export MAX_SCROLL=60 MAX_CANDIDATE=300
export BATCH_COOLDOWN=300 MAX_RETRY=3      # 批次冷却 + 限流重试
"$PY" collect_30.py          # 推荐：自动跑两批并合并出正式名单
```
> 也可以单类目跑：
> ```bash
> export CATE_PARENT=美妆 TARGET_DAREN=15 OUT_TAG=_mz
> "$PY" collect.py
> ```
> `TARGET_DAREN` = 取满多少个**有效达人**（成功取到联系方式）即停止筛选。
> `OUT_TAG` 给输出文件加后缀，避免分批跑互相覆盖。
> **别连跑两批**——平台会返回 `11001 请求过于频繁`（见下文「平台限流」）。
>
> 诊断探针（在 `.probe/`）：
> - `probe_login.py` —— 最小登录态诊断（URL / 标题 / 是否出现「登录」+ 截图）
> - `probe_api.py <类目>` —— 抓列表接口**请求体 + 返回码**（判断"没数据"还是"被限流"）
> - `probe_daren.py [uid]` —— dump 达人主页「带货分析」表格列头与行
> - `probe_filters.py <类目>` —— 逐个累加筛选条件看结果数
> - `test_rules.py` / `test_brand.py` —— 规则单测（28 + 11 组）

**为什么分两批**：主推类目筛选虽是**多选按钮**，但一个达人的 `main_cate` 是数组，
一次勾两个类目会变成"或"关系、**无法分别限量**。所以按类目分批跑（每批独立目标 15），
最后按 `uid` 去重合并。

**输出**
- `out/collect/darens.json` / `darens.csv` / **`darens.xlsx`**
- `darens.xlsx` = 用户指定的 **7 列登记表**：
  `达人名称 / 达人微信 / 达人粉丝 / 销售总额 / 直播结算总额 / 视频结算总额 / 图文结算总额`
  （`达人微信` 只填微信号；手机号达人不填。结算额度为区间文本，如 `10000-25000`）
- 分批中间产物：`darens_ghq.*`（个护家清）、`darens_mz.*`（美妆）
- 日志：`out/collect.log`、`out/collect_ghq.log`、`out/collect_mz.log`、`out/collect_30.log`
- 输出模块独立成 `darens_io.py`（collect.py / collect_30.py 共用）；openpyxl 装在 `.probe/libs`

**筛选条件（含 7 条业务规则）**

| 规则 | 条件 | 实现 |
|---|---|---|
| **规则1** | 主推类目 = **个护家清** 或 **美妆**（整个大类，含全部子类目），**15 + 15** | 点类目按钮展开 `auxo-cascader` 面板 → 点 `li.auxo-cascader-menu-item` 中文本为「**不限**」的项；回显「主推类目： 个护家清/不限」 |
| **规则4** | 达人主推类目必须命中 **个护家清 或 美妆** 其一；目标词条 = 个护家清 / 美妆 / 服饰内衣 / 母婴宠物 / 运动户外。<br>· 命中 **≥2 个** → 通过，**第三个及以后的类目不做任何限制**<br>&nbsp;&nbsp;（例：`个护家清/母婴宠物/食品饮料` ✔、`个护家清/美妆/食品饮料` ✔）<br>· 只命中 **1 个** → 带下列 **18 个搭档类目**任一即排除：食品饮料 / 滋补保健 / 宠物 / 图书教育 / 生鲜 / 本地生活 / 酒 / 智能家居 / 玩具乐器 / 鲜花园艺 / 3C数码家电 / 鞋靴箱包 / 虚拟充值 / 钟表配饰 / 珠宝文玩 / 医疗健康 / 原料包装 / 餐饮外卖 | 本地过滤 `cate_verdict(main_cate)`；`author_tag.main_cate` 是**顶级类目名数组**，如实测 `["个护家清","服饰内衣","美妆"]` |
| **规则6** | 达人**内容类型**不得为下列 **16 种**任一：三农 / 公益 / 人文社科 / 二次元 / 医疗健康 / 动物 / 教育校园 / 汽车 / 游戏 / 生活家居 / 社会时政 / 科技 / 科普 / 美食 / 职场 / 财经 | 本地过滤 `author_tag.author_label_rec_reasons[].reason`（**覆盖率实测 100%**；字段值＝平台「内容类型」选项名，共 40 项）|
| **规则5** | 每批取满 **TARGET_DAREN（15）个有效达人** 即停止该批 | 主循环里 `valid_n >= TARGET_DAREN` 就 `break` |
| | **结算总额 = 1w-10w**（2026-09-15 由「视频结算总额」改） | `common_range_selection_author_sale_gmv_30d_settle:["2"]` |
| | 粉丝量 = 10w 以下 | `fans_num:["1"]` |
| | 有联系方式 | `has_contact:true` |
| **规则3a** | 达人主页「带货分析」：**同一品牌占比 ≥ 50%**（且严格过半）→ 跳过 | `brand_verdict()`，阈值 `SAME_BRAND_RATIO`（默认 0.50）|
| **规则3b** | 带货**商品名**含 **假发 / 院线 / 美甲** 任一 → 跳过该达人 | `product_exclude_hit(titles)`，词表 `PRODUCT_EXCLUDE_KW` |

**结算类字段对照（实测自 `/square_pc_api/square/filter`）**

| 界面名称 | 接口字段 |
|---|---|
| **结算总额**（全部带货来源） | `common_range_selection_author_sale_gmv_30d_settle` |
| 直播结算总额 | `common_range_selection_live_sales_30d_settle` |
| 视频结算总额 | `common_range_selection_video_sales_30d_settle` |
| 图文结算总额 | `common_range_selection_picture_sales_30d_settle` |
| 橱窗结算总额 | `common_range_selection_window_sales_30d_settle` |
| 场均结算额 | `common_range_selection_author_square_average_gmv_settle` |
| 单视频结算额 | `common_range_selection_author_single_video_gmv_settle` |

> 区间选项文本统一为 `1w以下 / 1w-10w / 10w-100w / 100w-500w / 500w-1000w / 1000w以上`（value 1~6）。
> `FIND_FORMITEM_JS` 是**精确匹配**（`innerText !== name`），所以「结算总额」不会误撞「视频结算总额」。
> 达人详情里的实际数值在接口 `sale_info.*`：
> `total_sales_settle` / `live_total_sales_settle` / `video_total_sales_settle` / `image_text_total_sales_settle`
> （各含 `sale_low` / `sale_high` 区间）。

> 接口字段参考：个护家清 `main_cate_new:["5","5"]`、美妆 `main_cate_new:["9","9"]`。
> 可用环境变量覆盖：`CATE_PARENT` / `CATE_CHILD`（默认 个护家清 / 不限；
> 若只想取「个人护理」子类，设 `CATE_CHILD=个人护理`）。
> **类目若选不中，脚本会直接中止**（防止采到无关类目）。
> 平台内容类型选项共 40 个：三农/二次元/亲子/人文社科/休闲娱乐/传统文化/体育/公益/剧情/动物/
> 医疗健康/情感/摄影摄像/教育校园/文化/旅行/时尚/明星/母婴/汽车/法律/游戏/特效&小游戏/生活家居/
> 生活记录/电影/电视剧/社会时政/科技/科普/综艺/美食/职场/舞蹈/艺术/财经/音乐/颜值/其他。
> **注意**：用户口语「人文」相应平台正式名为「**人文社科**」。

**关键接口**
- 达人列表：`POST /square_pc_api/square/search_feed_author`
- 筛选定义：`GET /square_pc_api/square/filter`
- 联系账户：`GET /connection/pc/im/account`
- 达人主页：`/dashboard/servicehall/daren-profile?uid=<uid>&enter_from=1&scene=1&author_type=1`

**筛选交互坑（重要）**
- 「主推类目」是筛选栏里**直接可见的一排按钮**，点父类目会弹出 `auxo-cascader` 级联面板，
  面板内第一项就是「**不限**」（= 整个父类目）。选「不限」后回显为 `主推类目： 个护家清/不限`。
  （早期用 `text=美妆` 会误撞表格里的「美妆/个护家清」和店铺名 → 必须用精确选择器点。）
- 区间筛选是真·下拉：`div.auxo-form-item`（点击）→ `.auxo-select-dropdown`
  → 选项文本 `1w以下 / 1w-10w / 10w-100w / ...`。
- 「有联系方式」是开关型，点击即生效。

**达人主页流程（含规则3、规则7b）**
- URL：`/dashboard/servicehall/daren-profile?uid=<uid>`
- **规则3a（必须先执行，不许跳过）**：先进主页点 `div.auxo-tabs-tab` 里的「带货分析」
  → 读表格「**商品信息**」+「**店铺信息**」两列（实测列头 = 商品信息 / 店铺信息 / 到手价 /
  结算额区间 / 销量区间 / 关联直播场次 / 关联短视频数）：
  - **品牌聚类**：店名去掉店型后缀后，与已有簇代表词有 **≥2 字公共前缀** → 视为同一品牌。
    例：明希精选 / 明希个护严选 / 明希优品优选 → 同一簇「明希」
  - **跳过条件（两个都满足）**：① 最大品牌占比 **≥ `SAME_BRAND_RATIO`（默认 0.50）**；
    ② 该品牌件数**严格过半**（`cnt*2 > total`）
    - 加 ② 是防小样本误判：2 件商品来自 2 个不同品牌时字面各占 50%，但显然不是同一家
  - 多家品牌（最大占比 < 50%，或打平）→ 点回「概览」→ 继续取联系方式
- **规则3b**：**商品名**含 `假发 / 院线 / 美甲` 任一 → 跳过该达人（在品牌占比判定**之前**先查）
  - ⚠️ **tab 点不到 / 商品数据拿不到 = 未判定 → 直接跳过该达人**，
    绝不"未判定就进入查微信"（用户 2026-09-15 明确纠错）
  - tab 未渲染会**回顶部重试 3 次**；表格异步加载会**最多再等 4 次**（每次 2.2 秒）
  - 判定结果按 `uid` 缓存，重试时不重复判（否则每次重试白等 40 秒）
  - 日志会打印每个达人的「带货 N 件，最大品牌「X」M 件占 P%（Top3: …）」，可据此核实
- **规则7b（动态层）**：同一批带货店铺名聚类出的品牌词，若**昵称里出现** → 跳过。
  这是规则7的加强版 —— 用**该达人自己的真实带货数据**反查昵称，不依赖静态词表。
- 「达人微信号」右侧的**眼睛**：按该行 y 坐标就近匹配图标；
  **有两个闭眼时取最下方那个**；点开后同位置变复制图标，再点一次 → 剪贴板取值。
- 值若是 `********` 遮罩 → 视为无效，继续尝试复制图标。

**列表翻页（两个已踩过的坑）**
- 真实滚动容器是 `div.auxo-table-body`（约 1615×1150 @ (565,614)）。
- **坑A**：鼠标停在顶部筛选栏时 `page.mouse.wheel` 完全无效（滚的是外层窗口）
  → 曾出现"有时翻 17 屏得 246 个，有时翻 70 屏只得 7 个"。
- **坑B**：只按"gap 最大"挑容器会误选小面板（曾选到 276px 高的元素）。
- 对策：容器挑选**优先 `table-body`**（打分加权 1e6）；每轮先 `JS scrollTop += 3600`
  再把鼠标移到容器中心补一次 `wheel`；**连续 5 屏无新增**才判到底。

**⚠️ 平台限流（2026-09-15 踩到，最容易被误判成"该类目没数据"）**

- 症状：列表渲染成「**未找到相关达人，请调整筛选后重试**」，接口返回
  `{"code":11001,"msg":"请求过于频繁，请稍后再试"}`。
- **这不是没数据，是被限流。** 实测时间线：18:44 美妆能拿 461 个 →
  18:52 个护家清拿 292 个 → **紧接着的 18:59 美妆直接 0 个**，之后一路 0。
- 定位手段：抓 `search_feed_author` 的**请求体**（`filters` 结构与响应 `code`），
  探针见 `.probe/probe_api.py`。
- 现状对策（已内置）：
  - `collect.py` 监听**所有** `square_pc_api` 响应，命中 `11001` 立刻打日志并**停止滚动**，
    且**不用空名单覆盖已有产出**，只写 `out/collect/ratelimit_<tag>.txt` 标记。
  - 达人主页阶段命中限流 → 退避 `RATE_BACKOFF`（默认 90 秒）后继续。
  - `collect_30.py` 读到标记 → 冷却 `BATCH_COOLDOWN`（默认 300 秒）后重试该批，
    最多 `MAX_RETRY`（默认 3）次；**两批之间也强制冷却**。
- 相关环境变量：`BATCH_COOLDOWN` / `MAX_RETRY` / `DAREN_PAUSE`（达人间隔秒，默认 2.0）
  / `RATE_BACKOFF` / `SCROLL_PAUSE`（每屏等待秒，默认 2.8） / `CATE_RETRY_WAIT`。
- **结论：不要连跑多个批次；跑完一批最好等 5 分钟以上再跑下一批。**

**⚠️ 浏览器假死自动重启（2026-09-15 踩到）**
- 症状：`Page.evaluate: Execution context was destroyed` /
  `Page.goto: Navigation ... interrupted by another navigation`，
  每个达人主页都失败，**批次会把候选池白烧完**（实测系统休眠 4.5 小时后，
  一个批次空转 40 个候选人、0 收获）。
- 已内置：连续 4 次「上下文损坏」类异常 → `restart_browser()`
  重启 Edge 并重新挂响应监听，之后继续跑。
- ⚠️ 但**重启浏览器不能恢复登录**：登录态过期时，让使用者在重启后打开的 Edge
  窗口里手动登录即可（采集器会等待），或可选跑 `login.py` 重新扫码。

**⚠️ 类目按钮定位（2026-09-15 加固）**
- 早先 `FIND_CATE_JS` 用固定 y 区间 `[240,350]` 圈定筛选栏；
  页面出现引导条 / 已选行时按钮会落到区间外 → 报「未找到类目按钮」。
- 现改为：只认 `button|a.auxo-btn` 的**精确文本**、**排除表格内后代**、
  按 y 从上到下排序取最上面那个；重试 6 次，并在第 3 次时 dump 当前可见按钮文本便于诊断。

**本地过滤规则**
- 仅女性：`gender == 2`
- 排除区域：海南 / 新疆 / 西藏 / 香港 / 澳门 / 台湾 / 海外 / 国外
- **规则4**：`cate_verdict()` —— 必须命中 个护家清/美妆 其一；目标词条
  （个护家清/美妆/服饰内衣/母婴宠物/运动户外）命中 **≥2 个**则第三个及以后不限；
  只命中 1 个时才查 18 项搭档排除表
- **规则6**：`author_tag.author_label_rec_reasons[].reason` 不得命中 16 种排除内容类型
  （多标签时**任一命中即排除**）
- **规则7**：昵称排除，三层判定（`nick_exclude_hit()`）
  1. `NICK_EXCLUDE_KW`（10 个）：国际 / 全球 / 美业 / 供应链 / 折扣 / 厂家 / 大牌 / 养发 / 集团 / 防晒
  2. `NICK_BRAND_HINT`（12 个，品牌号/店铺号特征）：官方 / 旗舰 / 专卖 / 专营 / 授权 / 正品 /
     品牌 / 总代 / 总经销 / 企业号 / 官方号 / 品牌店
  3. `BRAND_KW`（185 个品牌词表）：蜜丝婷 / 珀莱雅 / 云南白药 / 百雀羚 / 花西子 …
  - 判定前统一走 `norm_name()` 归一化（去符号、转小写），所以 `SK-II` 与 `skii` 等价
  - **歧义词已刻意剔除**：`清风` / `霸王` / `大宝` 不在词表内
    （个人昵称里太常见；且真品牌号一定带「官方/旗舰」，由第 2 层兜住）
- **规则5**：取满 `TARGET_DAREN`（默认 30）个有效达人即停
- 按 `uid` 去重

---

## 3. 阶段B：微信加好友 —— `wechat_add.py`  ⭐

> **用户说「开始帮我添加微信」时执行本节。**

### 3.1 前置检查（必须）
1. 微信已登录。
2. **「添加朋友」窗口已打开** —— 用户在微信左下角「+」→「添加朋友」。
   窗口没开时脚本报 `找不到「添加朋友」窗口（请先在微信里点「+」→「添加朋友」）`。
3. 微信未被最大化的 Edge 完全遮挡（否则点击会打到 Edge 上）。

### 3.2 运行

```bash
# 正式跑（先跑 10 个，安全批量）
"$PY" wechat_add.py run --limit 10

# 看台账与剩余待加（多轮调度前先看这个）
"$PY" wechat_add.py status

# 演练（走完全流程但最后点「取消」，不真发申请）
"$PY" wechat_add.py run --limit 2 --dry

# 调试
"$PY" wechat_add.py probe                    # 看「添加朋友」窗口 OCR
"$PY" wechat_add.py probe-search <微信号>     # 搜一个号并 dump 结果页
```

**启动后立刻提醒用户：8-10 分钟内不要碰鼠标键盘。**

### 3.2.1 多轮台账（重要）

`run` 会读 `out/wechat/add_results.json`（**累积台账**）并跳过已完成达人，
**自动从上次断点继续，不会重复处理**；本轮结果**合并写入**（不覆盖历史）。

- 「已完成」= 状态属于 `sent / already / excluded / not_found`
- 不计入（下次会重试）= `unknown / error / risk_control`
- 剩余待加数量：`wechat_add.py status`
- 汇总表：`out/wechat/add_results.csv`（状态中文名 + 备注名 + 抖音达人 + 联系方式）

**实测节奏（2026-09-15）**：单轮 10 个不触发风控；但**连续累计约 24 次请求后必触发**。
→ 严格执行「**10 个/轮，轮间冷却 ≥2 小时**」，**不要连跑多轮**。

### 3.3 状态机

| 状态 | 含义 | 处理 |
|---|---|---|
| `sent` | 已发出好友申请 | ✅ 成功 |
| `excluded` | 结果昵称含「稿费」 | 跳过，换下一个 |
| `not_found` | 搜不到该用户 | 换下一个 |
| `already` | 已是好友 | 跳过 |
| `unknown` | 结果页无法识别 | 换下一个 |
| `no_apply_dialog` | 点「添加到通讯录」后没弹申请页 | 换下一个 |
| `risk_control` | **微信风控** | **立即 break，停止整个流程** |

### 3.4 微信 4.x 自动化的技术要点

微信 4.x 是 **Qt + MMUI 全自绘**，UIA 控件树为空（只有 2 个空 Pane）→
**只能**走：`截图 → RapidOCR 找字 → 换算屏幕坐标 → SendInput 注入键鼠`。

**窗口**
- 「添加朋友」和「申请添加朋友」都是**独立顶层窗口**，类名 `Qt51514QWindowIcon`。
- 「申请添加朋友」在点击「添加到通讯录」后才出现，**窗口 rect 与「添加朋友」不同**
  （例：添加朋友 2333,365,562,851 vs 申请页 1638,563,562,971）→
  **点击基准必须切到申请页窗口的 rect**。
- 每轮开始先 `dismiss_apply_dialog()` 关掉遗留申请页，否则它飘在上层挡住点击。

**申请页三步坐标（全都要动态定位，不能写死）**
- 布局会**随申请语行数上移**：申请语 1 行→3 行时，`备注`标签 y 从 372 → 299；
  而 `确定/取消` 固定在底部 cy≈903 不动。
- **「填入」**：OCR 常把它粘在提示语行尾（如 `55佣金，可以考虑下合作嘛填入`），
  取该行 box **右端 −9px** 最准（实测 (325,325) 生效）。
  兜底用蓝色像素簇（`b>120 && b-r>45 && b-g>20`），但**必须限制 x<宽−30 且取最密集 y 桶**，
  否则窗口右缘杂散像素会带偏均值（曾偏 18px 导致点击完全失效）。
- **备注框**：`备注`标签 cy **+62**，点 x = 窗口宽/2。微信会自动把微信昵称同步进备注。
- **确定**：底部固定，`确定` cx≈179 / `取消` cx≈383，cy≈903。

**通用**
- 点「添加到通讯录」后需 `sleep 3.2s` 再找申请页窗口。
- 搜索：聚焦搜索框 → `Ctrl+A` → `Delete` → 粘贴 → 点「搜索」（找不到则回车）→ `sleep 3.2s`。

### 3.5 风控（血的教训）

- **实测第 13 个好友申请开始触发**：「操作过于频繁，请稍后再试。」
  弹窗居中于「添加朋友」窗口，遮挡结果页 → OCR 表现为「结果页无法识别」。
- **一轮安全上限约 10-12 个**；两轮间隔 ≥ 2 小时；触发后当日不再重试。
- 脚本已内置自动停止：`RISK_KW` 关键词表 → `read_result` 返回 `risk_control`
  → `close_risk_dialog()` 关弹窗 → **`break` 停止整个流程**并记录停止原因。
- `fill_apply` 返回 `no_apply_dialog` 时会用 `detect_risk()` 复查（防止被弹窗挡判断）。

### 3.6 其他已知限制
- `wxid_xxxxx` 形式的**原始ID 无法通过微信搜索添加**（微信不开放该搜索），会走 `not_found`/`unknown`。

---

## 4. 输出物清单

| 文件 | 内容 |
|---|---|
| `out/collect/darens.json` / `.csv` | 阶段A 达人清单（含 contact / contact_type） |
| `out/collect.log` | 阶段A 日志 |
| `out/wechat_add.log` | 阶段B 实时日志（每轮清空重写） |
| `out/wechat/add_results.json` | 阶段B 结果（含 `add_status` / `add_note`） |
| `out/wechat/steps/*.png` | 每一步的截图（搜索页/申请页/前后对比），用于复盘 |

---

## 5. 底层工具（.probe/）

- **`win_io.py`** —— `find_window / list_windows / set_foreground / window_rect / move_window /
  click / click_in_window / paste_text / send_keys / get_clipboard / set_clipboard /
  screenshot_window / screenshot_region / screenshot_desktop`
  - 坑：ctypes 必须显式声明 `restype`，否则 64 位句柄被截断
    （`GlobalLock` 返回 NULL → memmove 访问违例）。`DWORD`/`ULONG_PTR` 别名要在使用前定义。
- **`ocr.py`** —— `ocr.ocr(img)` → `[{text, box, cx, cy, w, h, score}]`；`ocr.find(...)`；`ocr.dump(...)`

---

## 6. 安全铁律（绝不可违反）

1. **永不按窗口标题 `taskkill` / 认领窗口**——曾因按标题匹配误写用户记事本。
   只用「自己启动的 PID → 该 PID 的窗口」定位。
2. 任何会**抢占键鼠**的脚本，启动前必须先告知用户。
3. 涉及个人目录的批量操作一律先扫描、备份、再确认。
