import { useEffect, useState } from "react";
import { Activity, Bookmark, Database, FolderSearch, RefreshCw } from "lucide-react";
import { api, type DashboardSummary } from "../services/api";

const emptySummary: DashboardSummary = {
  repositories: 0,
  successful_trending_snapshots: 0,
  interested_projects: 0,
  research_projects: 0,
  latest_trending_at: null,
  latest_stars_scan_at: null,
};

function formatDate(value: string | null): string {
  if (!value) return "尚无采集记录";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary>(emptySummary);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadSummary() {
    setLoading(true);
    setError(null);
    try {
      setSummary(await api.dashboardSummary());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取概览数据失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSummary();
  }, []);

  const cards = [
    { label: "收录项目", value: summary.repositories, icon: FolderSearch, hint: "SQLite 项目主档" },
    { label: "成功趋势快照", value: summary.successful_trending_snapshots, icon: Activity, hint: "日 / 周 / 月历史批次" },
    { label: "感兴趣项目", value: summary.interested_projects, icon: Bookmark, hint: "个人关注清单" },
    { label: "研究项目", value: summary.research_projects, icon: Database, hint: "项目研究工作区" },
  ];

  return (
    <div className="page-stack">
      <section className="welcome-panel">
        <div>
          <span className="eyebrow">DISCOVER · TRACK · RESEARCH</span>
          <h2>让值得关注的开源项目，不再错过。</h2>
          <p>从 GitHub 趋势发现项目，持续追踪热度，再进入自己的研究工作区。</p>
        </div>
        <div className="welcome-mark"><Activity size={42} strokeWidth={1.4} /></div>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="section-heading">
        <div>
          <h3>工作台概览</h3>
          <p>当前数据直接读取本机 SQLite 数据库。</p>
        </div>
        <button className="button button-quiet" onClick={() => void loadSummary()} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          刷新数据
        </button>
      </div>

      <section className="stat-grid">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <article className="stat-card" key={card.label}>
              <div className="stat-card-top">
                <span>{card.label}</span>
                <span className="stat-icon"><Icon size={18} /></span>
              </div>
              <strong>{loading ? "—" : card.value.toLocaleString("zh-CN")}</strong>
              <small>{card.hint}</small>
            </article>
          );
        })}
      </section>

      <section className="content-grid">
        <article className="surface-card">
          <div className="card-heading">
            <div><h3>数据采集状态</h3><p>真实采集器将在后续阶段接入。</p></div>
            <span className="status-dot status-idle">等待接入</span>
          </div>
          <div className="data-row"><span>最近 Trending 采集</span><strong>{formatDate(summary.latest_trending_at)}</strong></div>
          <div className="data-row"><span>最近 Stars 总榜采集</span><strong>{formatDate(summary.latest_stars_scan_at)}</strong></div>
        </article>
        <article className="surface-card next-card">
          <span className="eyebrow">NEXT MILESTONE</span>
          <h3>建立真实数据采集链路</h3>
          <p>下一阶段将接入 GitHub Trending 日 / 周 / 月采集器，并保留每次采集的历史快照。</p>
          <div className="progress-track"><span style={{ width: "25%" }} /></div>
          <small>工程骨架与 SQLite 数据底座 · M0 / M1</small>
        </article>
      </section>
    </div>
  );
}
