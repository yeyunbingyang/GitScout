import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity, BarChart3, Bookmark, Boxes, CircleHelp, Clock3, Compass,
  Github, Layers3, Lightbulb, Settings2, Sparkles,
} from "lucide-react";
import DashboardPage from "./pages/DashboardPage";
import RepositoriesPage from "./pages/RepositoriesPage";
import TrendingPage from "./pages/TrendingPage";
import CollectionJobsPage from "./pages/CollectionJobsPage";
import CollectionSettingsPage from "./pages/CollectionSettingsPage";
import StarsPage from "./pages/StarsPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import { api, type HealthResponse } from "./services/api";

const navigation = [
  { to: "/", label: "趋势总览", icon: Compass, end: true },
  { to: "/trending", label: "周期榜单", icon: Activity },
  { to: "/stars", label: "Stars 总榜", icon: BarChart3 },
  { to: "/recommendations", label: "智能推荐", icon: Sparkles },
  { to: "/compare", label: "周期趋势对比", icon: Layers3 },
  { to: "/interested", label: "感兴趣项目", icon: Bookmark },
  { to: "/research", label: "项目研究", icon: Lightbulb },
  { to: "/repositories", label: "项目库", icon: Boxes },
  { to: "/collections", label: "采集记录", icon: Clock3 },
  { to: "/settings", label: "采集设置", icon: Settings2 },
];

const pageMeta: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "趋势总览", subtitle: "开源项目发现与研究工作台" },
  "/trending": { title: "周期榜单", subtitle: "在同一入口切换日榜、周榜和月榜" },
  "/stars": { title: "Stars 总榜", subtitle: "独立采集 GitHub 当前 Stars 排名" },
  "/recommendations": { title: "智能推荐", subtitle: "基于 Stars 与日周月上榜表现计算推荐分" },
  "/compare": { title: "周期趋势对比", subtitle: "追踪项目在不同周期的排名变化" },
  "/interested": { title: "感兴趣项目", subtitle: "保存值得持续关注的项目" },
  "/research": { title: "项目研究", subtitle: "管理研究状态、目标、笔记与结论" },
  "/repositories": { title: "项目库", subtitle: "统一管理所有发现过的 GitHub 仓库" },
  "/collections": { title: "采集记录", subtitle: "查看采集任务、执行状态与运行日志" },
  "/settings": { title: "采集设置", subtitle: "配置采集频率、数据保存和本地运行" },
};

function AppShell() {
  const location = useLocation();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [apiError, setApiError] = useState(false);
  const meta = pageMeta[location.pathname] ?? pageMeta["/"];

  useEffect(() => {
    let active = true;
    const check = () => api.health()
      .then((result) => { if (active) { setHealth(result); setApiError(false); } })
      .catch(() => { if (active) setApiError(true); });
    void check();
    const timer = window.setInterval(check, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-symbol"><Github size={21} /></div>
          <div><strong>GitScout</strong><span>开源项目发现与研究平台</span></div>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="main-nav">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card"><span className="local-indicator" /><div><strong>本地工作台</strong><small>数据保存在当前设备</small></div></div>
          <a className="help-link" href="https://github.com/yeyunbingyang/GitScout" target="_blank" rel="noreferrer"><CircleHelp size={15} /> 项目仓库 <span>↗</span></a>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div><span className="breadcrumb">GitScout</span><span className="breadcrumb-separator">/</span><strong>{meta.title}</strong></div>
          <div className="topbar-right">
            <span className={apiError ? "connection-state offline" : "connection-state"}>
              <i />{apiError ? "后端未连接" : health ? "本地服务已连接" : "正在连接"}
            </span>
            <span className="version-tag">STARS LEADERBOARD · 0.3.0</span>
          </div>
        </header>
        <div className="page-header"><div><h1>{meta.title}</h1><p>{meta.subtitle}</p></div></div>
        <div className="page-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/repositories" element={<RepositoriesPage />} />
            <Route path="/trending" element={<TrendingPage />} />
            <Route path="/stars" element={<PlaceholderPage title="Stars 实时总榜" description="独立于 Trending 的 Stars 排名采集。将显示扫描时间、结果覆盖范围、分片状态和排名快照。" milestone="M3 · STARS LEADERBOARD" />} />
            <Route path="/recommendations" element={<PlaceholderPage title="综合推荐评分" description="按 Stars 30%、日榜 15%、周榜 30%、月榜 25% 的默认权重计算推荐分，并保留每次计算批次。" milestone="M5 · RECOMMENDATION ENGINE" />} />
            <Route path="/compare" element={<PlaceholderPage title="跨周期排名矩阵" description="选择历史快照，对比项目新增、掉榜和排名变化。" milestone="M4 · TREND ANALYTICS" />} />
            <Route path="/interested" element={<PlaceholderPage title="感兴趣项目库" description="轻量保存感兴趣项目；该标记与加入项目研究相互独立。" milestone="M6 · RESEARCH WORKSPACE" />} />
            <Route path="/research" element={<PlaceholderPage title="项目研究工作区" description="管理待研究、研究中、已完成和暂缓项目，记录目标、笔记、下一步行动与结论。" milestone="M6 · RESEARCH WORKSPACE" />} />
            <Route path="/collections" element={<CollectionJobsPage />} />
            <Route path="/settings" element={<CollectionSettingsPage />} />
          </Routes>
        </div>
        <footer className="app-footer"><span>GitScout · Discover · Track · Recommend · Research</span><span>本地数据优先 · SQLite</span></footer>
      </main>
    </div>
  );
}

export default function App() {
  return <AppShell />;
}
