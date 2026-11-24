# GitScout Windows 本地运行与数据安全手册

> 适用版本：GitScout 0.7.0 · Windows 10 / 11 · Python 3.11 · Node.js 20+

## 1. 首次安装

### 环境要求

- Windows 10 / Windows 11 64 位。
- Python 3.11，并启用 Python Launcher（py）。
- Node.js 20 或更高版本（包含 npm）。
- 首次安装需要网络访问 Python 包索引与 npm registry。

### 一键初始化

1. 将 GitScout 仓库完整下载或克隆到本地固定目录。
2. 双击仓库根目录的 setup_gitscout.bat。
3. 脚本检查 Python / Node 版本，创建 backend/.venv，安装后端依赖，安装前端依赖并构建 React。
4. 首次初始化会从 .env.example 创建 .env。
5. 初始化完成后，双击 start_gitscout.bat。

启动脚本发现虚拟环境、依赖、前端构建或 .env 缺失时，会再次调用初始化流程。正常启动不会每次重新安装依赖。

## 2. 日常启动与停止

### 启动

双击 start_gitscout.bat。启动器会：

1. 检查 127.0.0.1:8765 是否已被占用。
2. 如果已经是健康的 GitScout 服务，则直接打开浏览器。
3. 在 .runtime/logs/ 准备日志并轮转过大的日志文件。
4. 以隐藏后台进程启动单 Worker FastAPI。
5. 轮询 /api/v1/health，最多等待 60 秒。
6. 健康检查通过后打开 http://127.0.0.1:8765。

### 停止

双击 stop_gitscout.bat。脚本只会停止 PID 文件记录且命令行确认为 GitScout API 的进程；不会按端口号强制结束不相关程序。

不要直接删除 data/、.runtime/ 或 backend/.venv/ 来停止服务。

### 开发模式

开发模式仍使用两个终端：

后端：

~~~powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
~~~

前端：

~~~powershell
cd frontend
npm install
npm run dev
~~~

浏览器访问 http://127.0.0.1:5173。开发模式下 Vite 将 /api 转发到 127.0.0.1:8000。

## 3. 备份策略

### 默认策略

- 自动备份：默认启用。
- 自动备份间隔：24 小时。
- 自动备份保留：最近 14 份。
- 自动备份仅在 GitScout 服务运行时执行；启动时会检查是否逾期并补做。
- 自动备份保留数量只清理自动备份；手动备份和恢复前安全备份不会被自动清理。

### 创建备份

可选择以下任一方式：

- 打开 GitScout → 系统设置 → 数据库备份 → 立即备份。
- 双击 backup_gitscout.bat。
- 使用 POST /api/v1/system/backups。

备份保存在当前数据目录的 backups/ 子目录中。文件名以 gitscout-manual- 或 gitscout-auto- 开头，扩展名为 .db。

备份通过 Python sqlite3 的在线备份接口创建，会将 WAL 中已提交的数据纳入一致性快照。不要在文件管理器中直接复制运行中的 gitscout.db 作为唯一备份方案。

### 校验备份

在系统设置页面点击备份记录的“校验”。服务执行 SQLite PRAGMA integrity_check，并检查 GitScout schema 标记，显示 Schema 版本和仓库数量。

可通过 POST /api/v1/system/backups/{filename}/verify 执行校验。

建议在重要升级、迁移数据目录或清理旧备份前先校验。

## 4. 数据恢复

恢复是破坏性操作，GitScout 采用延迟恢复：

1. 在系统设置中选择目标备份，点击“恢复”并确认。
2. GitScout 先验证备份完整性。
3. 系统自动创建一份 gitscout-pre-restore-*.db 恢复前安全备份。
4. 系统写入 data/restore_pending.json，安排下次启动恢复。
5. 关闭 GitScout：双击 stop_gitscout.bat。
6. 重新双击 start_gitscout.bat。
7. 后端启动阶段在初始化数据库和启动调度器之前应用备份，再执行必要的数据库迁移。
8. 进入系统设置确认数据库状态与备份记录。

恢复请求不会立即覆盖正在运行的数据库。恢复前安全备份可用于回退；不要在恢复流程中删除 data/backups/ 或 data/restore_pending.json。

命令行也可以使用：

~~~powershell
restore_gitscout.bat gitscout-manual-20261124T090000000000Z.db
~~~

命令行会要求输入 RESTORE 二次确认。备份文件名必须是当前数据目录 backups/ 中的文件名。

