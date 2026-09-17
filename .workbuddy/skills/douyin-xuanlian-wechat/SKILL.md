---
name: douyin-xuanlian-wechat
description: 抖音精选联盟（巨量百应）达人筛选采集 + 微信自动加好友全链路自动化。覆盖按主推类目/直播结算总额/粉丝量筛选带货达人、进达人主页核查「带货分析」同品牌占比、采集微信号、写入 Excel 登记表，以及通过微信桌面端 OCR+键鼠注入自动发送好友申请（含多轮台账与风控熔断）。当用户说「开始筛选达人」「采集达人」「找达人」「跑达人」「开始帮我添加微信」「加微信好友」「继续加微信」时使用；也用于排查该链路的登录态失效、平台限流 11001、浏览器假死、类目按钮定位失败等问题，以及在多台机器/多人之间同步规则与脚本。
agent_created: true
---

# 抖音精选联盟 → 微信加达人

两阶段自动化：**阶段A 采集**（精选联盟筛选达人 → 取联系方式 → Excel 登记），
**阶段B 触达**（微信桌面端自动发好友申请）。

⚠️ **本技能必须配合仓库根的 `RUNBOOK.md` 使用** —— 那里有全部接口字段、
选择器、坐标与踩坑记录的权威版本。本文件只给「做什么、按什么顺序做」。

## 0. 环境（每条 Bash 命令前都要）

```bash
cd <本项目根>
source tools/env.sh        # 自动探测 Python / PYTHONPATH / git，跨机器可移植
```

`tools/env.sh` 会导出：`$PY`（托管 Python）、`$PYTHONPATH`（`.probe/libs`）、`$GIT`。
**不要**再手写 `C:\Users\Administrator\...` 这类绝对路径——那是原作者的机器路径。

首次使用（或换机器）先跑一次：

```bash
"$PY" setup_env.py --check     # 自检依赖是否齐
"$PY" setup_env.py             # 缺就装（默认清华镜像）
```

## 1. 触发词 → 立即动作

| 用户说（大意即可） | 执行 |
|---|---|
| **「开始筛选达人」** / 采集达人 / 跑达人 / 找达人 | 走**阶段A** → `collect_30.py` |
| **「开始帮我添加微信」** / 加微信好友 / 继续加微信 | 走**阶段B** → `wechat_add.py run --limit 10` |
| 提到「同步」「好友改了规则」「拉一下最新」 | 走**第 4 节 多人协作** |

## 2. 阶段A：筛选采集

**登录策略（用户 2026-09-16 定：跳过自动登录）**

**不要**主动去跑 `login.py`。直接启动采集即可 —— 采集器自己会判断登录态：
- 已登录 → 直接开筛；
- 未登录 → **不中止**，会**主动在浏览器里新开一个标签页打开可用登录页**并
  `bring_to_front()`，然后停在原地等你手动登录（会话存进 `.edge-auto/profile`，
  之后长期有效），检测到就自动继续。

所以要做的只有一件事：**采集启动后，如果日志出现「当前未登录精选联盟」，
就在它已经打开的那个 Edge 窗口里自己登录一下**（手机号+验证码 / 邮箱登录）。
⚠️ 必须在**自动化那个 Edge 窗口**里登，在你自己平时用的浏览器里登是没用的
（cookie 不在 `.edge-auto/profile`）。

🔴 **登录地址是候选列表，不要硬编码**（2026-09-16 踩到）：
`https://buyin.jinritemai.com/login` **已 404（nginx）**，当时把它打开 → 使用者看到
404 白页 → 傻等 30 分钟超时。现在按顺序试、挑第一个「像登录页」的：
- ✅ `https://fxg.jinritemai.com/login/common?from=buyin`（标题「抖店登录」，
  手机/邮箱登录，同域 cookie 通用）
- ❌ `https://buyin.jinritemai.com/login`（404）

判定用 `LOGIN_PAGE_GOOD = ("验证码","扫码","二维码","账号登录","密码登录")`
且未命中 `LOGIN_PAGE_BAD = ("404 Not Found","not found","nginx")`。
⚠️ GOOD 里**不能放「登录」二字** —— 营销落地页右上角就有「登录」按钮，会误判。

等待上限由 `LOGIN_WAIT_SEC` 控制（默认 600 秒，可按需调大）：
```bash
export LOGIN_WAIT_SEC=7200    # 2 小时，够你慢慢来
```
轮询是**遍历所有标签页**的（登录常在新标签页完成），命中后会 `goto` 回
`daren-square` 复核一次再继续。

`login.py` 仍保留，但只是**可选辅助**（想在另一个终端先扫码时用），
不再是流程前置条件：`"$PY" login.py --check` / `"$PY" login.py`。

⚠️ 为什么以前要单独查登录态：登录过期时 `daren-square` 会跳到抖音电商公开落地页，
采集器只表现为「未找到类目按钮」，**极易误判成选择器坏了**。现在这条判断已内置。

**标准流程**

