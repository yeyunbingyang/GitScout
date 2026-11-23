import { useEffect, useState } from "react";
import { ExternalLink, Search } from "lucide-react";
import { api, type Repository } from "../services/api";

export default function RepositoriesPage() {
  const [items, setItems] = useState<Repository[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.repositories()
      .then((result) => {
        setItems(result.items);
        setTotal(result.pagination.total);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "读取项目失败"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page-stack">
      <div className="section-heading">
        <div><h3>项目库</h3><p>所有来源统一关联到 GitHub 仓库主档，避免重复建档。</p></div>
        <span className="count-chip">{total} 个项目</span>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <section className="surface-card table-card">
        {loading ? <div className="empty-state">正在读取 SQLite 项目数据…</div> : items.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon"><Search size={24} /></span>
            <strong>项目库暂时为空</strong>
            <p>完成第一轮 GitHub 采集后，项目会自动进入统一项目库。</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>项目</th><th>主要语言</th><th>Stars</th><th>Forks</th><th>最近同步</th><th /></tr></thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.full_name}</strong><small>{item.description || "暂无项目简介"}</small></td>
                    <td>{item.language || "—"}</td>
                    <td>{item.stars_count.toLocaleString()}</td>
                    <td>{item.forks_count.toLocaleString()}</td>
                    <td>{item.last_synced_at ? new Date(item.last_synced_at).toLocaleDateString() : "—"}</td>
                    <td><a href={item.html_url} target="_blank" rel="noreferrer" aria-label="打开 GitHub"><ExternalLink size={15} /></a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
