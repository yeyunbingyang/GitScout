import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Clock3, FileText, RefreshCw, RotateCcw, X } from "lucide-react";
import { api, type CollectionJob, type CollectionJobDetail } from "../services/api";

function date(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function label(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中", running: "运行中", success: "成功",
    partial_success: "部分成功", failed: "失败", cancelled: "已取消",
    interrupted: "中断",
  };
  return labels[status] ?? status;
}

function periodName(jobType: string): string {
  if (jobType === "stars_scan") return "Stars 总榜";
  const value = jobType.replace("trending_", "");
  return value === "daily" ? "日榜" : value === "weekly" ? "周榜" : value === "monthly" ? "月榜" : jobType;
}

export default function CollectionJobsPage() {
  const [items, setItems] = useState<CollectionJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<CollectionJobDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.collectionJobs();
      setItems(response.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取采集记录失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function showDetails(jobId: string) {
    if (selectedJob?.id === jobId) {
      setSelectedJob(null);
      return;
    }
    setDetailLoading(true);
    try {
      setSelectedJob(await api.collectionJob(jobId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取任务详情失败");
    } finally {
      setDetailLoading(false);
    }
  }

  async function retry(job: CollectionJob) {
    setRetrying(job.id);
    setError(null);
    try {
      await api.retryCollectionJob(job.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    } finally {
      setRetrying(null);
    }
  }

  const successful = items.filter((item) => item.status === "success").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const active = items.filter((item) => item.status === "running" || item.status === "queued").length;

  return (
    <div className="page-stack">
      <div className="section-heading">
        <div><h3>Trending 采集任务</h3><p>统一记录 Trending 与 Stars 总榜采集、数据入库、失败原因和重试关系。</p></div>
        <button className="button button-quiet" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={14} className={loading ? "spin" : ""} />刷新记录
        </button>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="job-summary-grid">
        <div className="job-summary-card"><span>任务总数</span><strong>{items.length}</strong><small>当前查询批次</small></div>
        <div className="job-summary-card"><span>成功</span><strong>{successful}</strong><small><CheckCircle2 size={12} /> 已完成任务</small></div>
        <div className="job-summary-card"><span>运行中</span><strong>{active}</strong><small><Clock3 size={12} /> 排队或执行</small></div>
        <div className="job-summary-card"><span>失败</span><strong>{failed}</strong><small><AlertCircle size={12} /> 可查看原因并重试</small></div>
      </div>
      <section className="surface-card jobs-table-card">
        {loading ? <div className="empty-state">正在读取采集记录…</div> : items.length === 0 ? (
          <div className="empty-state"><span className="empty-icon"><Clock3 size={24} /></span><strong>暂无采集任务</strong><p>在周期榜单页面点击“立即采集”后，任务会记录在这里。</p></div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>任务</th><th>状态</th><th>触发方式</th><th>开始时间</th><th>入库 / 更新</th><th>请求 / 返回</th><th>操作</th></tr></thead>
              <tbody>
                {items.map((job) => (
                  <tr key={job.id}>
                    <td><strong>{periodName(job.job_type)}</strong><small>{job.id.slice(0, 12)}…</small></td>
                    <td><span className={`job-status status-${job.status}`}>{label(job.status)}</span></td>
                    <td>{job.trigger_type === "manual" ? "手动" : job.trigger_type}</td>
                    <td>{date(job.started_at || job.created_at)}</td>
                    <td>{job.inserted_count} / {job.updated_count}</td>
                    <td>{job.request_count} / {job.fetched_count}</td>
                    <td>
                      <div className="job-actions">
                        <button className="text-button" onClick={() => void showDetails(job.id)}>
                          <FileText size={13} />详情
                        </button>
                        {["failed", "partial_success", "interrupted"].includes(job.status) && (
                          <button className="text-button" disabled={retrying === job.id} onClick={() => void retry(job)}>
                            <RotateCcw size={13} />{retrying === job.id ? "提交中" : "重试"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {detailLoading && <div className="surface-card job-detail-panel">正在读取任务详情…</div>}
      {selectedJob && (
        <section className="surface-card job-detail-panel">
          <div className="job-detail-heading">
            <div><span className="eyebrow">COLLECTION JOB DETAIL</span><h3>{periodName(selectedJob.job_type)} · {selectedJob.id}</h3></div>
            <button className="icon-button" onClick={() => setSelectedJob(null)} aria-label="关闭详情"><X size={16} /></button>
          </div>
          {selectedJob.error_message && <div className="job-error-message">{selectedJob.error_message}</div>}
          {selectedJob.retry_of_job_id && <p className="job-retry-link">重试来源：{selectedJob.retry_of_job_id}</p>}
          {selectedJob.stars_scan && (
            <div className="stars-job-summary">
              <strong>Stars 扫描覆盖</strong>
              <span>{selectedJob.stars_scan.coverage_description || "暂无覆盖说明"}</span>
              <small>
                扫描 #{selectedJob.stars_scan.id} · {selectedJob.stars_scan.shards.length} 个分片
                · {selectedJob.stars_scan.incomplete_results ? "API 返回不完整结果" : "API 未标记不完整"}
              </small>
            </div>
          )}
          <div className="job-detail-stats">
            <span>请求 {selectedJob.request_count}</span>
            <span>返回 {selectedJob.fetched_count}</span>
            <span>新增 {selectedJob.inserted_count}</span>
            <span>更新 {selectedJob.updated_count}</span>
            <span>去重 {selectedJob.deduplicated_count}</span>
            <span>重试 {selectedJob.retry_count}</span>
          </div>
          <div className="job-log-list">
            {selectedJob.logs.map((log) => (
              <div className="job-log-row" key={log.id}>
                <span className={log.level === "ERROR" ? "log-level error" : log.level === "WARNING" ? "log-level warning" : "log-level"}>{log.level}</span>
                <div><strong>{log.message}</strong><small>{date(log.created_at)}</small>
                  {Object.keys(log.details).length > 0 && <code>{JSON.stringify(log.details)}</code>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <p className="jobs-footnote">失败任务的重试会创建新的执行记录，并保留与原任务的关联；历史任务不会被覆盖。</p>
    </div>
  );
}
