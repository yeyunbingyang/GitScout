import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown, ArrowUp, Download, Filter, RefreshCw, Search,
  TrendingDown, TrendingUp, Minus, Plus,
} from "lucide-react";
import {
  api,
  type ComparisonChangeType,
  type TrendingComparisonResponse,
  type TrendingPeriod,
  type TrendingSnapshot,
} from "../services/api";

const periods: { value: TrendingPeriod; label: string }[] = [
  { value: "daily", label: "日榜" },
  { value: "weekly", label: "周榜" },
  { value: "monthly", label: "月榜" },
];

const changeOptions: { value: ComparisonChangeType; label: string }[] = [
  { value: "all", label: "全部变化" },
  { value: "new", label: "新晋上榜" },
  { value: "dropped", label: "本次掉榜" },
  { value: "up", label: "排名上升" },
  { value: "down", label: "排名下降" },
  { value: "unchanged", label: "排名不变" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function statusText(type: string): string {
  return changeOptions.find((item) => item.value === type)?.label ?? type;
}

function statusClass(type: string): string {
  return "compare-change compare-change-" + type;
}

function rankText(value: number | null): string {
  return value === null ? "—" : "#" + value;
}

export default function ComparisonPage() {
  const [period, setPeriod] = useState<TrendingPeriod>("daily");
  const [snapshots, setSnapshots] = useState<TrendingSnapshot[]>([]);
  const [baseId, setBaseId] = useState<number | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const [changeType, setChangeType] = useState<ComparisonChangeType>("all");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<TrendingComparisonResponse | null>(null);
  const [loadingSnapshots, setLoadingSnapshots] = useState(true);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingSnapshots(true);
    setSnapshots([]);
    setBaseId(null);
    setTargetId(null);
    setResult(null);
    api.trendingSnapshots(period)
      .then((response) => {
        if (!active) return;
        setSnapshots(response.items);
        setTargetId(response.items[0]?.id ?? null);
        setBaseId(response.items[1]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取历史快照失败");
      })
      .finally(() => { if (active) setLoadingSnapshots(false); });
    return () => { active = false; };
  }, [period]);

  useEffect(() => {
    if (baseId === null || targetId === null || baseId === targetId) {
      setResult(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    api.compareTrending({
      baseSnapshotId: baseId,
      targetSnapshotId: targetId,
      changeType,
      q: appliedQuery,
      language: language.trim(),
      page,
      pageSize: 50,
    })
      .then((response) => { if (active) setResult(response); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "比较历史快照失败");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [baseId, targetId, changeType, appliedQuery, language, page]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setPage(1);
  }

  async function exportCsv() {
    if (baseId === null || targetId === null || !result) return;
    setExporting(true);
    setError(null);
    try {
      const allItems: TrendingComparisonResponse["items"] = [];
      const totalPages = result.pagination.total_pages;
      for (let currentPage = 1; currentPage <= totalPages; currentPage += 1) {
        const response = await api.compareTrending({
          baseSnapshotId: baseId,
          targetSnapshotId: targetId,
          changeType,
          q: appliedQuery,
          language: language.trim(),
          page: currentPage,
          pageSize: 100,
        });
        allItems.push(...response.items);
      }
      const header = ["仓库", "语言", "上次排名", "本次排名", "排名变化", "变化类型", "Stars", "本期增量", "Forks", "GitHub URL"];
      const rows = allItems.map((item) => [
        item.full_name,
        item.language ?? "",
        item.base_rank ?? "",
        item.target_rank ?? "",
        item.rank_change ?? "",
        statusText(item.change_type),
        item.stars_count,
        item.stars_delta,
        item.forks_count,
        item.html_url,
      ]);
      const escape = (value: string | number) => '"' + String(value).replace(/"/g, '""') + '"';
      const csv = "\uFEFF" + [header, ...rows].map((row) => row.map(escape).join(",")).join("\r\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "gitscout-" + period + "-comparison-" + baseId + "-to-" + targetId + ".csv";
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出对比结果失败");
    } finally {
      setExporting(false);
    }
  }

  const summary = result?.summary;
  const totalPages = result?.pagination.total_pages ?? 0;
  const baseSnapshot = snapshots.find((item) => item.id === baseId);
  const targetSnapshot = snapshots.find((item) => item.id === targetId);

  return (
    <div className="page-stack">
      <section className="compare-intro surface-card">
        <div>
          <span className="eyebrow">HISTORICAL SNAPSHOT ANALYSIS</span>
          <h3>周期趋势对比</h3>
          <p>选择同一周期的两次历史快照，识别新晋、掉榜、排名上升和下降的项目。所有结果均来自本地历史记录。</p>
        </div>
        <div className="compare-intro-icon"><TrendingUp size={24} /></div>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="surface-card compare-selector">
        <div className="compare-period-switch">
          {periods.map((item) => (
            <button key={item.value} className={period === item.value ? "period-tab active" : "period-tab"}
              onClick={() => setPeriod(item.value)}>{item.label}</button>
          ))}
        </div>
        <div className="compare-selectors-row">
          <label>
            <span>基准快照 · 较早</span>
            <select value={baseId ?? ""} disabled={loadingSnapshots || snapshots.length < 2}
              onChange={(event) => { setBaseId(Number(event.target.value)); setPage(1); }}>
              <option value="">选择基准快照</option>
              {snapshots.map((item) => <option key={item.id} value={item.id}>#{item.id} · {formatDate(item.collected_at)} · {item.item_count} 项</option>)}
            </select>
          </label>
          <div className="compare-direction"><ArrowUp size={16} /><span>对比变化</span><ArrowDown size={16} /></div>
          <label>
            <span>目标快照 · 较新</span>
            <select value={targetId ?? ""} disabled={loadingSnapshots || snapshots.length < 2}
              onChange={(event) => { setTargetId(Number(event.target.value)); setPage(1); }}>
              <option value="">选择目标快照</option>
              {snapshots.map((item) => <option key={item.id} value={item.id}>#{item.id} · {formatDate(item.collected_at)} · {item.item_count} 项</option>)}
            </select>
          </label>
          <button className="button button-quiet" onClick={() => { setBaseId(snapshots[1]?.id ?? null); setTargetId(snapshots[0]?.id ?? null); setPage(1); }}
            disabled={loadingSnapshots || snapshots.length < 2}>
            <RefreshCw size={13} />最新两次
          </button>
        </div>
        {baseSnapshot && targetSnapshot && (
          <div className="compare-selected-meta">
            <span>基准：{baseSnapshot.period_key} · {baseSnapshot.item_count} 项</span>
            <span>目标：{targetSnapshot.period_key} · {targetSnapshot.item_count} 项</span>
          </div>
        )}
      </section>

      {loadingSnapshots ? (
        <div className="surface-card analytics-empty">正在读取历史快照…</div>
      ) : snapshots.length < 2 ? (
        <div className="surface-card compare-empty">
          <span><DatabaseIcon /></span>
          <strong>至少需要两次 {period === "daily" ? "日榜" : period === "weekly" ? "周榜" : "月榜"}采集</strong>
          <p>当前历史快照不足，先前往周期榜单完成采集；后续可在这里比较新增、掉榜与排名变化。</p>
          <Link className="button button-primary" to="/trending">前往周期榜单</Link>
        </div>
      ) : baseId === targetId ? (
        <div className="alert alert-warning">基准快照和目标快照不能相同，请选择两个不同批次。</div>
      ) : (
        <>
          <section className="compare-summary-grid">
            <div className="compare-summary-card"><span>新晋上榜</span><strong>{formatNumber(summary?.new ?? 0)}</strong><small><Plus size={12} />目标快照新增</small></div>
            <div className="compare-summary-card"><span>排名上升</span><strong>{formatNumber(summary?.up ?? 0)}</strong><small><TrendingUp size={12} />名次向前</small></div>
            <div className="compare-summary-card"><span>排名下降</span><strong>{formatNumber(summary?.down ?? 0)}</strong><small><TrendingDown size={12} />名次向后</small></div>
            <div className="compare-summary-card"><span>本次掉榜</span><strong>{formatNumber(summary?.dropped ?? 0)}</strong><small><Minus size={12} />未出现在目标快照</small></div>
          </section>

          <section className="surface-card compare-filter-card">
            <form className="trending-filters" onSubmit={applyFilters}>
              <label className="search-field">
                <Search size={15} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索仓库名称或简介…" />
              </label>
              <input className="filter-input" value={language} onChange={(event) => { setLanguage(event.target.value); setPage(1); }} placeholder="语言筛选" />
              <select value={changeType} onChange={(event) => { setChangeType(event.target.value as ComparisonChangeType); setPage(1); }}>
                {changeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <button className="button button-filter" type="submit"><Filter size={14} />筛选</button>
              <button className="button button-quiet" type="button" onClick={() => void exportCsv()} disabled={exporting || loading || !result}>
                <Download size={14} />{exporting ? "导出中…" : "导出 CSV"}
              </button>
            </form>
            <div className="filter-meta">
              <span>匹配 {formatNumber(result?.pagination.total ?? 0)} 个项目 · 共 {formatNumber(summary?.total ?? 0)} 个变化记录</span>
              <span>排名变化 = 基准排名 − 目标排名，正数表示上升</span>
            </div>
          </section>

          <section className="surface-card compare-table-card">
            {loading ? <div className="empty-state">正在计算快照差异…</div> : result?.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>项目</th><th>语言</th><th>基准排名</th><th>目标排名</th><th>排名变化</th><th>状态</th><th>Stars</th></tr></thead>
                  <tbody>
                    {result.items.map((item) => (
                      <tr key={item.repository_id}>
                        <td className="trending-project-cell">
                          <Link className="repo-link" to={"/repositories/" + item.repository_id}>{item.full_name}</Link>
                          <small>{item.description || "暂无项目简介"}</small>
                        </td>
                        <td>{item.language || "—"}</td>
                        <td>{rankText(item.base_rank)}</td>
                        <td>{rankText(item.target_rank)}</td>
                        <td className="compare-rank-change">
                          {item.rank_change === null ? "—" : item.rank_change > 0 ? <span className="rank-up"><ArrowUp size={12} />{item.rank_change}</span> : item.rank_change < 0 ? <span className="rank-down"><ArrowDown size={12} />{Math.abs(item.rank_change)}</span> : <span className="rank-same">0</span>}
                        </td>
                        <td><span className={statusClass(item.change_type)}>{statusText(item.change_type)}</span></td>
                        <td className="number-cell">{formatNumber(item.stars_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="empty-state">没有符合当前筛选条件的项目。</div>}
            <div className="table-pagination">
              <span>第 {result?.pagination.page ?? page} / {Math.max(totalPages, 1)} 页 · 共 {formatNumber(result?.pagination.total ?? 0)} 条</span>
              <div>
                <button className="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
                <button className="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
              </div>
            </div>
          </section>
        </>
      )}
      <div className="source-note"><span>比较规则：仓库 ID 匹配 · 同周期快照 · 未出现表示未进入该批次采集范围，不代表项目热度为零。</span></div>
    </div>
  );
}

function DatabaseIcon() {
  return <span className="compare-empty-database">DB</span>;
}
