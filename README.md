# GitScout
### 开源项目发现与研究平台

GitScout 是面向 GitHub 开源项目发现、趋势追踪、智能推荐与项目研究的本地 Web 工作台。

> Discover · Track · Recommend · Research

## 当前版本

- 产品需求基线：**v0.5.1**
- 技术工程版本：**0.5.0 · Recommendation Engine**
- 品牌：**GitScout**
- 运行模式：**Windows 本地 Web 工作台**
- 技术栈：**React + TypeScript + FastAPI + SQLite**
- 当前开发阶段：**M5 · 智能推荐**

## 文档

| 资源 | 说明 |
|---|---|
| [需求说明书](docs/requirements/GitScout_PRD_v0.5.1.md) | 产品功能、业务规则、数据要求和原型说明 |
| [HTML 交互原型](prototype/GitScout_v0.5.1.html) | v0.5.1 可直接在浏览器打开的交互原型 |
| [技术架构设计说明书 v1.0](docs/architecture/GitScout_Technical_Architecture_v1.0.md) | 正式技术选型、运行形态、数据库和接口边界 |
| [开发实施计划 v1.0](docs/development/GitScout_Implementation_Plan_v1.0.md) | 阶段、任务、测试和验收计划 |

## 技术选型

| 层级 | 技术 |
|---|---|
| 前端 | React + TypeScript + Vite |
| 后端 | Python + FastAPI |
| 数据库 | SQLite（Python 标准库 sqlite3） |
| 数据采集 | HTTPX + BeautifulSoup + GitHub REST API |
| 调度 | Python asyncio（单进程） |

不使用 PostgreSQL、Redis、Celery、Docker 或其他独立基础设施。

## Windows 本地启动

### 方式一：本地单地址运行

1. 安装 Python 3.11、Node.js 20+。
2. 首次构建前端：

```powershell
cd frontend
npm install
npm run build
cd ..
```

3. 双击根目录的 `start_gitscout.bat`。
4. 浏览器访问：

```text
http://127.0.0.1:8765
```

FastAPI 会提供前端构建产物和 API。默认只监听本机回环地址。

### 方式二：前后端开发模式

终端一：

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

终端二：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 请求代理到 FastAPI。

## 本地配置

首次使用可将仓库根目录的 `.env.example` 复制为 `.env`。后端启动时会读取该文件；已经存在的系统环境变量优先级更高。Trending 来源地址可通过 `GITSCOUT_TRENDING_URL` 覆盖。Stars 总榜可选配置 `GITHUB_TOKEN`，以提高 Search API 可用请求额度；也可通过 `GITSCOUT_GITHUB_SEARCH_INTERVAL_SECONDS` 调整请求间隔。GitHub Token 只配置在本地根目录 `.env`，不要提交真实 Token。



### 首次验证 Trending 采集

1. 启动 GitScout 并打开左侧“周期榜单”。
2. 选择日榜、周榜或月榜，点击“立即采集”。
3. 采集结束后，榜单从 SQLite 历史快照读取；切换历史批次不会重新访问 GitHub。
4. 在“采集记录”查看任务日志、返回数量、入库数量和失败原因。
5. 在“采集设置”分别配置日 / 周 / 月自动计划。三个计划默认关闭，启用后要求本地服务持续运行。

API 文档地址：`http://127.0.0.1:8765/docs`。健康检查：`http://127.0.0.1:8765/api/v1/health`。

若 GitHub 返回限流、访问拒绝或页面结构发生变化，任务会保留失败记录，不会生成成功榜单；可在采集记录中查看原因并重试。



### 首次验证 Stars 总榜

1. 在根目录 `.env` 中按需配置 `GITHUB_TOKEN`；只采集公开仓库时不强制要求 Token。
2. 启动 GitScout，打开左侧“Stars 总榜”。
3. 选择 Top 1,000 / 3,000 / 5,000 / 10,000、最低 Stars 阈值和是否包含 Fork。
4. 点击“开始采集”，页面会显示任务进度、历史扫描和分片覆盖详情。
5. 在“采集设置”中可单独启用 Stars 每日自动扫描；默认关闭。
6. 在“采集记录”查看请求数、获取数量、失败分片和重试关系。

Stars 扫描默认目标为 Top 5,000、最低 100 Stars。它是有边界的公开仓库排行榜，不是 GitHub 全站仓库清单。Search API 每个查询最多可返回 1,000 条，系统会按 Stars 区间递归拆分；同 Stars 桶仍超限时再按创建日期拆分。若 GitHub 返回不完整结果或某个分片失败，扫描状态会明确显示为部分覆盖。

## 当前已实现

### M2 · Trending 真实采集

- GitHub Trending 日榜、周榜、月榜 HTTPX 采集。
- BeautifulSoup 解析仓库名称、简介、语言、Stars、周期增量、Forks 和 Topics。
- 仓库主档 Upsert、Topics 同步和重复仓库去重。
- 每次采集创建独立历史快照，旧排名不会被覆盖。
- 采集任务、执行日志、失败快照、重试记录和原任务关联。
- 日 / 周 / 月独立自动调度，可配置执行时间与时区；默认关闭。
- 历史榜单查询、快照切换、语言 / Topic / 关键词筛选、排序和分页。
- 采集任务记录、失败重试和调度设置页面接入真实 API。

