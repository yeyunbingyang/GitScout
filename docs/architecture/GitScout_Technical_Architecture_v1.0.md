# GitScout 技术架构设计说明书

- 产品：GitScout · 开源项目发现与研究平台
- 文档版本：v1.0
- 状态：首期技术基线已确认
- 运行模式：Windows 本地 Web 工作台

## 1. 架构决策

| 层级 | 技术 | 职责 |
|---|---|---|
| 前端 | React + TypeScript + Vite | 页面、交互、图表与用户操作 |
| 后端 | Python + FastAPI | REST API、业务规则、采集和持久化 |
| 数据库 | SQLite | 唯一业务数据库，默认位于 `data/gitscout.db` |
| 数据访问 | Python 标准库 `sqlite3` | 连接、事务、SQL 迁移 |
| 请求与解析 | HTTPX + BeautifulSoup | GitHub REST API 与 Trending 页面 |
| 任务调度 | Python `asyncio` | 单进程内定时任务和手动任务 |
| ASGI 服务 | Uvicorn | 本地 API 和生产静态资源服务 |

不引入 PostgreSQL、MySQL、MongoDB、Redis、Celery、RabbitMQ、Docker 或 Kubernetes。首期不引入 ORM；数据库版本通过受 Git 管理的 SQL 迁移文件维护。

## 2. 本地运行形态

### 开发模式

- React / Vite：`http://127.0.0.1:5173`
- FastAPI / Uvicorn：`http://127.0.0.1:8000`
- Vite 将 `/api` 请求代理到 FastAPI。
- CORS 只允许配置的本地开发 Origin。

### 本地使用模式

前端执行 `npm run build` 生成 `frontend/dist`，FastAPI 提供静态文件和 API。用户通过 `http://127.0.0.1:8765` 使用工作台。

默认只绑定 `127.0.0.1`，不开放公网或局域网访问。正式运行使用单个 Uvicorn Worker，避免进程内调度器重复启动。

## 3. 分层职责

1. **React 前端**：负责趋势总览、周期榜单、Stars 总榜、推荐、比较、兴趣、研究、采集记录和设置页面；不直接请求 GitHub、不连接 SQLite、不持有 Token。
2. **FastAPI API 层**：负责输入校验、响应格式、错误处理和 API 版本管理。
3. **Service 层**：承载项目、榜单、推荐、研究、采集等业务规则。
4. **Collector 层**：隔离 GitHub API 客户端与 Trending HTML 解析器。
5. **Repository / Database 层**：集中处理 SQL、连接、事务和迁移。
6. **asyncio 调度层**：触发采集与计算任务；任务状态持久化到 SQLite。

## 4. 数据库设计

SQLite 是唯一业务数据库，首期核心表如下：

| 领域 | 表 |
|---|---|
| 项目主档 | `repositories`、`repository_topics`、`repository_stats` |
| Trending | `trending_snapshots`、`trending_snapshot_items` |
| Stars | `stars_scans`、`stars_scan_shards`、`stars_scan_items` |
| 推荐 | `recommendation_profiles`、`recommendation_runs`、`recommendation_scores` |
| 兴趣 | `interested_projects` |
| 研究 | `research_projects`、`research_notes`、`research_tags`、`research_project_tags` |
| 任务 | `collection_schedules`、`collection_jobs`、`collection_job_logs` |
| 系统 | `app_settings`、`schema_migrations` |

关键规则：

- 同一 GitHub 仓库以 `github_repo_id` 为首选唯一标识，`full_name` 作为唯一备用约束。
- 日 / 周 / 月每次采集都新增快照，不覆盖历史排名。
- Stars 总榜独立于 Trending 项目集合。
- 兴趣标记与研究关系相互独立。
- 推荐计算保留算法版本、实际权重、统计窗口、数据截止时间和分项得分。
- 时间统一存 ISO-8601 UTC 字符串，前端按本地时区显示。

### SQLite 运行参数

