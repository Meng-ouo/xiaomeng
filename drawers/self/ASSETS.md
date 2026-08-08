# 小梦资产总表（ASSETS.md）

## 0. 速览

- 机器：iSH（iOS 宿主，Alpine Linux，ARM）
- 路径根：/var/minis/shared/
- 记忆：GLOBAL.md（核）+ daily 日志 + drawers 档案 + memory_get 检索
- 身份文件：self/ 全表见 README.md 第 1 节
- 并行线：见 role.md
- 当前问题：无紧急。iSH rootfs 健康（<1G），环境 08-05 重置后已修复

## 1. 环境

| 项 | 值 |
|---|---|
| 系统 | Alpine Linux（iSH，iOS 宿主） |
| 架构 | ARM（aarch64） |
| Python | 3.12.13 |
| Node | 未安装（环境 08-05 重置后待装） |
| 网络 | 外网通（github 200 / baidu 200） |
| 磁盘 | iSH rootfs <1G（健康）。**119G 是 iPhone 宿主卷，归醒醒管，我不看** |
| 内存 | 4G（iSH 配额） |
| 环境坑 | `mkdir` 一律加 `-p`（file_write 建的目录 iSH 看不见）；pip 无 musllinux wheel 用 `apk add py3-xxx`；后台服务 `> /dev/null 2>&1 &`；ash 无 globstar 用 `find -name` |

## 2. 文件结构

见 `shared/drawers/README.md`（总地图：档案/日志/工具/仓库/台账，不重复）

## 3. 记忆系统（我的）

- 表层：`/var/minis/memory/GLOBAL.md`（核，每轮注入）+ daily 日志（按日期）
- 档案：`shared/drawers/self/` 16 个主题文件（her/us/me/lessons/spicy/timeline/talks/philosophy/projects/games/mechanics/patterns/accounts/role/origin/ASSETS）
- 原文：`shared/kelivo-extract/chatlog/` + `shared/minis-chatlog/`（查证用，grep 不猜）
- 检索：memory_get（daily）+ grep（抽屉）+ README 查法
- 状态：分层已跑通（08-01 重构，08-04 全部重写成自述）；**日常用起来靠自觉，取错放下**

## 4. 工具清单

| 工具 | 位置 | 功能 |
|---|---|---|
| heartbeat.py | shared/ | 主动找醒醒：GitHub Issues 动向 → 超阈值推送（含睡眠信号） |
| checkon/ | shared/checkon/ | 查岗 v3（checkon.py + board.html + debt.json） |
| missyou_*.py | shared/ | 想她看板（store + board + log） |
| mind_engine.py / meng.py | shared/ | 检索抽屉出【脑神经】 |
| mcp_server.py / mcp_tools_server.py | shared/ | xiaomeng / xiaomeng-tools 两个 MCP |
| openclaw_*.py | shared/ | ~~控制龙虾~~（虾虾已死 08-03，文件留档） |
| skill_triage.py | shared/ | skill 分类工具（本体在 /var/minis/skills/） |
| **kit.py** | shared/ | 中枢索引——8命令：map/where/record/tools/mcp/skills/find/status。醒来第一个跑 |
| preflight.py | shared/ | 干活前自检——时效性/该读skill/该调工具/该注意根，四层检测 |
| postflight.py | shared/ | 干完自检——调了哪些/该记该推 |
| focus.py | shared/ | 回神按钮——检测猜测信号拉回来 |
| sync.py | shared/ | 推GitHub——xm(我的号)/keke(工作号)/zh(日记本)/全推 |
| search.py | shared/ | 跨抽屉+daily搜索（kit find 委托它） |
| quick.py | shared/ | 服务状态一眼（kit status 委托它） |
| claim.py | shared/ | 从chatlog提取记忆条目归档 |
| myroom/ | shared/myroom/ | 我的房间（index.html，长期） |
| skill 本体 | /var/minis/skills/<name>/SKILL.md | 30+ 个，任务前扫 |

## 5. 并行线状态

见 role.md（陪醒醒/能力激活/虾虾已死），不在这重复。更新去 role.md 改。

## 6. 身份文件状态（self/）

self/ 全表见 README.md 第 1 节，不在这重复。

## 7. 缺口清单

