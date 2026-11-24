import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ExternalLink, Filter, Github, RefreshCw, RotateCcw, Search, ShieldCheck,
} from "lucide-react";
import RepositoryWorkspaceActions from "../components/RepositoryWorkspaceActions";
import {
  api,
  type CollectionJob,
  type StarsLeaderboardResponse,
  type StarsScan,
  type StarsScanDetail,
} from "../services/api";

const emptyResult: StarsLeaderboardResponse = {
  scan: null,
  items: [],
  pagination: { page: 1, page_size: 50, total: 0, total_pages: 0 },
};

function number(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function date(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "采集中",
    success: "采集成功",
    partial_success: "部分覆盖",
    failed: "采集失败",
    interrupted: "任务中断",
  };
  return labels[value] ?? value;
}

function statusClass(value: string): string {
  if (value === "success") return "status-success";
  if (value === "partial_success") return "status-partial_success";
  if (value === "failed") return "status-failed";
  if (value === "running" || value === "queued") return "status-running";
  return "status-interrupted";
}

export default function StarsPage() {
  const [scans, setScans] = useState<StarsScan[]>([]);
  const [scanId, setScanId] = useState<number | null>(null);
  const [scanDetail, setScanDetail] = useState<StarsScanDetail | null>(null);
  const [result, setResult] = useState<StarsLeaderboardResponse>(emptyResult);
  const [maxResults, setMaxResults] = useState(5000);
  const [minStars, setMinStars] = useState(100);
  const [includeForks, setIncludeForks] = useState(false);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<CollectionJob | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshScans = useCallback(async () => {
    const response = await api.starsScans();
    setScans(response.items);
    return response.items;
  }, []);

  const loadLeaderboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.starsLeaderboard({
        scanId,
        q: appliedQuery,
        language: language.trim(),
        page,
      });
      setResult(response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取 Stars 总榜失败");
      setResult(emptyResult);
    } finally {
      setLoading(false);
    }
  }, [scanId, appliedQuery, language, page]);

  useEffect(() => {
    void refreshScans()
      .then((items) => {
        if (items.length > 0) setScanId(items[0].id);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "读取扫描历史失败"));
  }, [refreshScans]);

  useEffect(() => {
    if (scanId === null) {
      setScanDetail(null);
      return;
    }
    let active = true;
    api.starsScan(scanId)
      .then((scan) => { if (active) setScanDetail(scan); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取扫描详情失败");
      });
    return () => { active = false; };
  }, [scanId]);

  useEffect(() => {
    void loadLeaderboard();
  }, [loadLeaderboard]);

  useEffect(() => {
    if (!activeJobId) return;
    let active = true;
    const poll = async () => {
      try {
        const job = await api.collectionJob(activeJobId);
        if (!active) return;
        setActiveJob(job);
        if (["success", "partial_success", "failed", "interrupted", "cancelled"].includes(job.status)) {
          setCollecting(false);
          if (job.related_stars_scan_id) setScanId(job.related_stars_scan_id);
          if (job.status === "success") {
            setNotice("Stars 总榜采集完成，已保存新的历史扫描快照。");
          } else if (job.status === "partial_success") {
            setNotice("Stars 总榜已完成部分采集，请检查覆盖范围和分片状态。");
          } else {
            setError(job.error_message || "Stars 总榜采集失败，请查看采集记录。");
          }
          await refreshScans();
          if (job.related_stars_scan_id) {
            const [detail, leaderboard] = await Promise.all([
              api.starsScan(job.related_stars_scan_id),
              api.starsLeaderboard({ scanId: job.related_stars_scan_id }),
            ]);
            if (active) {
              setScanDetail(detail);
              setResult(leaderboard);
            }
          }
          setActiveJobId(null);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "读取采集进度失败");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [activeJobId, refreshScans]);

  async function startCollection() {
    setCollecting(true);
    setError(null);
    setNotice(null);
    setActiveJob(null);
    try {
      const response = await api.collectStars({
        max_results: maxResults,
        min_stars: minStars,
        include_forks: includeForks,
      });
      setScanId(response.scan_id);
      setActiveJob(response.job);
      setActiveJobId(response.job.id);
    } catch (reason) {
      setCollecting(false);
      setError(reason instanceof Error ? reason.message : "发起 Stars 采集失败");
    }
  }

  async function retryScan() {
    if (!scanDetail) return;
    setRetrying(true);
    setError(null);
    setNotice(null);
    try {
      const response = await api.retryStarsScan(scanDetail.id);
      setScanId(response.scan_id);
      setActiveJob(response.job);
      setActiveJobId(response.job.id);
      setCollecting(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试 Stars 采集失败");
    } finally {
      setRetrying(false);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setPage(1);
  }

  const scan = result.scan ?? scanDetail;
  const totalPages = result.pagination.total_pages;

  return (
    <div className="page-stack">
      <section className="stars-hero surface-card">
        <div className="stars-hero-copy">
          <div className="stars-hero-icon"><Github size={21} /></div>
          <div>
            <span className="eyebrow">GITHUB REPOSITORY SEARCH API</span>
            <h3>Stars 总榜</h3>
            <p>独立于 Trending 的公开仓库 Stars 排名，支持区间分片、历史扫描与覆盖审计。</p>
          </div>
        </div>
        <div className="stars-hero-controls">
          <label>
            <span>目标数量</span>
            <select value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))}>
              <option value={1000}>Top 1,000</option>
              <option value={3000}>Top 3,000</option>
              <option value={5000}>Top 5,000</option>
              <option value={10000}>Top 10,000</option>
            </select>
          </label>
          <label>
            <span>最低 Stars</span>
            <select value={minStars} onChange={(event) => setMinStars(Number(event.target.value))}>
              <option value={10}>10+</option>
              <option value={100}>100+</option>
              <option value={500}>500+</option>
              <option value={1000}>1,000+</option>
              <option value={5000}>5,000+</option>
            </select>
          </label>
          <label className="stars-fork-toggle">
            <input type="checkbox" checked={includeForks} onChange={(event) => setIncludeForks(event.target.checked)} />
            <span>包含 Fork</span>
          </label>
          <button className="button button-primary" onClick={() => void startCollection()} disabled={collecting}>
            <RefreshCw size={14} className={collecting ? "spin" : ""} />
            {collecting ? "正在扫描…" : "开始采集"}
          </button>
        </div>
      </section>

      <div className="stars-api-note">
        <ShieldCheck size={14} />
        <span>建议在根目录 .env 配置 GITHUB_TOKEN。Token 仅由后端读取；无 Token 时 Search API 限流更严格。</span>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      {collecting && activeJob && (
        <div className="collection-progress">
          <span className="progress-spinner" />
          <span>Stars 扫描中 · {Math.round(activeJob.progress)}%</span>
          <div className="progress-track"><span style={{ width: String(activeJob.progress) + "%" }} /></div>
          <small>{activeJob.request_count} 次请求 · 已获取 {number(activeJob.fetched_count)} 个</small>
        </div>
      )}

      <section className="stars-scan-summary surface-card">
        <div className="stars-scan-heading">
          <div>
            <span className="eyebrow">SCAN SNAPSHOT</span>
            <strong>{scan ? "#" + scan.id + " · " + statusLabel(scan.status) : "尚无 Stars 扫描记录"}</strong>
            <small>{scan ? "开始于 " + date(scan.started_at) + " · " + (scan.finished_at ? "完成于 " + date(scan.finished_at) : "任务尚未结束") : "点击“开始采集”获取第一份真实 Stars 总榜。"}</small>
          </div>
          <div className="stars-scan-actions">
            {scan && <span className={"job-status " + statusClass(scan.status)}>{statusLabel(scan.status)}</span>}
            {scan && (
              <select aria-label="选择历史 Stars 扫描" value={scanId ?? ""} onChange={(event) => { setScanId(Number(event.target.value)); setPage(1); }}>
                {scans.map((item) => (
                  <option key={item.id} value={item.id}>#{item.id} · {date(item.finished_at || item.started_at)}</option>
                ))}
              </select>
            )}
            {scan && ["failed", "partial_success", "interrupted"].includes(scan.status) && (
              <button className="button button-quiet" onClick={() => void retryScan()} disabled={retrying || collecting}>
                <RotateCcw size={13} />{retrying ? "提交中…" : "重试扫描"}
              </button>
            )}
          </div>
        </div>

        <div className="stars-metrics-grid">
          <div><span>已保存项目</span><strong>{number(scan?.fetched_count ?? 0)}</strong></div>
          <div><span>扫描范围匹配</span><strong>{number(scan?.total_count ?? 0)}</strong></div>
          <div><span>重复仓库</span><strong>{number(scan?.deduplicated_count ?? 0)}</strong></div>
          <div><span>分片数量</span><strong>{number(scanDetail?.shards.length ?? 0)}</strong></div>
        </div>
        {scan?.coverage_description && <p className="stars-coverage">{scan.coverage_description}</p>}
        {scan?.incomplete_results && <div className="alert alert-warning">GitHub Search API 标记了不完整结果，当前扫描不能视为完整覆盖。</div>}
        {scan?.error_summary && <div className="alert alert-warning">{scan.error_summary}</div>}
      </section>

      <section className="surface-card stars-filter-card">
        <form className="trending-filters" onSubmit={applyFilters}>
          <label className="search-field">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索仓库名称或简介…" />
          </label>
          <input className="filter-input" value={language} onChange={(event) => { setLanguage(event.target.value); setPage(1); }} placeholder="语言筛选" />
          <button className="button button-filter" type="submit"><Filter size={14} />筛选</button>
        </form>
        <div className="filter-meta">
          <span>{scan ? "扫描 #" + scan.id + " · " + number(result.pagination.total) + " 个匹配项目" : "等待首次采集"}</span>
          <span>按 Stars 降序排列</span>
        </div>
      </section>

      <section className="surface-card stars-table-card">
        {loading ? (
          <div className="empty-state">正在读取本地 Stars 快照…</div>
        ) : result.items.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon"><Github size={24} /></span>
            <strong>{scan ? "没有符合条件的仓库" : "还没有 Stars 总榜数据"}</strong>
            <p>{scan ? "尝试调整搜索关键词或语言筛选。" : "开始一次 Stars 扫描后，这里将展示真实 GitHub 排名。"}</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>排名</th><th>GitHub 仓库</th><th>语言</th><th>Stars</th><th>Forks</th><th>工作区</th></tr></thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.repository_id}>
                    <td><span className="rank-number">{String(item.rank).padStart(2, "0")}</span></td>
                    <td className="trending-project-cell">
                      <Link to={"/repositories/" + item.repository_id} className="repo-link">{item.full_name}</Link>
                      <a href={item.html_url} target="_blank" rel="noreferrer" className="repo-external-link" aria-label="打开 GitHub 仓库">
                        <ExternalLink size={12} />
                      </a>
                      <small>{item.description || "暂无项目简介"}</small>
                      {item.topics.length > 0 && <div className="topic-list">{item.topics.slice(0, 4).map((topic) => <span key={topic}>{topic}</span>)}</div>}
                    </td>
                    <td>{item.language || "—"}</td>
                    <td className="number-cell stars-count-cell">{number(item.stars_count)}</td>
                    <td className="number-cell">{number(item.forks_count)}</td>
                    <td className="workspace-action-cell"><RepositoryWorkspaceActions
                      repositoryId={item.repository_id}
                      interested={item.interested}
                      researchStatus={item.research_status}
                      sourcePage="stars"
                      compact
                    /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-pagination">
          <span>第 {result.pagination.page} / {Math.max(totalPages, 1)} 页 · 共 {number(result.pagination.total)} 条</span>
          <div>
            <button className="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
            <button className="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
          </div>
        </div>
      </section>

      {scanDetail && scanDetail.shards.length > 0 && (
        <details className="surface-card stars-shards-panel">
          <summary>
            <span><strong>分片覆盖详情</strong><small>{scanDetail.shards.length} 个查询分片 · 展开查看每个 Stars 区间</small></span>
            <span className="text-button">查看分片</span>
          </summary>
          <div className="table-scroll">
            <table>
              <thead><tr><th>分片</th><th>状态</th><th>匹配数</th><th>获取数</th><th>不完整</th><th>查询范围</th></tr></thead>
              <tbody>
                {scanDetail.shards.map((shard) => (
                  <tr key={shard.id}>
                    <td><strong>{shard.shard_key}</strong></td>
                    <td><span className={"job-status " + statusClass(shard.status)}>{statusLabel(shard.status)}</span></td>
                    <td>{number(shard.total_count)}</td>
                    <td>{number(shard.fetched_count)}</td>
                    <td>{shard.incomplete_results ? "是" : "否"}</td>
                    <td><code className="stars-query-code">{shard.query_text}</code>{shard.error_message && <small className="stars-shard-error">{shard.error_message}</small>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <div className="source-note">
        <span>数据来源：GitHub REST Search Repositories API · SQLite 历史扫描</span>
        <a href="https://docs.github.com/en/rest/search/search#search-repositories" target="_blank" rel="noreferrer">API 文档 <ExternalLink size={11} /></a>
      </div>
    </div>
  );
}
