# 云端共享与双向同步手册

> 配套 `sync.py`。本文件解决：「我和好友都能跑这套自动化，且任一方的优化都能同步给对方」。

## 1. 同步架构

```
                 ┌──────────────────────────────┐
                 │  云端 git 仓库（私有）         │
                 │  collect.py / RUNBOOK.md /    │
                 │  .workbuddy/skills/...        │
                 └───────┬──────────────┬───────┘
                         │ push/pull    │ push/pull
                 ┌───────▼──────┐  ┌────▼─────────┐
                 │  你（本机）    │  │  好友（本机）  │
                 │  自己的账号    │  │  自己的账号    │
                 └──────────────┘  └──────────────┘
```

**关键设计：技能就放在仓库内**（`.workbuddy/skills/douyin-xuanlian-wechat/`），
所以同步代码 = 同步技能 = 同步规则文档，一次 `pull` 全部到位，不存在"技能版本和对不上"的问题。

### 同步什么 / 不同步什么

| 类别 | 是否同步 | 说明 |
|---|---|---|
| `collect.py` / `collect_30.py` / `wechat_add.py` / `darens_io.py` / `login.py` | ✅ | 核心脚本，改动即共享 |
| `RUNBOOK.md` / `SETUP.md` / `requirements.txt` | ✅ | 规则与手册 |
| `.workbuddy/skills/douyin-xuanlian-wechat/` | ✅ | **技能本体**，随仓库走 |
| `.probe/*.py`（探针 + 单测） | ✅ | 诊断工具 |
| `.edge-auto/` | ❌ | 459MB + **含本人登录 cookie** |
| `out/` | ❌ | 达人名单**含微信号**，属个人信息 |
| `.probe/libs/` | ❌ | 370MB 平台相关二进制 |
| `.workbuddy/memory/` | ❌ | 本机个人工作记忆 |

好友 clone 之后**必须**跑 `"$PY" login.py` 扫**自己**的精选联盟账号；
微信端也用**自己**的微信账号。**账号不共享。**

---

## 2. 选哪个云端平台

| 平台 | 适合 | 注意 |
|---|---|---|
| **CNB**（cnb.cool，腾讯） | 国内网络快，体验最顺 | 需注册；可在 WorkBuddy 里装 CNB 连接器后由 AI 代管仓库/PR |
| **GitHub** | 通用、生态全 | 国内访问可能慢；私有仓库免费 |
| **Gitee** | 国内快 | 需实名 |
| 企业微信微盘 / 微云 | 只想"发一份给对方" | **没有版本合并**，做不到双向同步，仅适合首次分发 |

> **要双向同步就必须用 git 仓库**，网盘/微盘只能单向传文件。

**仓库务必设为「私有」**——里面虽有 `.gitignore` 挡着，但脚本逻辑、
账号运营策略仍属敏感信息。

---

## 3. 首次配置（仓库主人 / 你）

```bash
cd <项目根>
source tools/env.sh

"$PY" sync.py status                 # 会自动 git init（分支 main）
"$PY" sync.py remote <仓库地址>       # 例：https://cnb.cool/<你>/douyin-daren.git
"$PY" sync.py push -m "首次共享：采集+加好友全链路"
```

推送时若要求登录，按平台提示输入**账号 + 访问令牌（PAT）**。
建议用 PAT 而不是密码（GitHub 已不支持密码推送）。

**推送前自查**（`sync.py` 也会拦）：

```bash
"$GIT" status --porcelain | head -30     # 确认没有 .edge-auto/ 和 out/
du -sh .git                              # 不该出现几百 MB
```

---

## 4. 首次配置（好友）

