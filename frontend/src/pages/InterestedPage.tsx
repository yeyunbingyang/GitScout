import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Bookmark, Check, ExternalLink, Filter, Pencil, Plus, Search,
  Star, Trash2, X,
} from "lucide-react";
import {
  api,
  type InterestedProject,
  type Repository,
} from "../services/api";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(/[,，;；\n]/).map((tag) => tag.trim()).filter(Boolean)));
}

export default function InterestedPage() {
  const [items, setItems] = useState<InterestedProject[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState<"marked_at" | "stars" | "name">("marked_at");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tagDraft, setTagDraft] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [pickerItems, setPickerItems] = useState<Repository[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [addingId, setAddingId] = useState<number | null>(null);

  async function loadItems() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.interestedProjects({
        q: query.trim(),
        language: language.trim(),
        tag: tag.trim(),
        sort,
        page,
        pageSize: 30,
      });
      setItems(response.items);
      setTotal(response.pagination.total);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取感兴趣项目失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadItems(); }, [query, language, tag, sort, page]);

  const markedIds = useMemo(() => new Set(items.map((item) => item.id)), [items]);

  function beginEdit(item: InterestedProject) {
    setEditingId(item.repository_id);
    setTagDraft(item.tags.join(", "));
    setNotesDraft(item.notes ?? "");
  }

  async function saveEdit(repositoryId: number) {
    setSavingId(repositoryId);
    setError(null);
    try {
      await api.updateInterested(repositoryId, {
        tags: parseTags(tagDraft),
        notes: notesDraft,
      });
      setEditingId(null);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存兴趣记录失败");
    } finally {
      setSavingId(null);
    }
  }

  async function remove(item: InterestedProject) {
    if (!window.confirm("取消感兴趣标记？这不会删除该项目的研究记录。")) return;
    setSavingId(item.repository_id);
    try {
      await api.removeInterested(item.repository_id);
      if (editingId === item.repository_id) setEditingId(null);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "取消标记失败");
    } finally {
      setSavingId(null);
    }
  }

  async function searchPicker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPickerLoading(true);
    try {
      const response = await api.searchRepositories(pickerQuery.trim());
      setPickerItems(response.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "搜索项目库失败");
    } finally {
      setPickerLoading(false);
    }
  }

  async function addInterest(repository: Repository) {
    setAddingId(repository.id);
    try {
      await api.markInterested({ repository_id: repository.id, source_page: "interested_workspace" });
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "添加感兴趣项目失败");
    } finally {
      setAddingId(null);
    }
  }

  return (
    <div className="page-stack workspace-page">
      <section className="surface-card workspace-intro">
        <div className="workspace-intro-icon"><Bookmark size={22} /></div>
        <div>
          <span className="eyebrow">PERSONAL LIBRARY · SAVE FOR LATER</span>
          <h2>把值得继续关注的项目收进来。</h2>
          <p>这里是轻量兴趣清单。添加到感兴趣项目不会自动创建研究任务；标签和备注只用于快速回顾。</p>
        </div>
        <button className="button button-primary" onClick={() => { setPickerOpen(true); setPickerItems([]); setPickerQuery(""); }}>
          <Plus size={14} />从项目库添加
        </button>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="surface-card workspace-filter-card">
        <form className="workspace-filter-form" onSubmit={(event) => { event.preventDefault(); setPage(1); void loadItems(); }}>
          <label className="workspace-search"><Search size={14} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索仓库名称或简介…" /></label>
          <label><span>语言</span><input value={language} onChange={(event) => { setLanguage(event.target.value); setPage(1); }} placeholder="Python" /></label>
          <label><span>标签</span><input value={tag} onChange={(event) => { setTag(event.target.value); setPage(1); }} placeholder="AI" /></label>
          <label><span>排序</span><select value={sort} onChange={(event) => { setSort(event.target.value as typeof sort); setPage(1); }}>
            <option value="marked_at">最近标记</option><option value="stars">Stars 最高</option><option value="name">名称</option>
          </select></label>
          <button className="button button-filter" type="submit"><Filter size={13} />筛选</button>
        </form>
      </section>

      <div className="workspace-list-heading">
        <div><h3>我的感兴趣项目</h3><p>共 {total.toLocaleString("zh-CN")} 个项目 · 与研究工作区独立</p></div>
        <span className="count-chip">{total} 项</span>
      </div>

      <section className="surface-card workspace-list-card">
        {loading ? <div className="analytics-empty">正在读取兴趣清单…</div> : items.length === 0 ? (
          <div className="workspace-empty">
            <Bookmark size={27} />
            <strong>这里还没有感兴趣项目</strong>
            <p>从项目库、推荐结果或项目详情中标记项目，它们会集中出现在这里。</p>
            <button className="button button-primary" onClick={() => setPickerOpen(true)}><Plus size={13} />添加第一个项目</button>
          </div>
        ) : (
          <div className="workspace-project-list">
            {items.map((item) => (
              <article className="workspace-project-item" key={item.repository_id}>
                <div className="workspace-project-main">
                  <div className="workspace-project-title">
                    <Link className="repo-link" to={"/repositories/" + item.repository_id}>{item.full_name}</Link>
                    <span className="workspace-language">{item.language || "未知语言"}</span>
                  </div>
                  <p>{item.description || "暂无项目简介"}</p>
                  <div className="workspace-project-meta">
                    <span><Star size={12} />{item.stars_count.toLocaleString("zh-CN")} Stars</span>
                    <span>标记于 {formatDate(item.marked_at)}</span>
                    {item.source_page && <span>来源：{item.source_page}</span>}
                  </div>
                  {item.tags.length > 0 && <div className="workspace-tags">{item.tags.map((value) => <span key={value}>{value}</span>)}</div>}
                  {item.notes && editingId !== item.repository_id && <div className="workspace-note-preview">{item.notes}</div>}
                </div>
                <div className="workspace-project-actions">
                  <button className="button button-quiet" onClick={() => editingId === item.repository_id ? setEditingId(null) : beginEdit(item)}>
                    <Pencil size={13} />{editingId === item.repository_id ? "收起" : "编辑"}
                  </button>
                  <a className="button button-quiet" href={item.html_url} target="_blank" rel="noreferrer" aria-label="打开 GitHub"><ExternalLink size={13} /></a>
                  <button className="button button-danger-quiet" disabled={savingId === item.repository_id} onClick={() => void remove(item)}><Trash2 size={13} />取消标记</button>
                </div>
                {editingId === item.repository_id && (
                  <div className="workspace-inline-editor">
                    <label><span>标签（逗号分隔）</span><input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} placeholder="AI, 工具, 待评估" /></label>
                    <label><span>备注</span><textarea rows={3} value={notesDraft} onChange={(event) => setNotesDraft(event.target.value)} placeholder="记录为什么关注这个项目…" /></label>
                    <div className="workspace-editor-actions">
                      <button className="button button-primary" disabled={savingId === item.repository_id} onClick={() => void saveEdit(item.repository_id)}><Check size={13} />{savingId === item.repository_id ? "保存中…" : "保存修改"}</button>
                      <button className="button button-quiet" onClick={() => setEditingId(null)}>取消</button>
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
        <div className="table-pagination">
          <span>第 {page} 页 · 共 {total} 个项目</span>
          <div>
            <button className="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
            <button className="button" disabled={page * 30 >= total || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
          </div>
        </div>
      </section>

      {pickerOpen && (
        <div className="workspace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPickerOpen(false); }}>
          <section className="workspace-modal" role="dialog" aria-modal="true" aria-labelledby="interested-picker-title">
            <div className="workspace-modal-heading">
              <div><span className="eyebrow">ADD TO PERSONAL LIBRARY</span><h3 id="interested-picker-title">从已收录项目中添加</h3><p>只添加兴趣标记，不会自动加入研究工作区。</p></div>
              <button className="icon-button" onClick={() => setPickerOpen(false)} aria-label="关闭"><X size={17} /></button>
            </div>
            <form className="workspace-picker-search" onSubmit={searchPicker}>
              <label><Search size={14} /><input value={pickerQuery} onChange={(event) => setPickerQuery(event.target.value)} placeholder="输入 owner/repo 或项目关键词…" autoFocus /></label>
              <button className="button button-primary" type="submit" disabled={pickerLoading}>{pickerLoading ? "搜索中…" : "搜索项目"}</button>
            </form>
            <div className="workspace-picker-results">
              {pickerItems.map((repository) => {
                const alreadyMarked = markedIds.has(repository.id);
                return (
                  <div className="workspace-picker-item" key={repository.id}>
                    <div><Link to={"/repositories/" + repository.id} onClick={() => setPickerOpen(false)}>{repository.full_name}</Link><small>{repository.description || "暂无项目简介"} · {repository.language || "未知语言"}</small></div>
                    <button className="button button-quiet" disabled={alreadyMarked || addingId === repository.id} onClick={() => void addInterest(repository)}>
                      {alreadyMarked ? <><Check size={12} />已标记</> : <><Plus size={12} />{addingId === repository.id ? "添加中…" : "添加"}</>}
                    </button>
                  </div>
                );
              })}
              {!pickerLoading && pickerItems.length === 0 && <div className="analytics-empty">搜索项目库中的仓库后，在这里添加兴趣标记。</div>}
            </div>
            <div className="workspace-modal-footer"><span>项目必须先存在于本地项目库。</span><button className="button button-quiet" onClick={() => setPickerOpen(false)}>完成</button></div>
          </section>
        </div>
      )}
    </div>
  );
}
