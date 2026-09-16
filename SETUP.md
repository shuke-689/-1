# 上手指南（首次使用看这里）

抖音精选联盟达人筛选采集 → 微信自动加好友。两阶段全自动链路。

- 完整规则、接口字段、选择器与踩坑记录：**`RUNBOOK.md`**
- 触发词与执行流程（AI 用）：**`.workbuddy/skills/douyin-xuanlian-wechat/SKILL.md`**
- 多人协作与云端同步：**`.workbuddy/skills/douyin-xuanlian-wechat/references/SYNC.md`**

---

## 0. 硬性前提

| 项 | 要求 |
|---|---|
| 操作系统 | **Windows**（阶段B 依赖 Windows 窗口 API + 键鼠注入；阶段A 依赖本机 Edge） |
| WorkBuddy 桌面端 | 已安装（提供托管 Python 与 PortableGit） |
| Microsoft Edge | 已安装（playwright 用 `channel=msedge`，不额外下载浏览器） |
| 抖音精选联盟账号 | **你自己的**（巨量百应 / 精选联盟，需有达人广场权限） |
| 微信桌面版 | 已登录（阶段B 用） |
| 网络 | 能访问 `buyin.jinritemai.com` |

> 屏幕分辨率影响阶段B 的点击坐标（脚本按窗口 rect 动态换算，但要保证微信窗口完整可见）。

---

## 1. 五步跑起来

```bash
# ① 进入项目目录，加载可移植环境
cd <项目目录>
source tools/env.sh

# ② 装依赖（装进项目内 .probe/libs，不污染全局）
"$PY" setup_env.py
"$PY" setup_env.py --check        # 期望：全部依赖就绪 + 找到 Microsoft Edge

# ③ 登录你自己的精选联盟账号（会弹 Edge，用抖音 App 扫码）
"$PY" login.py

# ④ 跑规则单测，确认代码完好
"$PY" .probe/test_rules.py && "$PY" .probe/test_brand.py

# ⑤ 开始干活
"$PY" collect_30.py               # 阶段A：15 个个护家清 + 15 个美妆
```

微信端：先登录微信、打开「+」→「添加朋友」窗口，然后

```bash
"$PY" wechat_add.py status
"$PY" wechat_add.py run --limit 10
```

**跑微信阶段时，8-10 分钟内不要碰鼠标键盘。**

---

## 2. 产出在哪

| 文件 | 内容 |
|---|---|
| `out/collect/darens.xlsx` | **7 列达人登记表**（手动要的那份） |
| `out/collect/darens.json` / `.csv` | 同一份数据的原始版 |
| `out/collect_30.log` / `collect_ghq.log` / `collect_mz.log` | 阶段A 日志 |
| `out/wechat/add_results.json` / `.csv` | 阶段B 台账与汇总 |
| `out/wechat/steps/*.png` | 阶段B 每一步截图（复盘用） |

---

## 3. ⛔ 不要提交 / 不要外传的东西

`.gitignore` 已挡，`sync.py` 会二次拦截：

| 路径 | 为什么 |
|---|---|
| `.edge-auto/` | 459MB，且**含你的精选联盟登录 cookie** |
| `out/` | 达人名单**含微信号**等个人信息 |
| `.probe/libs/` | 370MB 平台相关二进制，用 `setup_env.py` 重建 |
| `.workbuddy/memory/` | 本机个人工作记忆 |

---

## 4. 和好友一起用

整个项目就是一个 git 仓库，**技能和规则文档都在仓库里**，
所以任何一方改了规则、脚本或文档，另一方 `pull` 一下就同步了。

**云端仓库**：<https://github.com/shuke-689/-1>（私有）
克隆：`git clone https://github.com/shuke-689/-1.git`

```bash
"$PY" sync.py pull                # 拉取对方的优化
"$PY" sync.py auto -m "说明改动"    # 提交并推送自己的优化
"$PY" sync.py status              # 看当前状态
```

首次绑定云端仓库：`"$PY" sync.py remote https://github.com/shuke-689/-1.git`

> 详细流程、平台选择、冲突处理：见
> `.workbuddy/skills/douyin-xuanlian-wechat/references/SYNC.md`
>
> **账号绝不共享**：好友 clone 后必须跑 `login.py` 扫**自己的**码，用**自己的**微信。

---

## 5. 出问题先看这里

| 症状 | 先做 |
|---|---|
| 采集报「未找到类目按钮」 | `"$PY" login.py --check` —— 十有八九是登录过期 |
| 页面显示「未找到相关达人，请调整筛选后重试」 | **平台限流 11001**，不是没数据；等 5 分钟再跑 |
| 报 `No module named xxx` | `"$PY" setup_env.py` |
| `git: command not found` | 用 `source tools/env.sh` 后再跑，或看 `tools/env.sh` 探到的 `$GIT` |
| 微信报找不到「添加朋友」窗口 | 先在微信里点「+」→「添加朋友」 |
| 其他 | `RUNBOOK.md` 第 2 节的「⚠️」小节 |

诊断探针：`.probe/probe_login.py`、`.probe/probe_api.py <类目>`、
`.probe/probe_daren.py [uid]`、`.probe/probe_filters.py <类目>`。

---

## 6. 合规与风控提醒

- **平台限流**：不要连跑批次，两批之间至少 5 分钟。
- **微信风控**：一轮 ≤10 个好友申请，两轮间隔 ≥2 小时，触发后当日停手。
- **不要试图绕过**任何平台风控。
- 达人联系方式属个人信息，采集与使用请自行确认符合当地法律与平台规则。