如果恢复期间启动失败，先查看 .runtime/logs/gitscout-error.log 和 .runtime/logs/gitscout.log。恢复替换数据库文件前会先校验临时恢复副本；校验失败不会替换当前数据库。保留原备份与恢复前安全备份，先排查问题，不要手动覆盖数据库文件。

## 5. 数据目录与配置

默认目录：

~~~text
GitScout/
├── backend/
│   └── .venv/                 # Python 虚拟环境，可重建
├── frontend/
│   └── dist/                  # React 构建产物，可重建
├── data/
│   ├── gitscout.db            # SQLite 主数据库
│   ├── gitscout.db-wal        # SQLite WAL 运行文件
│   ├── gitscout.db-shm        # SQLite SHM 运行文件
│   ├── system_settings.json   # 本地自动备份策略
│   ├── restore_pending.json   # 待执行恢复任务（存在时）
│   └── backups/               # 数据库备份
├── .runtime/
│   └── logs/                  # 运行日志与历史日志
├── scripts/                   # PowerShell 运维脚本
├── .env                       # 本地配置与 Token
├── setup_gitscout.bat
├── start_gitscout.bat
├── stop_gitscout.bat
└── README.md
~~~

### 自定义数据目录

编辑仓库根目录 .env：

~~~dotenv
GITSCOUT_DATA_DIR=E:/GitScoutData
~~~

相对路径按仓库根目录解析，绝对路径可放在其他磁盘。修改后必须停止并重新启动 GitScout。切换数据目录不会自动迁移旧数据库；请先手动备份，再将数据库和备份复制到新目录，并核对数据后再启动。

### GitHub Token

编辑根目录 .env：

~~~dotenv
GITHUB_TOKEN=你的_GitHub_Token
~~~

保存后停止并重新启动。系统设置页面只显示 Token 是否配置，不会读取或返回 Token 明文。不要将真实 Token 写入代码、截图、Issue 或 Git 提交。

## 6. 日志与诊断

- data/gitscout.db：业务数据。
- .runtime/logs/gitscout.log：标准输出日志。
- .runtime/logs/gitscout-error.log：错误输出日志。
- 日志文件超过约 20 MB 时，启动器会按时间戳轮转；最多保留最近 10 组轮转文件。
- 健康检查：http://127.0.0.1:8765/api/v1/health。
- API 文档：http://127.0.0.1:8765/docs。

常见问题：

| 现象 | 处理方式 |
|---|---|
| 找不到 Python | 安装 Python 3.11，启用 Python Launcher，重新运行 setup_gitscout.bat |
| 找不到 Node / npm | 安装 Node.js 20+，重新运行初始化脚本 |
| 前端页面未构建 | 运行 setup_gitscout.bat，检查 npm 安装和构建输出 |
| 8765 端口占用 | 确认是否已有 GitScout 实例；若是其他程序，请修改端口配置后同步调整启动器 |
| 服务启动超时 | 查看 .runtime/logs/gitscout-error.log |
| GitHub API 限流 | 检查 Token 是否配置、请求间隔和 GitHub 限流状态 |
| 数据库损坏提示 | 停止服务，先复制当前 data/，再使用最近一次通过校验的备份恢复 |

## 7. 安全边界

- 正式启动器固定绑定 127.0.0.1，不监听 0.0.0.0。
- 本地 API 当前没有用户登录认证，不应通过公网反向代理、端口映射或隧道公开。
- GitHub Token 只由后端读取；系统状态接口只返回是否配置。
- .env、SQLite 数据库、备份、恢复标记、运行日志、虚拟环境和前端构建产物均不应提交 Git。
- SQLite 备份文件未加密；若复制到云盘或移动介质，请使用受保护的存储位置。

## 8. 验收清单

- [ ] 首次运行 setup_gitscout.bat 可以创建环境、安装依赖并构建前端。
- [ ] start_gitscout.bat 健康检查通过后打开本地 Web 工作台。
- [ ] 再次启动不会重复创建服务进程。
- [ ] stop_gitscout.bat 能安全停止 GitScout。
- [ ] 系统设置显示数据目录、数据库大小、Schema 版本和 Token 配置状态。
- [ ] 手动备份可创建、下载、校验和删除。
- [ ] 自动备份按间隔执行，并按保留数量清理旧自动备份。
- [ ] 恢复前自动生成安全备份。
- [ ] 延迟恢复在下次启动时执行，原有数据按目标备份回滚。
- [ ] 服务重启后 Trending、Stars、推荐、感兴趣和研究数据仍然存在。