### M3 · Stars 总榜采集

- GitHub Search Repositories API，按 Stars 降序获取公开仓库。
- Stars 数值区间递归分片，单个查询不超过 Search API 1,000 条结果窗口。
- 同 Stars 桶超限时使用创建日期继续拆分；不可再拆分时记录失败，不伪装完整。
- 按 GitHub Repository ID 去重，并同步仓库主档、Topics 和 Stars 历史采样。
- 每次扫描独立保存快照、分片状态、incomplete_results、覆盖范围和错误说明。
- 支持 Top 1,000 / 3,000 / 5,000 / 10,000，最低 Stars 阈值和 Fork 开关。
- Stars 总榜、历史扫描、分片审计、任务详情和失败重试页面接入真实 API。
- Stars 每日自动采集可独立配置，默认关闭；支持时区和 Top-N 参数。

### M4 · 榜单与趋势分析

- 趋势总览读取真实历史快照，展示项目库规模、新晋上榜、跨周期热门、语言分布和 Topics。
- 展示最近 12 次所选周期快照的平均 Stars 走势，以及最新 Trending / Stars 采集状态。
- 历史快照对比支持同周期两批次选择，识别新晋、掉榜、排名上升、下降和不变。
- 对比结果支持关键词、语言和变化类型筛选，支持完整筛选结果 CSV 导出。
- 项目详情聚合仓库主档、Topics、感兴趣 / 研究状态、日周月上榜记录、当前连续上榜次数、周期排名走势、Stars 扫描历史和历史观测曲线。
- 从总览、Trending、Stars 总榜和项目库进入项目详情；所有分析读取 SQLite，不触发 GitHub 请求。
- 复用现有 SQLite 表，无新增数据库依赖或迁移。

### M5 · 智能推荐引擎

- 候选池由最近一次成功 Stars 扫描与评分窗口内成功的日 / 周 / 月快照去重合并，按 repository_id 识别。
- 综合平衡、趋势发现优先、长期价值优先三套权重预设；默认权重为 Stars 30%、日榜 15%、周榜 30%、月榜 25%。
- Stars 使用候选池内百分位；日榜最近 30 次、周榜最近 12 次、月榜最近 12 次成功快照计算上榜比例。
- 日 / 周 / 月最低有效样本分别为 10 / 4 / 3；不足时显示 N/A，并按可用权重重新归一化。
- 每次计算持久化算法版本、实际权重、候选池规模、数据截止时间、子分、总分、排名、推荐理由和覆盖信息。
- 推荐页支持批次历史、权重方案切换、优先关注 / 新兴潜力 / 长期稳定筛选、关键词 / 语言 / 主要贡献维度筛选和 CSV 导出。
- Stars 完整扫描超过 7 天或最近扫描不完整时明确显示数据提示；历史推荐批次不可覆盖。


- React 页面骨架与主要导航。
- 趋势总览页面读取 SQLite 汇总数据。
- 项目库页面读取项目主档。
- FastAPI 健康检查：`GET /api/v1/health`。
- 首页汇总：`GET /api/v1/dashboard/summary`。
- 项目列表：`GET /api/v1/repositories`。
- SQLite 初始数据模型和 SQL 版本迁移。
- WAL、外键、busy_timeout 和基础索引。
- Windows 本地启动入口。
- 数据库迁移与约束测试。

## 尚未接入

M4 趋势分析已通过 CI；M5 推荐引擎和推荐页面已通过 GitHub Actions CI。Windows 本机真实数据验证待进行；M6 感兴趣与研究工作区 CRUD、M7 本地备份恢复仍待开发。所有正式分析页面只使用本地真实采集数据，不以演示数据填充。

## 数据与安全

- 数据库默认位于 `data/gitscout.db`。
- 本地日志位于 `.runtime/logs/`。
- 数据库、Token、备份、日志、虚拟环境和 node_modules 不提交 Git。
- GitHub Token 仅允许由后端读取，禁止发送到浏览器。
- 默认只监听 `127.0.0.1`。

## 开发状态

| 里程碑 | 状态 |
|---|---|
| M0 · React / FastAPI 工程骨架 | 已提交 |
| M1 · SQLite 数据底座 | 已提交 |
| M2 · Trending 真实采集与调度 | CI 通过，Windows 本机联网验收待确认 |
| M3 · Stars 总榜采集与分片审计 | CI 通过，Windows 本机联网验收待确认 |
| M4 · 榜单与趋势分析 | CI 通过，Windows 本机数据验证待确认 |
| M5 · 智能推荐 | CI 通过，Windows 本机数据验证待确认 |
| M6 · 感兴趣与项目研究 | 待开发 |
| M7 · 本地交付与备份恢复 | 待开发 |

