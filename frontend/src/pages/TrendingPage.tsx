import { useCallback, useEffect, useState } from "react";
import {
  Activity, ArrowDown, ArrowUp, ExternalLink, Filter, RefreshCw, Search,
} from "lucide-react";
import {
  api,
  type CollectionJob,
  type TrendingItem,
  type TrendingPeriod,
  type TrendingSnapshot,
  type TrendingResponse,
} from "../services/api";

const periodOptions: { value: TrendingPeriod; label: string }[] = [
  { value: "daily", label: "日榜" },
  { value: "weekly", label: "周榜" },
  { value: "monthly", label: "月榜" },
];

const emptyResult: TrendingResponse = {
  snapshot: null,
  items: [],
  pagination: { page: 1, page_size: 25, total: 0, total_pages: 0 },
};

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN");
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function periodName(period: TrendingPeriod): string {
  return periodOptions.find((item) => item.value === period)?.label ?? "日榜";
}

function statusLabel(status: string): string {
  if (status === "success") return "采集成功";
  if (status === "partial_success") return "部分成功";
  if (status === "running") return "采集中";
  if (status === "queued") return "排队中";
  if (status === "failed") return "采集失败";
  return status;
}

function TrendingRow({ item }: { item: TrendingItem }) {
  return (
    <tr>
      <td><span className="rank-number">{String(item.rank).padStart(2, "0")}</span></td>
      <td className="trending-project-cell">
        <a href={item.html_url} target="_blank" rel="noreferrer" className="repo-link">
          {item.full_name}<ExternalLink size={12} />
        </a>
        <small>{item.description || "暂无项目简介"}</small>
        {item.topics.length > 0 && (
          <div className="topic-list">
            {item.topics.slice(0, 4).map((topic) => <span key={topic}>{topic}</span>)}
          </div>
        )}
      </td>
      <td>{item.language || "—"}</td>
      <td className="number-cell">{formatNumber(item.stars_count)}</td>
      <td className="number-cell delta-cell">+{formatNumber(item.stars_delta)}</td>
      <td className="number-cell">{formatNumber(item.forks_count)}</td>
    </tr>
  );
}