```bash
# 1) 装好 WorkBuddy 桌面端，克隆仓库到一个本地目录
#    （WorkBuddy 里直接说「把 <仓库地址> 克隆到 <路径>」即可，或手动 git clone）
cd <克隆下来的目录>

# 2) 装依赖
source tools/env.sh
"$PY" setup_env.py
"$PY" setup_env.py --check        # 应显示「全部依赖就绪」+ 找到 Microsoft Edge

# 3) 登录自己的精选联盟账号（扫码）
"$PY" login.py

# 4) 试跑单测，确认规则完好
"$PY" .probe/test_rules.py && "$PY" .probe/test_brand.py

# 5) 准备微信端：登录微信桌面端，打开「+」→「添加朋友」窗口
```

之后照 `SKILL.md` 的触发词操作即可（「开始筛选达人」/「开始帮我添加微信」）。

---

## 5. 日常协作流程

### 改完东西要同步（改的人）

```bash
"$PY" .probe/test_rules.py && "$PY" .probe/test_brand.py   # 先保证全绿
"$PY" sync.py push -m "规则5：结算总额改为 1w-10w"
```

### 拿对方的优化（用的人）

```bash
"$PY" sync.py pull
# 若提示 requirements.txt 变了：
"$PY" setup_env.py
```

### 一句话搞定（推荐）

```bash
"$PY" sync.py auto -m "说明这次改了什么"
```

### 提交信息约定

写清「改了什么 + 为什么」，例如：

- `规则4：类目组合改为命中≥2个则第三个不限`
- `修复：类目按钮定位不再依赖固定 y 区间`
- `新增：假发/院线/美甲 商品名排除`

**一次改动一个提交**，别攒一大堆一起推——冲突时好定位。

---

## 6. 冲突处理

冲突 = 你和好友改了**同一个文件的同一处**。常见于双方同时改 `collect.py` 常量区。

```bash
"$PY" sync.py pull          # 会提示冲突
"$GIT" status               # 看哪些文件冲突（both modified）
```

打开冲突文件，会看到：

```
<<<<<<< HEAD
SAME_BRAND_RATIO = 0.50
=======
SAME_BRAND_RATIO = 0.70
>>>>>>> 好友的提交
```

改成人话（保留对的那个，或取个折中），删掉三行标记，然后：

```bash
"$GIT" add -A
"$GIT" rebase --continue
"$PY" .probe/test_rules.py && "$PY" .probe/test_brand.py   # 再测一遍！
"$PY" sync.py push -m "合并冲突：SAME_BRAND_RATIO 取 0.50"
```

**拿不准就喊 AI**：把 `git status` 输出贴给 WorkBuddy，说「帮我解冲突」。

### 降低冲突概率

- 改之前先 `sync.py pull`；
- 改完尽快 push，别攒着；
- 规则常量集中在 `collect.py` 顶部，两人别同时改同一段；
- 大改动开分支（`git switch -c feat/xxx`），做完再合回 `main`。

---

## 7. 回滚

```bash
"$GIT" log --oneline -n 15            # 找目标提交
"$GIT" revert <commit>                # 安全撤销（生成一个新提交）
"$PY" sync.py push -m "回滚：xxx 规则"
```

不要用 `git reset --hard` + 强推，会覆盖好友的提交。

---

## 8. 这个仓库特有的注意

- **登录态永远不共享**：`.edge-auto/profile` 被忽略是刻意的。
  好友跑 `login.py` 用的是他自己的账号，采集到的达人也是他自己账号可见的。
- **`out/` 不同步**：达人名单含微信号，属个人信息，不跨人传播。
  需要交接名单时，用 Excel 单独人工传递（并自行判断合规性）。
- **微信端只在 Windows 有效**：阶段B 依赖 Windows 窗口 API + 键鼠注入。
  阶段A 的采集也依赖本机 Edge。所以**没有 Windows 机器就别指望跑通**。
- **风控是账号级的**：好友触发风控不影响你，但**别共用账号**。
- **平台限流 11001 与两端同时跑**：两边同时段高频抓取有可能加剧限流，
  建议约定错开时间跑（例如你上午、好友下午）。
