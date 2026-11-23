import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, Bookmark,
  Database, FolderSearch, RefreshCw, Sparkles, Telescope,
} from "lucide-react";
import { api, type DashboardAnalytics, type TrendingPeriod } from "../services/api";

const periodOptions: { value: TrendingPeriod; label: string }[] = [
  { value: "daily", label: "日榜" },
  { value: "weekly", label: "周榜" },
  { value: "monthly", label: "月榜" },
];

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚无采集记录";
}

function periodLabel(period: TrendingPeriod): string {
  return periodOptions.find((item) => item.value === period)?.label ?? period;
}

function SnapshotTrendChart({ data }: { data: DashboardAnalytics["trend_series"] }) {
  const width = 720;
  const height = 190;
  const paddingX = 22;
  const paddingY = 18;
  const values = data.map((item) => Number(item.average_stars ?? 0));
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const range = Math.max(maxValue - minValue, 1);
  const points = values.map((value, index) => {
    const x = data.length <= 1
      ? width / 2
      : paddingX + (index / (data.length - 1)) * (width - paddingX * 2);
    const y = height - paddingY - ((value - minValue) / range) * (height - paddingY * 2);
    return String(x) + "," + String(y);
  });

  if (data.length === 0) {
    return <div className="analytics-empty">完成 Trending 采集后，这里会显示历史 Stars 均值走势。</div>;
  }

  return (
    <div className="analytics-chart-wrap">
      <svg className="analytics-line-chart" viewBox={"0 0 " + width + " " + height} role="img" aria-label="历史榜单平均 Stars 走势">
        {[0, 1, 2, 3].map((line) => {
          const y = paddingY + (line / 3) * (height - paddingY * 2);
          return <line key={line} x1={paddingX} x2={width - paddingX} y1={y} y2={y} className="chart-grid-line" />;
        })}
        <polyline points={points.join(" ")} className="chart-line" />
        {data.map((item, index) => {
          const coords = points[index].split(",").map(Number);
          return (
            <circle key={item.id} cx={coords[0]} cy={coords[1]} r="3.8" className="chart-point">
              <title>{item.period_key + " · 平均 " + formatNumber(Number(item.average_stars ?? 0)) + " Stars"}</title>
            </circle>
          );
        })}
      </svg>
      <div className="analytics-chart-labels">
        {data.map((item) => <span key={item.id}>{item.period_key}</span>)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [period, setPeriod] = useState<TrendingPeriod>("daily");
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.dashboardAnalytics(period)
      .then((result) => { if (active) setAnalytics(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取趋势分析失败");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [period, refreshKey]);

  const summary = analytics?.summary;
  const maxLanguage = useMemo(
    () => Math.max(1, ...(analytics?.language_distribution.map((item) => item.value) ?? [])),
    [analytics],
  );
  const latestSnapshot = analytics?.period_snapshots[period]?.latest;
  const latestStars = analytics?.latest_stars_scan;

  const cards = [
    { label: "项目库总量", value: summary?.repositories ?? 0, hint: "统一仓库主档", icon: FolderSearch },
    { label: periodLabel(period) + "收录", value: summary?.latest_period_items ?? 0, hint: "当前最新历史快照", icon: Activity },
    { label: "新晋上榜", value: summary?.new_items_vs_previous ?? 0, hint: "相较上一批次", icon: Sparkles },
    { label: "跨周期热门", value: summary?.cross_period_hot_projects ?? 0, hint: "至少两个周期进入 Top 100", icon: BarChart3 },
  ];

  return (
    <div className="page-stack">
      <section className="welcome-panel analytics-welcome">
        <div>
          <span className="eyebrow">DISCOVER · TRACK · ANALYZE</span>
          <h2>让开源项目的热度变化，一目了然。</h2>
          <p>聚合 Trending 历史快照与 Stars 扫描结果，识别新晋项目、跨周期热门和持续增长的技术方向。</p>
          <div className="analytics-welcome-links">
            <Link to="/trending">查看周期榜单</Link>
            <Link to="/compare">比较历史快照</Link>
            <Link to="/stars">Stars 总榜</Link>
          </div>
        </div>
        <div className="welcome-mark"><Telescope size={42} strokeWidth={1.4} /></div>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="section-heading">
        <div>
          <h3>趋势总览</h3>
          <p>全部指标来自本机 SQLite 已保存数据，不会在打开总览时触发 GitHub 请求。</p>
        </div>
        <button className="button button-quiet" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading}>
          <RefreshCw size={14} className={loading ? "spin" : ""} />刷新分析
        </button>
      </div>

      <div className="analytics-period-switch" role="tablist" aria-label="分析周期">
        {periodOptions.map((item) => (
          <button key={item.value} role="tab" aria-selected={period === item.value}
            className={period === item.value ? "period-tab active" : "period-tab"}
            onClick={() => setPeriod(item.value)}>{item.label}</button>
        ))}
      </div>

      <section className="stat-grid analytics-stat-grid">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <article className="stat-card" key={card.label}>
              <div className="stat-card-top">
                <span>{card.label}</span>
                <span className="stat-icon"><Icon size={18} /></span>
              </div>
              <strong>{loading ? "—" : formatNumber(card.value)}</strong>
              <small>{card.hint}</small>
            </article>
          );
        })}
      </section>

      <section className="analytics-main-grid">
        <article className="surface-card analytics-chart-card">
          <div className="card-heading">
            <div><h3>历史热度走势</h3><p>{periodLabel(period)}最近 12 次快照的榜单平均 Stars</p></div>
            <span className="analytics-chart-unit">AVG. STARS</span>
          </div>
          {loading ? <div className="analytics-empty">正在读取历史数据…</div> : (
            <SnapshotTrendChart data={analytics?.trend_series ?? []} />
          )}
        </article>
        <article className="surface-card analytics-source-card">
          <div className="card-heading">
            <div><h3>数据采集状态</h3><p>最近一次成功或部分成功的采集</p></div>
            <span className="status-dot status-idle">本地快照</span>
          </div>
          <div className="analytics-source-row">
            <span>最新{periodLabel(period)}</span>
            <strong>{formatDate(latestSnapshot?.collected_at)}</strong>
            <small>{latestSnapshot ? "快照 #" + latestSnapshot.id + " · " + latestSnapshot.item_count + " 个项目 · " + (latestSnapshot.status === "success" ? "完整成功" : "部分成功") : "尚无历史快照"}</small>
          </div>
          <div className="analytics-source-row">
            <span>最新 Stars 总榜</span>
            <strong>{formatDate(latestStars?.finished_at)}</strong>
            <small>{latestStars ? "扫描 #" + latestStars.id + " · 获取 " + formatNumber(latestStars.fetched_count) + " 个仓库" + (latestStars.incomplete_results ? " · API 结果不完整" : "") : "尚无 Stars 扫描记录"}</small>
          </div>
          {analytics?.latest_stars_top && (
            <div className="analytics-top-repo">
              <span>Stars 榜首</span>
              <strong>{analytics.latest_stars_top.full_name}</strong>
              <b>{formatNumber(analytics.latest_stars_top.stars_count)} ★</b>
            </div>
          )}
        </article>
      </section>

      <section className="analytics-distribution-grid">
        <article className="surface-card analytics-distribution-card">
          <div className="card-heading"><div><h3>主要语言分布</h3><p>当前{periodLabel(period)}快照</p></div></div>
          {loading ? <div className="analytics-empty">读取中…</div> : analytics?.language_distribution.length ? (
            <div className="analytics-bars">
              {analytics.language_distribution.map((item) => (
                <div className="analytics-bar-row" key={item.name}>
                  <span>{item.name}</span>
                  <div className="analytics-bar-track"><i style={{ width: (item.value / maxLanguage * 100) + "%" }} /></div>
                  <b>{item.value}</b>
                </div>
              ))}
            </div>
          ) : <div className="analytics-empty">暂无语言分布数据</div>}
        </article>
        <article className="surface-card analytics-distribution-card">
          <div className="card-heading"><div><h3>热门 Topics</h3><p>按当前快照中的仓库覆盖数排序</p></div></div>
          {loading ? <div className="analytics-empty">读取中…</div> : analytics?.topic_distribution.length ? (
            <div className="analytics-topic-list">
              {analytics.topic_distribution.map((item, index) => (
                <span key={item.name}><i>{index + 1}</i>{item.name}<b>{item.value}</b></span>
              ))}
            </div>
          ) : <div className="analytics-empty">当前快照没有可用 Topic</div>}
        </article>
      </section>

      <section className="surface-card analytics-cross-card">
        <div className="card-heading">
          <div><h3>跨周期热门项目</h3><p>同一项目在日榜、周榜、月榜中的最新排名交叉呈现</p></div>
          <Link className="text-button" to="/compare">进入历史对比 <ArrowUpRight size={13} /></Link>
        </div>
        {loading ? <div className="analytics-empty">正在读取项目矩阵…</div> : analytics?.cross_period_items.length ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>项目</th><th>语言</th><th>日榜</th><th>周榜</th><th>月榜</th><th>Stars</th></tr></thead>
              <tbody>
                {analytics.cross_period_items.map((item) => (
                  <tr key={item.repository_id}>
                    <td className="trending-project-cell">
                      <Link className="repo-link" to={"/repositories/" + item.repository_id}>{item.full_name}</Link>
                      <small>{item.description || "暂无项目简介"}</small>
                    </td>
                    <td>{item.language || "—"}</td>
                    <td>{item.rank_daily ? "#" + item.rank_daily : "—"}</td>
                    <td>{item.rank_weekly ? "#" + item.rank_weekly : "—"}</td>
                    <td>{item.rank_monthly ? "#" + item.rank_monthly : "—"}</td>
                    <td className="number-cell">{formatNumber(item.stars_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="analytics-empty">当前还没有可交叉比较的 Trending 快照。</div>}
      </section>

      <section className="analytics-footer-metrics">
        <div><Bookmark size={15} /><span>感兴趣项目</span><strong>{formatNumber(summary?.interested_projects ?? 0)}</strong></div>
        <div><Database size={15} /><span>研究项目</span><strong>{formatNumber(summary?.research_projects ?? 0)}</strong></div>
        <div><ArrowDownRight size={15} /><span>历史快照</span><strong>{formatNumber(summary?.successful_trending_snapshots ?? 0)}</strong></div>
      </section>
    </div>
  );
}