export default function TrendingPage() {
  const [period, setPeriod] = useState<TrendingPeriod>("daily");
  const [snapshots, setSnapshots] = useState<TrendingSnapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [result, setResult] = useState<TrendingResponse>(emptyResult);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [topic, setTopic] = useState("");
  const [sortBy, setSortBy] = useState<"rank" | "stars" | "delta" | "forks">("rank");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [activeJob, setActiveJob] = useState<CollectionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadSnapshots = useCallback(async () => {
    const response = await api.trendingSnapshots(period);
    setSnapshots(response.items);
    return response.items;
  }, [period]);

  const loadTrending = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.trending(period, {
        snapshotId,
        q: appliedQuery,
        language: language.trim(),
        topic: topic.trim(),
        sortBy,
        sortOrder,
        page,
      });
      setResult(response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取 Trending 榜单失败");
      setResult(emptyResult);
    } finally {
      setLoading(false);
    }
  }, [period, snapshotId, appliedQuery, language, topic, sortBy, sortOrder, page]);

  useEffect(() => {
    setSnapshotId(null);
    setPage(1);
    setQuery("");
    setAppliedQuery("");
    setLanguage("");
    setTopic("");
    setNotice(null);
  }, [period]);

  useEffect(() => {
    let active = true;
    api.trendingSnapshots(period)
      .then((response) => { if (active) setSnapshots(response.items); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取历史快照失败");
      });
    return () => { active = false; };
  }, [period]);

  useEffect(() => {
    void loadTrending();
  }, [loadTrending]);

  async function waitForJob(jobId: string): Promise<CollectionJob> {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const job = await api.collectionJob(jobId);
      setActiveJob(job);
      if (["success", "partial_success", "failed", "cancelled", "interrupted"].includes(job.status)) {
        return job;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error("采集仍在执行，可前往采集记录页面查看任务状态。");
  }

  async function handleCollect() {
    setCollecting(true);
    setNotice(null);
    setError(null);
    try {
      const response = await api.collectTrending(period);
      setActiveJob(response.job);
      const finished = await waitForJob(response.job.id);
      if (finished.status === "success" || finished.status === "partial_success") {
        const updatedSnapshots = await loadSnapshots();
        setSnapshotId(updatedSnapshots[0]?.id ?? null);
        setPage(1);
        setNotice(
          finished.status === "success"
            ? `${periodName(period)}采集完成，入库 ${finished.inserted_count} 个新项目，更新 ${finished.updated_count} 个项目。`
            : `${periodName(period)}采集部分完成，请查看采集日志了解跳过的条目。`,
        );
      } else {
        setError(finished.error_message || "采集失败，请在采集记录中查看详情。");
      }
      await loadTrending();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发起采集失败");
    } finally {
      setCollecting(false);
    }
  }

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setPage(1);
  }

  const snapshot = result.snapshot;
  const totalPages = result.pagination.total_pages;

  return (
    <div className="page-stack">
      <section className="trending-toolbar surface-card">
        <div className="period-switch" role="tablist" aria-label="Trending 周期">
          {periodOptions.map((option) => (
            <button
              key={option.value}
              className={period === option.value ? "period-tab active" : "period-tab"}
              onClick={() => setPeriod(option.value)}
              role="tab"
              aria-selected={period === option.value}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button className="button button-primary" onClick={() => void handleCollect()} disabled={collecting}>
          <RefreshCw size={14} className={collecting ? "spin" : ""} />
          {collecting ? "正在采集…" : "立即采集"}
        </button>
      </section>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      <section className="surface-card snapshot-panel">
        <div className="snapshot-main">
          <div className="snapshot-icon"><Activity size={18} /></div>
          <div>
            <span className="snapshot-eyebrow">{periodName(period)} · TRENDING SNAPSHOT</span>
            <strong>{snapshot ? `#${snapshot.id} · ${snapshot.period_key}` : "尚无历史快照"}</strong>
            <small>{snapshot ? `采集时间：${formatDate(snapshot.collected_at)} · ${snapshot.item_count} 个项目` : "首次使用请点击“立即采集”获取真实 GitHub 数据。"}</small>
          </div>
        </div>
        <div className="snapshot-actions">
          {snapshot && (
            <span className={snapshot.status === "success" ? "status-pill success" : "status-pill warning"}>
              {statusLabel(snapshot.status)}
            </span>
          )}
          <select
            aria-label="选择历史快照"
            value={snapshotId === null ? "latest" : String(snapshotId)}
            onChange={(event) => { setSnapshotId(event.target.value === "latest" ? null : Number(event.target.value)); setPage(1); }}
          >
            <option value="latest">最新快照</option>
            {snapshots.map((item) => (
              <option key={item.id} value={String(item.id)}>
                {formatDate(item.collected_at)} · {item.item_count} 项
              </option>
            ))}
          </select>
        </div>
      </section>

      {activeJob && collecting && (
        <div className="collection-progress">
          <span className="progress-spinner" />
          <span>{statusLabel(activeJob.status)} · {activeJob.progress}%</span>
          <div className="progress-track"><span style={{ width: `${activeJob.progress}%` }} /></div>
        </div>
      )}

      <section className="surface-card trending-filter-card">
        <form className="trending-filters" onSubmit={applyFilters}>
          <label className="search-field">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索仓库名称或简介…" />
          </label>
          <input className="filter-input" value={language} onChange={(event) => { setLanguage(event.target.value); setPage(1); }} placeholder="语言筛选" />
          <input className="filter-input" value={topic} onChange={(event) => { setTopic(event.target.value); setPage(1); }} placeholder="Topic 筛选" />
          <select value={sortBy} onChange={(event) => { setSortBy(event.target.value as typeof sortBy); setPage(1); }}>
            <option value="rank">按排名</option>
            <option value="stars">按 Stars</option>
            <option value="delta">按增量</option>
            <option value="forks">按 Forks</option>
          </select>
          <button className="button button-filter" type="submit"><Filter size={14} />筛选</button>
        </form>
        <div className="filter-meta">
          <span>{snapshot ? `快照 #${snapshot.id} · ${result.pagination.total} 个匹配项目` : "等待首次采集"}</span>
          <button className="text-button" onClick={() => { setSortOrder(sortOrder === "asc" ? "desc" : "asc"); setPage(1); }}>
            {sortOrder === "asc" ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
            {sortOrder === "asc" ? "升序" : "降序"}
          </button>
        </div>
      </section>

      <section className="surface-card trending-table-card">
        {loading ? (
          <div className="empty-state">正在读取本地历史快照…</div>
        ) : result.items.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon"><Activity size={24} /></span>
            <strong>{snapshot ? "没有符合条件的项目" : "还没有真实采集数据"}</strong>
            <p>{snapshot ? "尝试调整搜索关键词或筛选条件。" : "点击右上角“立即采集”，从 GitHub Trending 获取当前榜单。"}</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>排名</th><th>项目</th><th>语言</th><th>Stars</th><th>本期增量</th><th>Forks</th></tr></thead>
              <tbody>{result.items.map((item) => <TrendingRow key={item.repository_id} item={item} />)}</tbody>
            </table>
          </div>
        )}
        <div className="table-pagination">
          <span>第 {result.pagination.page} / {Math.max(totalPages, 1)} 页 · 共 {result.pagination.total} 条</span>
          <div>
            <button className="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
            <button className="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
          </div>
        </div>
      </section>

      <div className="source-note">
        <span>数据来源：GitHub Trending</span>
        {snapshot && <a href={snapshot.source_url} target="_blank" rel="noreferrer">打开原始来源 <ExternalLink size={11} /></a>}
      </div>
    </div>
  );
}