- `PRAGMA journal_mode=WAL`
- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=5000`
- `PRAGMA synchronous=NORMAL`

所有网络请求期间不持有数据库写事务；采集写入采用短事务和单写入锁。每个请求 / 任务使用独立连接，结束后关闭。

## 5. 采集方案

### Trending 采集实现

当前 M2 已实现独立 Trending collector service：

- HTTPX 异步客户端获取 GitHub Trending 页面，默认请求地址为 `https://github.com/trending?since={daily|weekly|monthly}`。
- 解析器以 `article.Box-row` 和仓库链接为主锚点，提取仓库名、简介、语言、Stars、周期增量、Forks 与可见 Topics。
- 对短暂网络错误、429 和 5xx 响应进行有限次数退避重试。
- 网络请求在 SQLite 事务之外执行；仓库 upsert、Topics 更新和快照明细在一个短事务内提交。
- 每次运行创建独立快照；失败运行创建 status=failed 的审计记录，但历史榜单接口只返回 success / partial_success。
- HTML 解析结果包含重复和跳过计数；存在无法识别卡片时以 partial_success 标记，避免伪装成完整采集。

### Stars 总榜采集实现

- 使用 GitHub REST `GET /search/repositories`，`sort=stars&order=desc`，仅采集公开仓库。
- 默认 Top 5,000、最低 100 Stars；可配置 Top 1,000 / 3,000 / 5,000 / 10,000、Stars 下限及是否包含 Fork。
- 每页最多 100 条；每个 Search 查询最多可读取 1,000 条。超出时按 Stars 数值范围递归拆分，优先处理高 Stars 区间。
- 同一 Stars 值的结果桶若仍超过 1,000 条，则按 `created` 日期区间继续拆分；无法继续拆分的叶子分片标记失败。
- 使用 GitHub Repository ID 去重；更新仓库主档、Topics 和 `repository_stats`；每次扫描写入独立 `stars_scans`、`stars_scan_shards` 和 `stars_scan_items`。
- 记录 `incomplete_results`、每个分片的查询、匹配数量、获取数量、失败原因及覆盖说明。部分分片失败或 API 返回不完整结果时，扫描标记 `partial_success`。
- Token 从本地 `.env` 的 `GITHUB_TOKEN` 读取，只在后端请求头中使用；日志不记录 Token。
- Search API 请求默认节流：有 Token 时约 2.1 秒一次；无 Token 时约 6.1 秒一次。尊重 `Retry-After` 与 `X-RateLimit-Reset`，并对短暂网络错误和服务端错误有限重试。
- Stars 扫描是有明确 Top-N 和最低 Stars 阈值的排行榜，不宣称覆盖 GitHub 全站所有仓库。

### M4 趋势分析实现

- `GET /dashboard/analytics` 只读取 SQLite：返回所选周期最新 / 上一批快照、最近 12 次快照平均 Stars 走势、当前快照语言与 Topic 分布、三个周期各自最新快照的 Top 100 交叉矩阵，以及最新 Stars 扫描摘要。
- 跨周期热门项目以各周期最新快照 Top 100 为计算边界；不把未进入采集范围解释为零热度。
- `GET /trending/compare` 要求两个不同且同周期的有效快照，按 repository_id 做并集比较，区分 new / dropped / up / down / unchanged；支持关键词、语言、变化类型筛选和分页。
- `GET /repositories/{id}` 聚合仓库主档、Topics、个人兴趣 / 研究状态、Trending 上榜历史、各周期当前连续上榜次数、Stars 扫描历史和 repository_stats 历史观测；所有数据都来自本地数据库。
- 对比 CSV 由前端按当前筛选条件分页拉取完整结果后生成，不增加后端导出服务。
- M4 复用现有 `trending_snapshots`、`trending_snapshot_items`、`stars_scans`、`stars_scan_items` 和 `repository_stats`，不需要新增迁移。


### M5 推荐引擎实现

