import { useEffect, useState } from "react";
import {
  AlertTriangle, Archive, Check, Clock3, Database, Download, FileCheck2,
  Folder, HardDrive, KeyRound, LoaderCircle, RefreshCw, RotateCcw,
  Save, ShieldCheck, Trash2,
} from "lucide-react";
import { api, type BackupItem, type BackupSettings, type SystemStatusResponse } from "../services/api";

function formatBytes(value: number): string {
  if (value < 1024) return value + " B";
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
  if (value < 1024 * 1024 * 1024) return (value / (1024 * 1024)).toFixed(1) + " MB";
  return (value / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function backupKindLabel(kind: BackupItem["kind"]): string {
  if (kind === "auto") return "自动备份";
  if (kind === "pre-restore") return "恢复前安全备份";
  return "手动备份";
}

export default function SystemSettingsPage() {
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [settings, setSettings] = useState<BackupSettings>({
    auto_backup_enabled: true,
    interval_hours: 24,
    retention_count: 14,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyFilename, setBusyFilename] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function loadData(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const response = await api.systemStatus();
      setStatus(response);
      setSettings(response.backup_settings);
      setBackups(response.backups);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取系统状态失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { void loadData(); }, []);

  async function createManualBackup() {
    setCreating(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.createBackup();
      setSuccess("备份已创建：" + response.item.filename);
      await loadData(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建备份失败");
    } finally {
      setCreating(false);
    }
  }

  async function verifyBackup(filename: string) {
    setBusyFilename(filename);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.verifyBackup(filename);
      const result = response.result;
      setBackups((current) => current.map((item) => item.filename === filename ? {
        ...item,
        valid: result.valid,
        schema_version: result.schema_version,
        repositories: result.repositories,
      } : item));
      setSuccess("备份校验通过 · SQLite integrity_check = " + result.integrity_check);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "备份校验失败");
    } finally {
      setBusyFilename(null);
    }
  }

  async function deleteBackup(item: BackupItem) {
    if (!window.confirm("确定删除备份文件？\n" + item.filename + "\n此操作不可撤销。")) return;
    setBusyFilename(item.filename);
    setError(null);
    setSuccess(null);
    try {
      await api.deleteBackup(item.filename);
      setSuccess("已删除备份：" + item.filename);
      await loadData(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除备份失败");
    } finally {
      setBusyFilename(null);
    }
  }

  async function queueRestore(item: BackupItem) {
    const accepted = window.confirm(
      "确认安排恢复到这个备份？\n\n" +
      item.filename +
      "\n\n系统会先创建一份“恢复前安全备份”，然后在你关闭并重新启动 GitScout 时执行恢复。当前运行中的数据不会立即改变。",
    );
    if (!accepted) return;
    setBusyFilename(item.filename);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.queueBackupRestore(item.filename);
      setSuccess(
        "恢复已安排。恢复前安全备份：" + response.restore.safety_backup +
        "。请先关闭 GitScout，再重新运行 start_gitscout.bat。",
      );
      await loadData(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "安排恢复失败");
    } finally {
      setBusyFilename(null);
    }
  }

  async function saveSettings() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.updateBackupSettings(settings);
      setSettings(response.settings);
      setSuccess("自动备份设置已保存。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存备份设置失败");
    } finally {
      setSaving(false);
    }
  }

  const pendingRestore = status?.info.pending_restore;
  const databaseStatus = status?.info.database_exists ? "正常" : "未初始化";

  return (
    <div className="page-stack system-settings-page">
      <section className="surface-card system-settings-intro">
        <div className="system-settings-icon"><ShieldCheck size={22} /></div>
        <div>
          <span className="eyebrow">LOCAL RUNTIME · DATA SAFETY</span>
          <h2>让本地工作台稳定运行，数据可备份、可验证、可恢复。</h2>
          <p>GitScout 默认仅在本机运行。数据库、备份、运行日志与源码分开保存；恢复操作会延迟到下次启动执行，避免覆盖正在使用的数据库。</p>
        </div>
        <button className="button button-quiet" onClick={() => void loadData(true)} disabled={loading || refreshing}>
          {refreshing ? <LoaderCircle size={13} className="spin" /> : <RefreshCw size={13} />}刷新状态
        </button>
      </section>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success"><Check size={14} />{success}</div>}

      {pendingRestore && (
        <section className="system-pending-restore">
          <AlertTriangle size={18} />
          <div>
            <strong>有一项数据库恢复等待执行</strong>
            <p>目标备份：{pendingRestore.filename || "恢复任务文件异常"}</p>
            <p>恢复前安全备份：{pendingRestore.safety_backup || "未知"}</p>
            <p>请停止 GitScout 服务，然后重新运行 <code>start_gitscout.bat</code>。恢复将在启动阶段完成。</p>
          </div>
        </section>
      )}

      <section className="system-overview-grid">
        <article className="surface-card system-overview-card">
          <span><HardDrive size={15} />应用版本</span>
          <strong>{loading ? "读取中…" : "v" + (status?.app_version ?? "—")}</strong>
          <small>FastAPI · React · SQLite</small>
        </article>
        <article className="surface-card system-overview-card">
          <span><Database size={15} />数据库状态</span>
          <strong>{loading ? "读取中…" : databaseStatus}</strong>
          <small>Schema {status?.schema_version ?? "—"} · {formatBytes(status?.info.database_size_bytes ?? 0)}</small>
        </article>
        <article className="surface-card system-overview-card">
          <span><Archive size={15} />备份数量</span>
          <strong>{loading ? "—" : backups.length}</strong>
          <small>自动、手动与恢复前安全备份</small>
        </article>
        <article className="surface-card system-overview-card">
          <span><KeyRound size={15} />GitHub Token</span>
          <strong>{loading ? "读取中…" : status?.info.github_token_configured ? "已配置" : "未配置"}</strong>
          <small>仅后端读取，不向浏览器返回 Token</small>
        </article>
      </section>

      <section className="surface-card system-path-card">
        <div className="system-section-heading">
          <div><h3><Folder size={15} />本地存储位置</h3><p>数据目录由根目录 .env 中的 GITSCOUT_DATA_DIR 控制，修改后需重启服务。</p></div>
        </div>
        <div className="system-path-list">
          <div><span>数据目录</span><code>{status?.info.data_dir ?? "—"}</code></div>
          <div><span>SQLite 数据库</span><code>{status?.info.database_path ?? "—"}</code></div>
          <div><span>备份目录</span><code>{status?.info.backup_dir ?? "—"}</code></div>
          <div><span>运行日志</span><code>.runtime/logs/</code></div>
        </div>
        <div className="system-security-note"><ShieldCheck size={13} />数据库、备份、Token、虚拟环境和日志均已排除在 Git 版本控制之外。</div>
      </section>

      <section className="surface-card system-backup-settings-card">
        <div className="system-section-heading">
          <div><h3><Clock3 size={15} />自动备份策略</h3><p>服务运行期间按设定间隔检查；服务启动时也会补做逾期备份。</p></div>
          <label className="switch-control">
            <input type="checkbox" checked={settings.auto_backup_enabled} onChange={(event) => setSettings((current) => ({ ...current, auto_backup_enabled: event.target.checked }))} />
            <span />
            <small>{settings.auto_backup_enabled ? "已启用" : "已关闭"}</small>
          </label>
        </div>
        <div className="system-backup-settings-fields">
          <label><span>自动备份间隔</span><select value={settings.interval_hours} onChange={(event) => setSettings((current) => ({ ...current, interval_hours: Number(event.target.value) }))}>
            <option value={6}>每 6 小时</option><option value={12}>每 12 小时</option><option value={24}>每天</option><option value={48}>每 2 天</option><option value={72}>每 3 天</option><option value={168}>每周</option>
          </select></label>
          <label><span>自动备份保留数量</span><select value={settings.retention_count} onChange={(event) => setSettings((current) => ({ ...current, retention_count: Number(event.target.value) }))}>
            <option value={3}>3 份</option><option value={7}>7 份</option><option value={14}>14 份</option><option value={30}>30 份</option><option value={60}>60 份</option><option value={90}>90 份</option>
          </select></label>
          <div className="system-backup-settings-action"><button className="button button-primary" onClick={() => void saveSettings()} disabled={saving || loading}><Save size={13} />{saving ? "保存中…" : "保存策略"}</button></div>
        </div>
        <p className="system-settings-footnote">保留数量仅作用于自动备份；手动备份与恢复前安全备份不会被自动清理。</p>
      </section>

      <section className="surface-card system-backups-card">
        <div className="system-section-heading system-backups-heading">
          <div><h3><Archive size={15} />数据库备份</h3><p>使用 SQLite 在线备份接口生成一致性快照，兼容 WAL，不需要先关闭服务。</p></div>
          <button className="button button-primary" onClick={() => void createManualBackup()} disabled={creating || loading}>
            {creating ? <LoaderCircle size={13} className="spin" /> : <Archive size={13} />}{creating ? "备份中…" : "立即备份"}
          </button>
        </div>
        {backups.length === 0 ? (
          <div className="system-backups-empty"><Archive size={24} /><strong>暂时没有备份</strong><span>可以立即创建一份手动备份。</span></div>
        ) : (
          <div className="system-backup-list">
            {backups.map((item) => (
              <article className="system-backup-row" key={item.filename}>
                <div className="system-backup-file-icon"><Database size={16} /></div>
                <div className="system-backup-copy">
                  <strong>{item.filename}</strong>
                  <span>{backupKindLabel(item.kind)} · {formatDate(item.created_at)} · {formatBytes(item.size_bytes)}</span>
                  {item.valid === true && <small className="system-backup-verified"><Check size={11} />校验通过 · Schema {item.schema_version ?? "—"} · {item.repositories ?? 0} 个仓库</small>}
                  {item.valid === false && <small className="system-backup-invalid">校验失败</small>}
                </div>
                <div className="system-backup-actions">
                  <button className="button button-quiet" disabled={busyFilename === item.filename} onClick={() => void verifyBackup(item.filename)}>
                    {busyFilename === item.filename ? <LoaderCircle size={12} className="spin" /> : <FileCheck2 size={12} />}校验
                  </button>
                  <a className="button button-quiet" href={"/api/v1/system/backups/" + encodeURIComponent(item.filename) + "/download"}><Download size={12} />下载</a>
                  <button className="button button-quiet" disabled={busyFilename === item.filename || Boolean(pendingRestore)} onClick={() => void queueRestore(item)}><RotateCcw size={12} />恢复</button>
                  <button className="button button-danger-quiet" disabled={busyFilename === item.filename || pendingRestore?.filename === item.filename} onClick={() => void deleteBackup(item)} aria-label="删除备份"><Trash2 size={12} /></button>
                </div>
              </article>
            ))}
          </div>
        )}
        <div className="system-restore-note"><AlertTriangle size={13} />恢复不会立即覆盖正在运行的数据库。安排恢复后，请关闭 GitScout，再重新启动；启动时会先校验备份并执行恢复。</div>
      </section>

      <section className="surface-card system-token-card">
        <div className="system-section-heading">
          <div><h3><KeyRound size={15} />GitHub 访问配置</h3><p>Token 只保存在本机后端配置中，不会展示明文，也不会进入前端请求。</p></div>
          <span className={status?.info.github_token_configured ? "system-token-state configured" : "system-token-state"}>{status?.info.github_token_configured ? "已检测到 Token" : "未配置 Token"}</span>
        </div>
        <div className="system-token-instructions">
          <span>编辑项目根目录的 <code>.env</code> 文件：</span>
          <code>GITHUB_TOKEN=你的 GitHub Token</code>
          <small>保存后停止并重新启动 GitScout。公开数据采集可在无 Token 状态下运行，但 API 请求额度可能较低。</small>
        </div>
      </section>
    </div>
  );
}
