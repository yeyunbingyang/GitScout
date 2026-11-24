import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, BookOpen, Check, ExternalLink, FileText, Filter,
  Lightbulb, Plus, Save, Search, Tag, Trash2, X,
} from "lucide-react";
import {
  api,
  type ResearchNote,
  type ResearchProject,
  type ResearchProjectDetail,
  type ResearchPriority,
  type ResearchStatus,
  type Repository,
} from "../services/api";

const statusOptions: { value: ResearchStatus; label: string }[] = [
  { value: "pending", label: "待研究" },
  { value: "in_progress", label: "研究中" },
  { value: "completed", label: "已完成" },
  { value: "paused", label: "暂缓" },
];

const priorityOptions: { value: ResearchPriority; label: string }[] = [
  { value: "high", label: "高优先级" },
  { value: "medium", label: "中优先级" },
  { value: "low", label: "低优先级" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(/[,，;；\n]/).map((tag) => tag.trim()).filter(Boolean)));
}

function statusLabel(value: ResearchStatus): string {
  return statusOptions.find((item) => item.value === value)?.label ?? value;
}

function priorityLabel(value: ResearchPriority): string {
  return priorityOptions.find((item) => item.value === value)?.label ?? value;
}

export default function ResearchPage() {
  const [items, setItems] = useState<ResearchProject[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ResearchStatus | "all">("all");
  const [priorityFilter, setPriorityFilter] = useState<ResearchPriority | "all">("all");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ResearchProjectDetail | null>(null);
  const [draft, setDraft] = useState({
    status: "pending" as ResearchStatus,
    priority: "medium" as ResearchPriority,
    research_goal: "",
    next_action: "",
    conclusion: "",
  });
  const [tagsDraft, setTagsDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingTags, setSavingTags] = useState(false);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [noteTitleDraft, setNoteTitleDraft] = useState("");
  const [noteContentDraft, setNoteContentDraft] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [pickerItems, setPickerItems] = useState<Repository[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [addingRepositoryId, setAddingRepositoryId] = useState<number | null>(null);

  async function loadItems() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.researchProjects({
        q: query.trim(),
        status: statusFilter === "all" ? undefined : statusFilter,
        priority: priorityFilter === "all" ? undefined : priorityFilter,
        page,
        pageSize: 30,
      });
      setItems(response.items);
      setTotal(response.pagination.total);
      if (selectedId === null && response.items.length > 0) setSelectedId(response.items[0].id);
      if (selectedId !== null && !response.items.some((item) => item.id === selectedId) && response.items.length > 0) {
        setSelectedId(response.items[0].id);
      }
      if (response.items.length === 0) {
        setSelectedId(null);
        setDetail(null);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取研究工作区失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadItems(); }, [query, statusFilter, priorityFilter, page]);

  async function loadDetail(researchId: number) {
    setDetailLoading(true);
    try {
      const response = await api.researchProject(researchId);
      setDetail(response.item);
      setDraft({
        status: response.item.status,
        priority: response.item.priority,
        research_goal: response.item.research_goal ?? "",
        next_action: response.item.next_action ?? "",
        conclusion: response.item.conclusion ?? "",
      });
      setTagsDraft(response.item.tags.map((item) => item.name).join(", "));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取研究详情失败");
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    if (selectedId !== null) void loadDetail(selectedId);
  }, [selectedId]);

  async function saveProject() {
    if (!detail) return;
    setSaving(true);
    setError(null);
    try {
      const response = await api.updateResearchProject(detail.id, {
        ...draft,
        research_goal: draft.research_goal.trim() || null,
        next_action: draft.next_action.trim() || null,
        conclusion: draft.conclusion.trim() || null,
      });
      setDetail(response.item);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存研究信息失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveTags() {
    if (!detail) return;
    setSavingTags(true);
    try {
      const response = await api.setResearchTags(detail.id, parseTags(tagsDraft));
      setDetail(response.item);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存研究标签失败");
    } finally {
      setSavingTags(false);
    }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !noteContent.trim()) return;
    setAddingNote(true);
    try {
      await api.createResearchNote(detail.id, {
        title: noteTitle.trim(),
        content: noteContent.trim(),
      });
      setNoteTitle("");
      setNoteContent("");
      await loadDetail(detail.id);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "添加研究笔记失败");
    } finally {
      setAddingNote(false);
    }
  }

  function beginEditNote(note: ResearchNote) {
    setEditingNoteId(note.id);
    setNoteTitleDraft(note.title);
    setNoteContentDraft(note.content);
  }

  async function saveNote(noteId: number) {
    if (!detail || !noteContentDraft.trim()) return;
    setSavingNote(true);
    try {
      await api.updateResearchNote(detail.id, noteId, {
        title: noteTitleDraft.trim(),
        content: noteContentDraft.trim(),
      });
      setEditingNoteId(null);
      await loadDetail(detail.id);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存笔记失败");
    } finally {
      setSavingNote(false);
    }
  }

  async function removeNote(noteId: number) {
    if (!detail || !window.confirm("删除这条研究笔记？")) return;
    try {
      await api.deleteResearchNote(detail.id, noteId);
      await loadDetail(detail.id);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除笔记失败");
    }
  }

  async function removeResearch() {
    if (!detail || !window.confirm("从研究工作区移除此项目？感兴趣标记和项目主档不会删除。")) return;
    try {
      await api.deleteResearchProject(detail.id);
      setDetail(null);
      setSelectedId(null);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "移除研究项目失败");
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

  async function addResearch(repository: Repository) {
    setAddingRepositoryId(repository.id);
    setError(null);
    try {
      const response = await api.createResearchProject({
        repository_id: repository.id,
        priority: "medium",
      });
      setPickerOpen(false);
      setSelectedId(response.item.id);
      setPage(1);
      await loadItems();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入研究工作区失败");
    } finally {
      setAddingRepositoryId(null);
    }
  }

  const selectedListItem = items.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="page-stack workspace-page">
      <section className="surface-card workspace-intro research-intro">
        <div className="workspace-intro-icon"><Lightbulb size={22} /></div>
        <div>
          <span className="eyebrow">RESEARCH DESK · NOTES · DECISIONS</span>
          <h2>把关注转化为持续、可回顾的研究。</h2>
          <p>独立管理研究状态、优先级、目标、下一步行动、结论和笔记。取消感兴趣标记不会影响这里的研究记录。</p>
        </div>
        <button className="button button-primary" onClick={() => { setPickerOpen(true); setPickerItems([]); setPickerQuery(""); }}>
          <Plus size={14} />加入研究
        </button>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="research-workspace-layout">
        <section className="surface-card research-list-panel">
          <div className="research-list-heading">
            <div><h3>研究项目</h3><p>{total.toLocaleString("zh-CN")} 个项目</p></div>
            <span className="count-chip">{total}</span>
          </div>
          <div className="research-list-filters">
            <label className="workspace-search"><Search size={13} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索项目或研究目标…" /></label>
            <div className="research-filter-pair">
              <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as typeof statusFilter); setPage(1); }}>
                <option value="all">全部状态</option>
                {statusOptions.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
              <select value={priorityFilter} onChange={(event) => { setPriorityFilter(event.target.value as typeof priorityFilter); setPage(1); }}>
                <option value="all">全部优先级</option>
                {priorityOptions.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
            </div>
          </div>

          {loading ? <div className="analytics-empty">正在读取研究项目…</div> : items.length === 0 ? (
            <div className="workspace-empty compact">
              <BookOpen size={25} /><strong>研究工作区还是空的</strong>
              <p>从项目库或智能推荐中选择一个项目开始研究。</p>
              <button className="button button-primary" onClick={() => setPickerOpen(true)}><Plus size={13} />添加研究项目</button>
            </div>
          ) : (
            <div className="research-project-list">
              {items.map((item) => (
                <button key={item.id} className={"research-project-row" + (selectedId === item.id ? " active" : "")}
                  onClick={() => setSelectedId(item.id)}>
                  <span className={"research-status-dot status-" + item.status} />
                  <span className="research-project-row-copy">
                    <strong>{item.full_name}</strong>
                    <small>{item.research_goal || item.description || "尚未填写研究目标"}</small>
                    <span className="research-project-row-meta">
                      <i className={"research-priority priority-" + item.priority}>{priorityLabel(item.priority)}</i>
                      <i>{statusLabel(item.status)}</i>
                      <i><FileText size={10} />{item.notes_count} 条笔记</i>
                    </span>
                  </span>
                  <ArrowRight size={13} />
                </button>
              ))}
            </div>
          )}
          <div className="research-list-footer">
            <span>第 {page} 页 · 共 {total} 项</span>
            <div>
              <button className="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
              <button className="button" disabled={page * 30 >= total || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
            </div>
          </div>
        </section>

        <section className="surface-card research-detail-panel">
          {detailLoading ? <div className="analytics-empty">正在读取研究详情…</div> : !detail ? (
            <div className="workspace-empty"><BookOpen size={27} /><strong>选择一个研究项目</strong><p>从左侧列表选择项目，编辑研究目标、记录笔记和维护结论。</p></div>
          ) : (
            <>
              <div className="research-detail-heading">
                <div>
                  <span className="eyebrow">RESEARCH #{detail.id}</span>
                  <h2>{detail.repository.full_name}</h2>
                  <p>{detail.repository.description || "暂无项目简介"}</p>
                </div>
                <div className="research-detail-heading-actions">
                  <a className="button button-quiet" href={detail.repository.html_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />GitHub</a>
                  <Link className="button button-quiet" to={"/repositories/" + detail.repository.id}>项目详情</Link>
                </div>
              </div>

              <div className="research-detail-meta">
                <span>加入于 {formatDate(detail.added_at)}</span>
                <span>最近更新 {formatDate(detail.updated_at)}</span>
                {detail.started_at && <span>开始于 {formatDate(detail.started_at)}</span>}
                {detail.completed_at && <span>完成于 {formatDate(detail.completed_at)}</span>}
              </div>

              <div className="research-form-grid">
                <label><span>研究状态</span><select value={draft.status} onChange={(event) => setDraft((value) => ({ ...value, status: event.target.value as ResearchStatus }))}>
                  {statusOptions.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
                </select></label>
                <label><span>优先级</span><select value={draft.priority} onChange={(event) => setDraft((value) => ({ ...value, priority: event.target.value as ResearchPriority }))}>
                  {priorityOptions.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
                </select></label>
                <label className="wide"><span>研究目标</span><textarea rows={2} value={draft.research_goal} onChange={(event) => setDraft((value) => ({ ...value, research_goal: event.target.value }))} placeholder="希望通过研究弄清楚什么？" /></label>
                <label className="wide"><span>下一步行动</span><textarea rows={2} value={draft.next_action} onChange={(event) => setDraft((value) => ({ ...value, next_action: event.target.value }))} placeholder="下一次打开这个项目时要做什么？" /></label>
                <label className="wide"><span>研究结论</span><textarea rows={3} value={draft.conclusion} onChange={(event) => setDraft((value) => ({ ...value, conclusion: event.target.value }))} placeholder="记录最终结论、适用场景和限制…" /></label>
              </div>
              <div className="research-detail-actions">
                <button className="button button-primary" disabled={saving} onClick={() => void saveProject()}><Save size={13} />{saving ? "保存中…" : "保存研究信息"}</button>
                <button className="button button-danger-quiet" onClick={() => void removeResearch()}><Trash2 size={13} />移出研究工作区</button>
              </div>

              <div className="research-section-divider" />
              <section className="research-tags-section">
                <div className="research-subheading"><div><h3><Tag size={13} />研究标签</h3><p>标签用于研究项目的分类与筛选</p></div></div>
                <div className="research-tag-editor">
                  <input value={tagsDraft} onChange={(event) => setTagsDraft(event.target.value)} placeholder="架构, AI, 可复用工具（逗号分隔）" />
                  <button className="button button-quiet" disabled={savingTags} onClick={() => void saveTags()}>{savingTags ? "保存中…" : "保存标签"}</button>
                </div>
                {detail.tags.length > 0 && <div className="workspace-tags">{detail.tags.map((item) => <span key={item.id}>{item.name}</span>)}</div>}
              </section>

              <div className="research-section-divider" />
              <section className="research-notes-section">
                <div className="research-subheading"><div><h3><FileText size={13} />研究笔记</h3><p>{detail.notes.length} 条记录 · 按最近修改排序</p></div></div>
                <form className="research-note-form" onSubmit={(event) => void addNote(event)}>
                  <input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} placeholder="笔记标题（可选）" />
                  <textarea rows={3} value={noteContent} onChange={(event) => setNoteContent(event.target.value)} placeholder="记录关键发现、技术细节、疑问或待验证假设…" required />
                  <div><button className="button button-primary" type="submit" disabled={addingNote || !noteContent.trim()}><Plus size={13} />{addingNote ? "保存中…" : "添加笔记"}</button></div>
                </form>
                {detail.notes.length > 0 ? (
                  <div className="research-note-list">
                    {detail.notes.map((note) => (
                      <article className="research-note-item" key={note.id}>
                        {editingNoteId === note.id ? (
                          <div className="research-note-edit">
                            <input value={noteTitleDraft} onChange={(event) => setNoteTitleDraft(event.target.value)} placeholder="笔记标题" />
                            <textarea rows={4} value={noteContentDraft} onChange={(event) => setNoteContentDraft(event.target.value)} />
                            <div><button className="button button-primary" disabled={savingNote} onClick={() => void saveNote(note.id)}><Check size={12} />保存</button><button className="button button-quiet" onClick={() => setEditingNoteId(null)}>取消</button></div>
                          </div>
                        ) : (
                          <>
                            <div className="research-note-heading"><strong>{note.title || "未命名笔记"}</strong><span>{formatDate(note.updated_at)}</span></div>
                            <p>{note.content}</p>
                            <div className="research-note-actions"><span>{note.note_type}</span><button onClick={() => beginEditNote(note)}>编辑</button><button onClick={() => void removeNote(note.id)}>删除</button></div>
                          </>
                        )}
                      </article>
                    ))}
                  </div>
                ) : <div className="research-note-empty">还没有研究笔记。可以先记录一个问题或初步发现。</div>}
              </section>
            </>
          )}
        </section>
      </div>

      {pickerOpen && (
        <div className="workspace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPickerOpen(false); }}>
          <section className="workspace-modal" role="dialog" aria-modal="true" aria-labelledby="research-picker-title">
            <div className="workspace-modal-heading">
              <div><span className="eyebrow">START A RESEARCH</span><h3 id="research-picker-title">选择要研究的项目</h3><p>加入研究不会自动标记为感兴趣。</p></div>
              <button className="icon-button" onClick={() => setPickerOpen(false)} aria-label="关闭"><X size={17} /></button>
            </div>
            <form className="workspace-picker-search" onSubmit={searchPicker}>
              <label><Search size={14} /><input value={pickerQuery} onChange={(event) => setPickerQuery(event.target.value)} placeholder="输入 owner/repo 或项目关键词…" autoFocus /></label>
              <button className="button button-primary" type="submit" disabled={pickerLoading}>{pickerLoading ? "搜索中…" : "搜索项目"}</button>
            </form>
            <div className="workspace-picker-results">
              {pickerItems.map((repository) => (
                <div className="workspace-picker-item" key={repository.id}>
                  <div><Link to={"/repositories/" + repository.id} onClick={() => setPickerOpen(false)}>{repository.full_name}</Link><small>{repository.description || "暂无项目简介"} · {repository.language || "未知语言"}</small></div>
                  <button className="button button-quiet" disabled={addingRepositoryId === repository.id} onClick={() => void addResearch(repository)}>
                    <Plus size={12} />{addingRepositoryId === repository.id ? "加入中…" : "加入研究"}
                  </button>
                </div>
              ))}
              {!pickerLoading && pickerItems.length === 0 && <div className="analytics-empty">搜索本地项目库中的仓库后，在这里加入研究。</div>}
            </div>
            <div className="workspace-modal-footer"><span>同一仓库只能有一条研究主记录，可随时修改状态。</span><button className="button button-quiet" onClick={() => setPickerOpen(false)}>完成</button></div>
          </section>
        </div>
      )}
    </div>
  );
}