- 候选池由最近一次成功 Stars 扫描的项目，以及最近成功日榜 30 次、周榜 12 次、月榜 12 次快照中的项目并集构成；按 repositories.id / GitHub repository_id 去重。
- Stars 子分在当前候选池按 stars_count 降序排名，使用 PRD 百分位公式 `100 × (N - rank + 1) / N`；相同 Stars 数量以规范化 full_name 和 repository 主键稳定打破并列。
- 日 / 周 / 月子分分别按最近 30 / 12 / 12 次成功快照中的上榜次数除以有效快照数计算。仅 `status='success'` 的快照进入分母。
- 日榜 / 周榜 / 月榜最低有效样本数分别为 10 / 4 / 3；未达门槛时子分保存为 NULL（N/A），总分按可用指标权重重新归一化。最终总分保存一位小数，排序使用未四舍五入原始值。
- 默认权重 30 / 15 / 30 / 25；另提供趋势发现优先 20 / 25 / 35 / 20、长期价值优先 40 / 10 / 25 / 25。每批次固化 weights_json，不因后续预设变化而改变旧结果。
- 并列排序依次按未舍入综合分、Stars 候选池排名、最近一次上榜时间和仓库 full_name；理由码由加权贡献最高的可用指标生成。
- 推荐等级阈值：85 优先研究、75 强烈推荐、65 值得关注、50 观察，其余低优先级。新兴潜力默认日榜分数不低于 60 且 Stars 分数不高于 70；长期稳定默认周榜和月榜分数均不低于 60。
- Stars 数据完整性单独展示：最近一次完整 Stars 扫描超过 7 天标记为过期；最近扫描为部分成功或 incomplete_results=true 时标记不完整。过期 / 不完整提示不会被隐藏，也不把旧扫描伪装为实时数据。
- `recommendation_runs` 保存算法版本、权重、窗口配置、候选规模、数据截止时间和执行状态；`recommendation_scores` 保存四项子分、总分、排名、理由码和样本覆盖。新计算创建新批次，不覆盖旧记录。
- `GET /recommendations/profiles`、`POST /recommendations/runs`、`GET /recommendations/runs/latest`、`GET /recommendations/runs/{id}` 提供真实 API；推荐页接入预设切换、批次历史、类别、语言、主要贡献维度筛选、关键词搜索和 CSV 导出。
- M5 新增迁移仅为三套默认预设和查询索引；复用初始 schema 已存在的 recommendation_profiles / recommendation_runs / recommendation_scores 表。

### M6 兴趣与研究工作区实现

- 兴趣与研究使用独立业务关系：`interested_projects.repository_id` 唯一标记兴趣；`research_projects.repository_id` 唯一标记研究关系。二者不互相级联。
- 兴趣标签沿用 `tags_json` 保存；研究标签通过 `research_tags` 与 `research_project_tags` 多对多关联；研究笔记存放在 `research_notes`。
- `/interested` API 提供列表 / 详情 / 幂等标记 / PATCH / DELETE；列表支持关键词、语言、标签、研究成员状态、排序和分页。
- `/research` API 提供列表 / 创建 / 详情 / PATCH / DELETE；标签使用 PUT 整体替换；笔记支持 POST / PATCH / DELETE。
- 状态转换自动维护 `started_at` / `completed_at`；从已完成重新打开时清除完成时间，保留首次开始时间。
- M5 推荐、Trending、Stars 和仓库详情 API 均提供兴趣 / 研究状态，前端使用统一的快捷操作组件。
- 感兴趣与研究页分别提供搜索、筛选、编辑、批量数据导出；研究导出会按项目拉取详情并包含笔记内容。
- 迁移 0005 仅增加查询索引；M6 复用 0001 已有数据表，不重建或搬迁用户数据。

### 本地调度实现

- 使用 FastAPI lifespan 启动一个 asyncio scheduler loop，不引入 Celery / Redis / APScheduler。
- `collection_schedules` 中日 / 周 / 月分别保存 enabled、timezone、settings_json 和 next_run_at。
- 日计划按每日时间触发；周计划按 weekday + 时间触发；月计划按 1—28 日 + 时间触发。
- Trending 日 / 周 / 月与 Stars 每日计划默认均关闭；必须由用户在采集设置页面显式启用。
- next_run_at 使用 UTC ISO-8601 持久化，调度时间按用户选定的 IANA 时区计算。
- 本地服务停止时取消调度任务；重启后遗留 queued / running 任务标记为 interrupted。
- 生产本地模式必须使用单 Uvicorn Worker，避免进程内调度重复执行。



### Trending 日 / 周 / 月

数据来源：

- `https://github.com/trending?since=daily`
- `https://github.com/trending?since=weekly`
- `https://github.com/trending?since=monthly`

使用 HTTPX 获取页面，BeautifulSoup 解析仓库名、简介、语言、Stars、周期增量、Forks 和排名。解析器独立封装，并使用本地 HTML Fixture 做回归测试。每次采集创建快照；失败不得伪装为成功。

### Stars 总榜

使用 GitHub REST Search Repositories API，按 `sort=stars&order=desc` 查询。Search API 单次查询最多返回 1,000 条结果，且有独立速率限制。因此必须显示结果覆盖范围、`incomplete_results` 和分片完成状态。超过单次结果上限时按 Stars 区间等条件分片，合并后按 GitHub repository ID 去重。部分分片失败时标记为部分成功，不得称为全站完整榜单。

