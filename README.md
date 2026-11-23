# GitScout
### 开源项目发现与研究平台

GitScout 是面向 GitHub 开源项目发现、趋势追踪、智能推荐与项目研究的本地 Web 工作台。

> Discover · Track · Recommend · Research

## 当前版本

- 产品需求基线：**v0.5.1**
- 技术工程版本：**0.2.0 · Trending Collector**
- 品牌：**GitScout**
- 运行模式：**Windows 本地 Web 工作台**
- 技术栈：**React + TypeScript + FastAPI + SQLite**
- 当前开发阶段：**M2 · Trending 真实采集与历史快照**

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

首次使用可将仓库根目录的 `.env.example` 复制为 `.env`。后端启动时会读取该文件；已经存在的系统环境变量优先级更高。Trending 来源地址可通过 `GITSCOUT_TRENDING_URL` 覆盖。GitHub Token 只配置在本地根目录 `.env`，不要提交真实 Token。

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

Stars 总榜真实采集、周期排名对比、推荐评分服务、感兴趣标记 API 和研究工作区 CRUD 尚未完成。Trending 页面已接入真实采集链路；尚无采集记录时会显示真实空状态，不会用演示数据填充。

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
| M2 · Trending 真实采集与调度 | 已提交实现，等待 CI 与本机验收 |
| M3 · Stars 总榜采集 | 待开发 |
| M4 · 榜单与趋势分析 | 待开发 |
| M5 · 智能推荐 | 待开发 |
| M6 · 感兴趣与项目研究 | 待开发 |
| M7 · 本地交付与备份恢复 | 待开发 |

