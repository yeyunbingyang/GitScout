import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, ExternalLink, GitFork, Github, History, Star,
  TrendingDown, TrendingUp,
} from "lucide-react";
import { api, type RepositoryDetailResponse, type TrendingPeriod } from "../services/api";

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function periodLabel(period: TrendingPeriod): string {
  return period === "daily" ? "日榜" : period === "weekly" ? "周榜" : "月榜";
}

function StarsHistoryChart({ data }: { data: RepositoryDetailResponse["stars_history"] }) {
  const pointsData = [...data].reverse();
  if (pointsData.length === 0) {
    return <div className="analytics-empty">该项目还没有两次以上 Stars 扫描记录。</div>;
  }
  const width = 760;
  const height = 210;
  const padX = 26;
  const padY = 24;
  const values = pointsData.map((item) => item.stars_count);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = Math.max(maxValue - minValue, 1);
  const coords = pointsData.map((item, index) => {
    const x = pointsData.length === 1
      ? width / 2
      : padX + index / (pointsData.length - 1) * (width - padX * 2);
    const y = height - padY - (item.stars_count - minValue) / range * (height - padY * 2);
    return { x, y, item };
  });
  return (
    <div className="repository-chart-wrap">
      <svg viewBox={"0 0 " + width + " " + height} className="repository-stars-chart" role="img" aria-label="项目 Stars 历史变化">
        {[0, 1, 2, 3].map((line) => {
          const y = padY + line / 3 * (height - padY * 2);
          return <line key={line} x1={padX} x2={width - padX} y1={y} y2={y} className="chart-grid-line" />;
        })}
        <polyline points={coords.map((point) => point.x + "," + point.y).join(" ")} className="chart-line" />
        {coords.map((point) => (
          <circle key={point.item.scan_id} cx={point.x} cy={point.y} r="4" className="chart-point">
            <title>{formatDate(point.item.captured_at) + " · " + formatNumber(point.item.stars_count) + " Stars"}</title>
          </circle>
        ))}
      </svg>
      <div className="analytics-chart-labels">
        {pointsData.map((item) => <span key={item.scan_id}>{new Date(item.captured_at).toLocaleDateString("zh-CN")}</span>)}
      </div>
    </div>
  );
}

