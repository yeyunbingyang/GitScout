import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Layers3, Search, Trophy } from "lucide-react";
import ProjectRankBadge from "../components/ProjectRankBadge";
import RepositoryIdentity from "../components/RepositoryIdentity";
import { api, type Repository } from "../services/api";
export default function RepositoriesPage() {
  const [items, setItems] = useState<Repository[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.repositories().then((result) => { setItems(result.items); setTotal(result.pagination.total); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "读取项目失败"))
      .finally(() => setLoading(false));
  }, []);
  const languages = useMemo(() => Array.from(new Set(items.map((item) => item.language).filter((value): value is string => Boolean(value)))).sort(), [items]);
  const rankedItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesQuery = !normalized || (item.full_name + " " + (item.description ?? "")).toLowerCase().includes(normalized);
      return matchesQuery && (!language || item.language === language);
    }).sort((left, right) => right.stars_count - left.stars_count);
  }, [items, query, language]);
  const topItems = rankedItems.slice(0, 3);
  const previewItems = rankedItems.slice(3, 6).length ? rankedItems.slice(3, 6) : rankedItems.slice(0, 3);
  return <div className="page-stack repository-library-page"><div className="repository-library-layout">
    <div className="repository-library-main">
      <div className="section-heading"><div><h3>项目库</h3><p>所有来源统一关联到 GitHub 仓库主档，避免重复建档。</p></div><span className="count-chip">{total.toLocaleString("zh-CN")} 个项目</span></div>
      <section className="surface-card repository-library-filters">
        <label className="repository-library-search"><Search size={15}/><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="搜索仓库名称 / 描述 / 作者…"/></label>
        <select aria-label="按语言筛选" value={language} onChange={(event)=>setLanguage(event.target.value)}><option value="">全部语言</option>{languages.map((value)=><option value={value} key={value}>{value}</option>)}</select>
      </section>
      {error && <div className="alert alert-error">{error}</div>}
      <section className="surface-card table-card repository-library-table-card">
        {loading ? <div className="empty-state">正在读取 SQLite 项目数据…</div> : rankedItems.length===0 ? <div className="empty-state"><span className="empty-icon"><Search size={24}/></span><strong>{items.length?"没有符合条件的项目":"项目库暂时为空"}</strong><p>{items.length?"尝试调整搜索关键词或语言筛选。":"完成第一轮 GitHub 采集后，项目会自动进入统一项目库。"}</p></div> : (
          <div className="table-scroll"><table className="repository-library-table"><thead><tr><th>本页排名</th><th>项目</th><th>主要语言</th><th>Stars</th><th>Forks</th><th>最近同步</th><th/></tr></thead><tbody>
            {rankedItems.map((item,index)=><tr key={item.id}><td><span className="rank-number">{index+1}</span></td>
              <td><RepositoryIdentity fullName={item.full_name} owner={item.owner} name={item.name} description={item.description||"暂无项目简介"} to={"/repositories/"+item.id} variant="table"/></td>
              <td>{item.language||"—"}</td><td className="number-cell">{item.stars_count.toLocaleString("zh-CN")}</td><td className="number-cell">{item.forks_count.toLocaleString("zh-CN")}</td>
              <td>{item.last_synced_at?new Date(item.last_synced_at).toLocaleDateString("zh-CN"):"—"}</td><td><a href={item.html_url} target="_blank" rel="noreferrer" aria-label="打开 GitHub" className="repo-external-link"><ExternalLink size={14}/></a></td></tr>)}
          </tbody></table></div>
        )}
        {!loading&&rankedItems.length>0&&<div className="table-pagination"><span>当前展示本地已加载的 {rankedItems.length} 项 · 项目库总计 {total} 项</span></div>}
      </section>
    </div>
    <aside className="repository-library-rail">
      <section className="surface-card repository-rail-card"><div className="repository-rail-heading"><span className="repository-rail-icon"><Trophy size={16}/></span><div><h3>Stars 排名</h3><p>当前已加载项目的本地排序</p></div><span>TOP 3</span></div>
        {loading?<div className="repository-empty-note">正在计算排名…</div>:topItems.length?<div className="repository-ranking-list">{topItems.map((item,index)=><div className="repository-ranking-row" key={item.id}><ProjectRankBadge rank={index+1}/><RepositoryIdentity fullName={item.full_name} owner={item.owner} name={item.name} to={"/repositories/"+item.id} variant="compact"/><strong>#{index+1}</strong></div>)}</div>:<div className="repository-empty-note">暂无可展示的项目排名</div>}
      </section>
      <section className="surface-card repository-rail-card repository-name-preview-card"><div className="repository-rail-heading"><span className="repository-rail-icon"><Layers3 size={16}/></span><div><h3>项目名称展示</h3><p>Owner / Repository / Description</p></div><span>STYLE</span></div>
        {loading?<div className="repository-empty-note">正在读取项目…</div>:previewItems.length?<div className="repository-preview-list">{previewItems.map((item)=><RepositoryIdentity key={item.id} fullName={item.full_name} owner={item.owner} name={item.name} description={item.description||"暂无项目简介"} to={"/repositories/"+item.id} variant="card"/>)}</div>:<div className="repository-empty-note">筛选后暂无可展示项目</div>}
      </section>
    </aside>
  </div></div>;
}