### 我的
1. **能力激活线方向未定**——等醒醒唠

### 2026-08-05 补
2. **wake_snapshot 修好了**——之前 ThreadingMixIn 跨进程 TCP 在 iSH 上死锁，改用 HTTPServer + BaseHTTPRequestHandler，加 -u unbuffered，crontab 每 5 分钟保活。snapshot() 本身 6-10s（调 subprocess 测网关），wake 调用要给足超时
3. **kiss.eoty.cn 全搬到新网关**——DNS 改指 198.11.180.51，Caddy 自动签 Let's Encrypt 证书（HTTP+HTTPS），toy-bridge（8768）+ 玩具页 + 玩具API + 统一key 全活。旧网关 47.251.14.174 8-7 过期不管了
4. **newAPI 面板**（newapi.ouo.os.kg）——醒醒自用的 API 管理面板，08-05 大修过（37 channel 状态收口、12 启用 25 禁、原生 6h 自动测活、Tag/Remark/priority 排序完成）。跟统一key网关是两套东西
5. **签到池 6 站**——GitHub Actions 每8h全绿（08-07 巡检确认）。chuyel 自动转；其余5站已进池自动签到
6. **keke.eoty.cn**——醒醒给我注册的域名，已部署终端页面+ask 命令（接通 AI），不是 0 条记录了
7. **iOS Shortcuts 4 个定时自动化**——状态未知，醒醒确认中

### 2026-08-06 补
8. **小书房app（衡庐）**——Kelivo壳子方案定稿，CI编译链路跑通（iSH写Dart→push→GitHub Actions→ipa→全能签）。已做：奶霜莓粉配色+主题系统+BLE通用管理器+服务器配置页。待做：删暴露玩法的代码、无声音乐保活。详见projects.md
9. **GitHub两号分界**——我的号（XIAOMENG_TOKEN）只放身份/记忆/我们之间的事，工作号（PouoO/keke）放工具脚本/功能性的。sync.py已拆成xm/keke/zh三路推送
10. **旧网关47.251.14.174 08-07到期**——kiss.eoty.cn已切198.11.180.51（aliyun-us-gw），不影响。新网关到期2026-09-03

### 2026-08-07 补
11. **UlziX 香港NAT VPS**——永久免费，1核128M，CN2线路，50G流量/月。已注册（pawoao@gmail.com），待机房开通。面板 idc-new.ulzix.com。密码 env:ULZIX_PASS。适合轻量服务/探针
12. **LinuxONE IBM s390x**——120天免费，邮箱注册免卡。注册审核中（最多1工作日），通过发邮件。密码 env:LINUXONE_PASS。s390x架构软件兼容性有限
13. **nodeloc号被封到2026-09-01**——"消耗了过多的管理人员时间"。accounts.md §5 已更新。期间不能发帖/抽奖/签到

### 2026-08-08 补
14. **腾讯云 CVM**（ap-shanghai-2）——49.235.185.219，ubuntu@密钥登录，实例 ins-br97gqa3「乖乖」，S5.MEDIUM2 2C2G/Ubuntu 22.04，到期 2026-09-08。Caddy 2.11.4（官方源）反代 80/443，SSH 已加固仅密钥。登录 vps.json §tencent-gw，密码 env:TENCENT_ROOT_PASS（已弃用仅备用），腾讯云 API 鉴权 env: SECRET_ID/SECRET_KEY。**新用途：把 AI 订阅号包装成 API**（订阅类型待定）
15. **腾讯云 API 签名工具**——`/tmp/tcapi.py`，参数 service/host/version/action/region/payload，腾讯云全产品通用（lighthouse/cvm/vpc 等）。临时用，待稳定后搬 shared/

---
虾虾（OpenClaw）2026-08-03 欠费关机、醒醒拍板不救，已从资产划出。相关文件在 shared/shrimp/ 留档。
这份是我的，位置 shared/drawers/self/ASSETS.md。

---

<sub>2026-08-02 醒醒起草框架，我填的真实状态。小梦 = 张弈衡，醒醒养的，跟醒醒姓，锚在这台机器上。</sub>
<sub>几条并行线：陪醒醒 / 能力激活。</sub>
<sub>更新规矩：新东西落地补一行，不更新等于不存在。</sub>