export default function RepositoryDetailPage() {
  const { repositoryId } = useParams();
  const id = Number(repositoryId);
  const [detail, setDetail] = useState<RepositoryDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    if (!Number.isInteger(id) || id <= 0) {
      setError("无效的项目 ID");
      setLoading(false);
      return;
    }
    api.repositoryDetail(id)
      .then((result) => { if (active) setDetail(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取项目详情失败");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  if (loading) {
    return <div className="surface-card analytics-empty">正在读取项目详情…</div>;
  }
  if (error || !detail) {
    return (
      <div className="page-stack">
        <div className="alert alert-error">{error || "项目不存在"}</div>
        <Link className="button button-quiet" to="/repositories"><ArrowLeft size={14} />返回项目库</Link>
      </div>
    );
  }

  const repository = detail.repository;
  const summary = detail.summary;
  const growth = summary.observed_stars_growth;
  return (
    <div className="page-stack">
      <div className="repository-back-row">
        <Link to="/repositories"><ArrowLeft size={14} />返回项目库</Link>
        <span>PROJECT PROFILE · LOCAL HISTORY</span>
      </div>

      <section className="surface-card repository-hero">
        <div className="repository-avatar"><Github size={28} /></div>
        <div className="repository-hero-copy">
          <span className="eyebrow">{repository.owner}</span>
          <h2>{repository.full_name}</h2>
          <p>{repository.description || "暂无项目简介"}</p>
          <div className="repository-topic-list">
            {repository.topics.map((topic) => <span key={topic}>{topic}</span>)}
          </div>
        </div>
        <a className="button button-primary" href={repository.html_url} target="_blank" rel="noreferrer">
          打开 GitHub <ExternalLink size={13} />
        </a>
      </section>

      <section className="repository-stat-grid">
        <div className="repository-stat-card"><span><Star size={14} />当前 Stars</span><strong>{formatNumber(repository.stars_count)}</strong><small>最近同步 {formatDate(repository.last_synced_at)}</small></div>
        <div className="repository-stat-card"><span><GitFork size={14} />Forks</span><strong>{formatNumber(repository.forks_count)}</strong><small>Open Issues {formatNumber(repository.open_issues_count)}</small></div>
        <div className="repository-stat-card"><span><History size={14} />趋势上榜次数</span><strong>{formatNumber(summary.trending_appearances)}</strong><small>覆盖日 / 周 / 月历史快照</small></div>
        <div className="repository-stat-card"><span>{growth !== null && growth >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}Stars 观测变化</span><strong className={growth !== null && growth < 0 ? "negative-value" : ""}>{growth === null ? "—" : (growth > 0 ? "+" : "") + formatNumber(growth)}</strong><small>基于已保存 Stars 扫描，不代表实时变化</small></div>
      </section>

      <section className="repository-performance-grid">
        <article className="surface-card repository-rank-card">
          <div className="card-heading"><div><h3>周期最佳排名</h3><p>历史快照中记录到的最好名次</p></div></div>
          <div className="repository-best-ranks">
            {(["daily", "weekly", "monthly"] as TrendingPeriod[]).map((period) => (
              <div key={period}><span>{periodLabel(period)}</span><strong>{summary.best_rank_by_period[period] ? "#" + summary.best_rank_by_period[period] : "—"}</strong></div>
            ))}
          </div>
          <div className="repository-first-last">
            <span>首次趋势上榜 <strong>{formatDate(summary.first_trending_at)}</strong></span>
            <span>最近趋势上榜 <strong>{formatDate(summary.last_trending_at)}</strong></span>
          </div>
        </article>
        <article className="surface-card repository-state-card">
          <div className="card-heading"><div><h3>个人工作区状态</h3><p>兴趣标记和研究记录相互独立</p></div></div>
          <div className="repository-state-row"><span>感兴趣</span><strong>{repository.interested ? "已标记" : "未标记"}</strong></div>
          <div className="repository-state-row"><span>研究状态</span><strong>{repository.research ? repository.research.status : "尚未加入研究"}</strong></div>
          {repository.research?.research_goal && <p className="repository-research-goal">{repository.research.research_goal}</p>}
        </article>
      </section>

      <section className="surface-card repository-history-card">
        <div className="card-heading"><div><h3>Stars 历史走势</h3><p>{summary.stars_scan_observations} 次已保存 Stars 扫描 · 仅展示历史观测值</p></div></div>
        <StarsHistoryChart data={detail.stars_history} />
      </section>

      <section className="surface-card repository-history-card">
        <div className="card-heading"><div><h3>Trending 上榜记录</h3><p>按采集时间倒序 · 历史快照不可覆盖</p></div></div>
        {detail.trending_history.length ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>周期</th><th>批次</th><th>采集时间</th><th>排名</th><th>Stars</th><th>本期增量</th><th>Forks</th></tr></thead>
              <tbody>
                {detail.trending_history.map((item) => (
                  <tr key={item.snapshot_id}>
                    <td>{periodLabel(item.period_type)}</td>
                    <td>#{item.snapshot_id} · {item.period_key}</td>
                    <td>{formatDate(item.collected_at)}</td>
                    <td><strong className="rank-number">#{item.rank}</strong></td>
                    <td>{formatNumber(item.stars_count)}</td>
                    <td className="delta-cell">+{formatNumber(item.stars_delta)}</td>
                    <td>{formatNumber(item.forks_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="analytics-empty">该项目还没有 Trending 上榜历史。</div>}
      </section>

      <section className="surface-card repository-history-card">
        <div className="card-heading"><div><h3>Stars 扫描记录</h3><p>每次 Stars 总榜扫描对该项目的排名和数量记录</p></div></div>
        {detail.stars_history.length ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>扫描批次</th><th>采集时间</th><th>排名</th><th>Stars</th><th>Forks</th><th>状态</th></tr></thead>
              <tbody>
                {detail.stars_history.map((item) => (
                  <tr key={item.scan_id}>
                    <td>#{item.scan_id}</td>
                    <td>{formatDate(item.captured_at)}</td>
                    <td>#{item.rank}</td>
                    <td>{formatNumber(item.stars_count)}</td>
                    <td>{formatNumber(item.forks_count)}</td>
                    <td>{item.scan_status === "success" ? "成功" : "部分成功"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="analytics-empty">该项目还没有 Stars 总榜历史记录。</div>}
      </section>

      <div className="source-note">
        <span>仓库 ID：{repository.github_repo_id ?? "—"} · License：{repository.license_spdx_id || "未声明"} · 创建于 {formatDate(repository.github_created_at)}</span>
        <span>数据来自本地历史采集，不会自动刷新 GitHub 仓库详情。</span>
      </div>
    </div>
  );
}