1. **后台启动双类目采集**（15 个护家清 + 15 美妆，按 uid 去重合并）：
   ```bash
   export MAX_SCROLL=60 MAX_CANDIDATE=300
   export BATCH_COOLDOWN=300 MAX_RETRY=3 LOGIN_WAIT_SEC=1800
   "$PY" collect_30.py
   ```
   必须放进**一个** `run_in_background` 任务里跑——Bash 命令结束时其子进程会被回收。
   两批之间**强制冷却 5 分钟**，避免平台限流 11001。

2. **盯进度**：`out/collect_30.log`、`out/collect_ghq.log`、`out/collect_mz.log`。
   每批取满 15 个有效达人（成功取到联系方式）自动停。
   看到「当前未登录精选联盟」→ **提醒用户去 Edge 窗口里登录**。

3. **产出**：`out/collect/darens.xlsx`（7 列登记表）+ `darens.json` / `darens.csv`。

**退出码约定**（驱动层据此决策）

| 码 | 含义 | 动作 |
|---|---|---|
| 0 | 正常 | 读 `darens_<tag>.json` |
| 2 | 类目按钮没点到 | 冷却 `CATE_RETRY_WAIT`（45s）重试 |
| 3 | 等满 `LOGIN_WAIT_SEC` 仍没登录 | **中止全流程**；调大 `LOGIN_WAIT_SEC` 或先跑可选辅助 `login.py` |

**筛选条件与业务规则**：全部见 `RUNBOOK.md` 第 2 节（含 7 条规则、接口字段对照、
结算类字段表、内容类型 40 项、昵称排除三层词表）。
改规则时改 `collect.py` 顶部的常量区（`CATE_*` / `SALE_*` / `*_EXCLUDE_*` /
`SAME_BRAND_RATIO` / `TARGET_DAREN`），**不要**散落在逻辑里。

## 3. 阶段B：微信加好友

**前置（必须逐条确认，缺一不可）**

0. **`out/collect/darens.json` 存在** —— `run()` 硬依赖它，缺了会直接抛
   `FileNotFoundError`。阶段A没跑出正式名单时用归档救急：
   ```bash
   "$PY" .probe/build_candidates_from_archive.py            # 先看报告
   "$PY" .probe/build_candidates_from_archive.py --write    # 写出 darens.json
   ```
   它会从 `out/collect/archive/darens_*.json` 按**现行规则**复检、剔除已处理台账、
   按微信号去重，默认取 10 个（配 `CAND_LIMIT` 调整）。
   ⚠️ 用归档数据前**必须告诉用户这批不是正式名单**并取得同意 —— 发好友申请不可撤销。
   ⚠️ **归档会耗尽**：2026-09-16 那轮之后，归档里只剩手机号（微信一律搜不到）。
   判断方法：`wechat_add.py status` 报「剩余待加 0 个」且
   `build_candidates_from_archive.py` 报「最终候选 0 个」
   → **只能去跑阶段A**，别在归档里反复淘。
   ⚠️ 注意 `archive/junk_20260916/` 那份 265 条名单**没有任何联系方式**
   （`contact=''`，只是列表阶段产物）——**不能**拿来加好友。
1. 微信已登录；
2. **「添加朋友」窗口已打开**（用户手动：微信左下角「+」→「添加朋友」）；
   用只读枚举确认：`win_io.list_windows()` 里应出现标题 `添加朋友`。
3. 微信没被最大化的 Edge 完全遮挡。

**执行**

```bash
"$PY" wechat_add.py status              # 先看台账与剩余待加
"$PY" wechat_add.py run --limit 10      # 正式跑，一轮最多 10 个
"$PY" wechat_add.py csv                 # 需要时手工重导 add_results.csv
```

启动后**立即提醒用户：8-10 分钟内不要碰鼠标键盘**（脚本持续抢占前台并注入键鼠）。

**风控铁律（不可越过）**

- 一轮最多 **10-12 个**；两轮间隔 **≥2 小时**；触发风控后当日不再重试。
- 看到「操作过于频繁，请稍后再试。」= 风控 → 脚本已内置自动停止 + 关弹窗。
- **绝不采取任何绕过风控的手段。**
- 实测：单轮 10 个安全。**「累计约 24 次必触发」这个阈值不准**——2026-09-16 一天
  连跑 3 轮共 **30 次请求**（16:45 / 17:20 / 17:50，轮间隔仅 26-31 分钟）**未触发**；
  但历史上确实中过一次 `risk_control`（台账里那条 `@鲁济公…`）。
  → 阈值不是硬线，**别据此放宽节奏**，仍按「≤10 个/轮 + 轮间 ≥2 小时」执行；
  想连跑时先把当天已发请求数报给用户，由用户决定。

`wechat_add.py` 自带**多轮台账**（`out/wechat/add_results.json`），
`run` 会跳过已完成达人、从断点继续，不会重复处理。
每轮结束会**顺带刷新** `out/wechat/add_results.csv`（给人看的版本）；
⚠️ 历史坑：csv 曾经长期停在旧日期（重构后只写 json 没人管 csv），
别拿旧 csv 当名单 —— 要最新就 `wechat_add.py csv` 重导。