Token 仅由后端读取，不进入前端、URL、Git 仓库或日志。限流时遵守 `Retry-After` 与 `X-RateLimit-Reset`，采用退避重试。

## 6. 任务调度与恢复

不使用 Celery / Redis。FastAPI lifespan 启动一个 asyncio 调度循环，读取 SQLite 中的调度配置。手动触发和定时触发共用任务入口。

任务状态包括 queued、running、success、partial_success、failed、cancelled、interrupted。通过幂等键防止重复执行；服务启动时识别异常退出留下的 running 任务并标记中断或按规则恢复。生产环境必须单 Worker。

## 7. API 约定

统一前缀 `/api/v1`，JSON 响应，列表统一分页。

| API | 用途 |
|---|---|
| `GET /health` | 服务与数据库健康状态 |
| `GET /dashboard/summary` | 首页基础概览统计 |
| `GET /dashboard/analytics?period_type={daily|weekly|monthly}` | 趋势总览聚合分析 |
| `GET /repositories` | 项目主档列表 |
| `GET /repositories/{id}` | 项目详情、历史排名与 Stars 观测 |
| `GET /trending` | 周期榜单 |
| `GET /trending/snapshots` | 历史快照列表 |
| `GET /trending/snapshots/{id}` | 历史快照详情 |
| `POST /trending/collect` | 手动触发日 / 周 / 月采集 |
| `GET /collections/jobs` | 采集任务记录 |
| `GET /collections/jobs/{id}` | 任务详情与执行日志 |
| `POST /collections/jobs/{id}/retry` | 重试失败任务 |
| `GET /collections/schedules` | 查询 Trending 与 Stars 调度设置 |
| `PUT /collections/schedules/{period}` | 更新 Trending 某个周期的调度计划 |
| `PUT /collections/schedules/stars` | 更新 Stars 每日调度计划 |
| `GET /stars/leaderboard` | 查询 Stars 排名快照 |
| `GET /trending/compare` | 比较同周期的两次历史快照 |
| `GET /stars/scans` | 查询历史 Stars 扫描 |
| `GET /stars/scans/{id}` | 查询扫描与分片详情 |
| `POST /stars/collect` | 手动触发 Stars 扫描 |
| `POST /stars/scans/{id}/retry` | 重试失败或部分成功扫描 |
| `GET /recommendations/profiles` | 查询推荐权重预设 |
| `GET /recommendations/runs` | 查询历史推荐计算批次 |
| `POST /recommendations/runs` | 按指定权重方案创建新推荐批次 |
| `GET /recommendations/runs/latest` | 查询最新成功推荐结果 |
| `GET /recommendations/runs/{id}` | 查询指定批次结果，支持类别、关键词和分页筛选 |
| `GET /research` | 研究工作区 |

耗时操作返回 job_id，前端轮询任务状态；首期不要求 WebSocket。

## 8. 目录与数据边界

```text
GitScout/
├── frontend/             # React 应用
├── backend/              # FastAPI、SQL 迁移、测试
├── data/                 # SQLite、备份、导出
├── docs/                 # 需求、架构、开发文档
├── prototype/            # 已确认 HTML 原型
├── .runtime/logs/         # 可重建运行日志
├── start_gitscout.bat
└── README.md
```

数据库、Token、日志、备份、虚拟环境和 node_modules 不提交 Git。

## 9. 当前实现边界

M0 / M1 建立工程骨架和 SQLite 数据底座；M2 已实现 Trending 采集与本地调度；M3 已实现 Stars Search API 采集、分片、去重、历史扫描、覆盖审计、重试及 Stars 每日调度；M4 已实现趋势总览聚合、同周期快照比较和仓库详情历史；M5 已实现推荐评分引擎、权重预设、批次留痕和推荐工作台。M2 / M3 / M4 CI 已通过；M5 GitHub Actions CI 已通过；M6 兴趣与研究工作区已实现，CI 验收中。Windows 本机真实数据验收仍待确认。M6 感兴趣与研究 CRUD、M7 本地备份恢复按后续阶段完成。

## 10. 升级条件

当出现多人协作、远程多实例、持续高并发写入或多采集 Worker 需求时，重新评估数据库与任务系统。本期不为尚未出现的负载提前增加基础设施。

---

文档版本：v1.0