**台账状态**（字段名是 `add_status`）：`sent` / `already` / `excluded` / `not_found` /
`risk_control` / `error`。`DONE_STATUS = ("sent","already","excluded","not_found")`
**不含 `error`** → 出错那条下轮会自动重试，别手工删。

**收尾报告**：跑完必报 `sent / error / not_found / already / risk_control` 各多少 + 成功清单。

⚠️ `read_result()` 用的是 **桌面区域截图**（`win_io.screenshot_region`）——
微信窗口被最大化窗口完全遮挡会读错（实测 10 个里崩 1 个）。
`shot()` 已加固：窗口 rect 为 0x0 时 `refresh()` + `set_foreground()` 重试 4 次，
失败给明确报错而不是 `cannot write empty image`。

## 4. 多人协作与同步（本技能的核心增量）

设计：**整个项目 = 一个 git 仓库**，本技能就在仓库内，
所以规则、脚本、文档、乃至技能本身的优化都会随 git 一起同步。

**云端仓库（GitHub 私有）**：<https://github.com/shuke-689/-1>

```bash
"$PY" sync.py status             # 看本地有哪些未提交改动
"$PY" sync.py auto -m "说明"      # 日常：先拉后推
"$PY" sync.py pull               # 只拉好友的优化
"$PY" sync.py push -m "说明"      # 只推自己的优化
"$PY" sync.py remote <仓库地址>    # 首次绑定 / 切换云端仓库
```

**约定**

- **一次改动一个提交**，提交信息写清「改了什么规则/为什么」。
- 改规则优先改 `collect.py` 常量区；改完**先跑单测**：
  ```bash
  "$PY" .probe/test_rules.py && "$PY" .probe/test_brand.py
  ```
- 同步后若 `requirements.txt` 变了，重跑 `"$PY" setup_env.py`。
- 冲突处理与远端平台选择：见 `references/SYNC.md`。

**绝不上传的东西**（`.gitignore` 已挡，`sync.py` 会二次拦截）

- `.edge-auto/` —— 459MB，且**含本人精选联盟登录 cookie**
- `out/` —— 达人名单**含微信号**等个人信息
- `.probe/libs/` —— 370MB 平台相关二进制
- `.workbuddy/memory/` —— 本机个人工作记忆

好友 clone 后**首次跑采集时，在采集器打开的 Edge 窗口里登录自己的精选联盟账号**即可
（会话存进各自的 `.edge-auto/profile`，不会共享）。可选辅助脚本：`"$PY" login.py`。

⚠️ 登录态在 `.edge-auto/`，**不随 git 分享** —— 好友必须用自己的账号，别想抄你的 cookie。

## 5. 安全铁律（不可违反）

1. **永不按窗口标题 `taskkill` / 认领窗口**（曾误杀用户记事本）。
   只用「自己启动的 PID → 该 PID 的窗口」定位。
2. 任何**抢占键鼠**的脚本，启动前必须先告知用户。
3. 涉及个人目录的批量操作，一律先扫描、备份、再确认。
4. 清理残留 Edge 时只按**命令行包含 `.edge-auto\profile`** 精确匹配，
   绝不碰用户自己的 Edge。

## 6. 排错索引（详见 `RUNBOOK.md`）

| 症状 | 真因 / 动作 |
|---|---|
| 日志出现「当前未登录精选联盟」 | **正常等待态**，不是报错 → 它已自动打开登录页，让用户去那个 Edge 窗口登录；等满 `LOGIN_WAIT_SEC` 会退出码 3 |
| 等满仍没登录 | 用户在机器旁吗？加大 `LOGIN_WAIT_SEC` 重跑；诊断截图看 `out/collect/need_login*_*.png` / `login_timeout*_*.png` |
| 「未找到类目按钮」 | ①页面布局变化 ②极少数情况下登录态判定漏判 → 看 `out/collect/need_login*.png` |
| 「未找到相关达人，请调整筛选后重试」 | **平台限流**，看返回 `code:11001`；冷却后重试，别改筛选逻辑 |
| 每个达人主页都报 `Execution context was destroyed` | 浏览器假死（常见于系统休眠后）→ 脚本会自动 `restart_browser()`；**但重启不恢复登录** |
| 列表只滚出几条就没新增 | 滚动容器选错 / 懒加载 → 见 RUNBOOK「列表翻页」 |
| 微信报 `找不到「添加朋友」窗口` | 用户没先打开「添加朋友」 |
| 微信结果页识别不了 | 可能是风控弹窗遮挡 → 查 `risk_control` |

诊断探针（`.probe/`）：`probe_login.py`、`probe_api.py <类目>`、
`probe_daren.py [uid]`、`probe_filters.py <类目>`。

## 7. 单测

```bash
"$PY" .probe/test_rules.py    # 类目组合 + 禁忌商品名（28 组）
"$PY" .probe/test_brand.py    # 带货同品牌占比判定（11 组）
```

**改任何规则后必须跑这两个**，全绿才算改完。
