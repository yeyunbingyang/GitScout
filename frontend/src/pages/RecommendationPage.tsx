import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, ArrowDown, ArrowUp, Award, Clock3, Database,
  Download, Filter, History, RefreshCw, Search, Sparkles, Star,
  TrendingUp,
} from "lucide-react";
import RepositoryWorkspaceActions from "../components/RepositoryWorkspaceActions";
import {
  api,
  type RecommendationCategory,
  type RecommendationDimension,
  type RecommendationItem,
  type RecommendationProfile,
  type RecommendationRunHistoryItem,
  type RecommendationRunResponse,
} from "../services/api";

const categories: { value: RecommendationCategory; label: string }[] = [
  { value: "all", label: "全部推荐" },
  { value: "priority", label: "优先关注" },
  { value: "emerging", label: "新兴潜力" },
  { value: "stable", label: "长期稳定" },
];

const dimensions = [
  { key: "stars_score", weightKey: "stars", label: "Stars", short: "S" },
  { key: "daily_score", weightKey: "daily", label: "日榜", short: "D" },
  { key: "weekly_score", weightKey: "weekly", label: "周榜", short: "W" },
  { key: "monthly_score", weightKey: "monthly", label: "月榜", short: "M" },
] as const;

function number(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function date(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function score(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(1);
}

function statusLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    success: "完整成功",
    partial_success: "部分成功",
    failed: "失败",
    running: "运行中",
    queued: "排队中",
    interrupted: "中断",
  };
  return value ? labels[value] ?? value : "尚无采集";
}

function runOption(run: RecommendationRunHistoryItem): string {
  const profile = run.profile_name || "未知方案";
  return "#" + run.id + " · " + profile + " · " + date(run.created_at);
}

function gradeClass(grade: RecommendationItem["grade"]): string {
  return "recommendation-grade recommendation-grade-" + grade;
}

function dimensionCount(item: RecommendationItem, key: "daily" | "weekly" | "monthly"): string {
  const period = item.coverage.periods[key];
  return period.appearance_count + "/" + period.sample_count;
}

function buildCsv(items: RecommendationItem[]): string {
  const header = [
    "排名", "仓库", "综合分", "推荐等级", "Stars得分", "日榜得分",
    "周榜得分", "月榜得分", "Stars数量", "日榜出现次数", "周榜出现次数",
    "月榜出现次数", "推荐理由", "GitHub URL",
  ];
  const rows = items.map((item) => [
    item.rank,
    item.full_name,
    item.total_score.toFixed(1),
    item.grade_label,
    score(item.stars_score),
    score(item.daily_score),
    score(item.weekly_score),
    score(item.monthly_score),
    item.stars_count,
    dimensionCount(item, "daily"),
    dimensionCount(item, "weekly"),
    dimensionCount(item, "monthly"),
    item.reasons.join("；"),
    item.html_url,
  ]);
  const escape = (value: string | number) => '"' + String(value).replace(/"/g, '""') + '"';
  return "\uFEFF" + [header, ...rows].map((row) => row.map(escape).join(",")).join("\r\n");
}

export default function RecommendationPage() {
  const [profiles, setProfiles] = useState<RecommendationProfile[]>([]);
  const [history, setHistory] = useState<RecommendationRunHistoryItem[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [result, setResult] = useState<RecommendationRunResponse | null>(null);
  const [category, setCategory] = useState<RecommendationCategory>("all");
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [appliedLanguage, setAppliedLanguage] = useState("");
  const [dimension, setDimension] = useState<RecommendationDimension>("all");
  const [page, setPage] = useState(1);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.recommendationProfiles(),
      api.recommendationRuns(1),
      api.latestRecommendationRun(),
    ])
      .then(([profileResponse, historyResponse, latest]) => {
        if (!active) return;
        setProfiles(profileResponse.items);
        setHistory(historyResponse.items);
        if (latest.run) {
          setResult(latest);
          setSelectedRunId(latest.run.id);
          setSelectedProfileId(latest.run.profile_id);
        } else {
          setSelectedProfileId(
            profileResponse.items.find((item) => item.is_default)?.id
              ?? profileResponse.items[0]?.id
              ?? null,
          );
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取推荐配置失败");
      })
      .finally(() => { if (active) setInitialLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (selectedRunId === null || initialLoading) return;
    let active = true;
    setLoading(true);
    setError(null);
    api.recommendationRun(selectedRunId, {
      category,
      q: appliedQuery,
      language: appliedLanguage,
      dimension,
      page,
      pageSize: 50,
    })
      .then((response) => {
        if (!active) return;
        setResult(response);
        if (response.run?.profile_id) setSelectedProfileId(response.run.profile_id);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取推荐结果失败");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedRunId, category, appliedQuery, appliedLanguage, dimension, page, initialLoading]);

  const selectedProfile = useMemo(
    () => profiles.find((item) => item.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );
  const run = result?.run ?? null;
  const summary = result?.summary;
  const pagination = result?.pagination;

  async function calculate() {
    if (selectedProfileId === null) {
      setError("没有可用的权重方案，请先检查推荐配置。");
      return;
    }
    setCalculating(true);
    setError(null);
    try {
      const response = await api.createRecommendationRun(selectedProfileId);
      setResult(response);
      setSelectedRunId(response.run?.id ?? null);
      setCategory("all");
      setAppliedQuery("");
      setQuery("");
      setAppliedLanguage("");
      setLanguage("");
      setDimension("all");
      setPage(1);
      const historyResponse = await api.recommendationRuns(1);
      setHistory(historyResponse.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成推荐结果失败");
    } finally {
      setCalculating(false);
    }
  }

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setAppliedLanguage(language.trim());
    setPage(1);
  }

  async function exportResults() {
    if (!run || !pagination || pagination.total === 0) return;
    setExporting(true);
    setError(null);
    try {
      const allItems: RecommendationItem[] = [];
      for (let currentPage = 1; currentPage <= pagination.total_pages; currentPage += 1) {
        const response = await api.recommendationRun(run.id, {
          category,
          q: appliedQuery,
          language: appliedLanguage,
          dimension,
          page: currentPage,
          pageSize: 100,
        });
        allItems.push(...response.items);
      }
      const blob = new Blob([buildCsv(allItems)], { type: "text/csv;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "gitscout-recommendations-run-" + run.id + ".csv";
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出推荐结果失败");
    } finally {
      setExporting(false);
    }
  }

  const latestStarsScan = summary?.latest_stars_scan;
  const dataWarnings = [
    summary?.stars_stale ? "最近一次完整 Stars 扫描已超过 7 天，或尚无完整 Stars 扫描。" : "",
    summary?.stars_incomplete ? "最近一次 Stars 扫描未完整完成，Stars 候选覆盖可能不完整。" : "",
  ].filter(Boolean);

  return (
    <div className="page-stack">
      <section className="surface-card recommendation-intro">
        <div className="recommendation-intro-copy">
          <span className="eyebrow">DISCOVER · SCORE · EXPLAIN</span>
          <h2>让值得研究的开源项目浮现出来。</h2>
          <p>以 Stars 长期影响力、日榜短期热度、周榜持续性和月榜长期趋势计算综合分。每次计算都会保存独立批次，可回看、可复算、可解释。</p>
          <div className="recommendation-intro-tags">
            <span><Star size={12} />真实采集数据</span>
            <span><History size={12} />历史批次留存</span>
            <span><Database size={12} />本地 SQLite 计算</span>
          </div>
        </div>
        <div className="recommendation-intro-mark"><Sparkles size={34} /></div>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="surface-card recommendation-control-card">
        <div className="recommendation-control-top">
          <div>
            <h3>计算方案</h3>
            <p>切换权重方案不会修改历史批次；点击生成后创建一份新的推荐结果。</p>
          </div>
          <button className="button button-primary" onClick={() => void calculate()}
            disabled={initialLoading || calculating || profiles.length === 0}>
            <RefreshCw size={14} className={calculating ? "spin" : ""} />
            {calculating ? "正在计算…" : "生成推荐"}
          </button>
        </div>
        <div className="recommendation-controls">
          <label>
            <span>权重预设</span>
            <select value={selectedProfileId ?? ""} onChange={(event) => setSelectedProfileId(Number(event.target.value) || null)}
              disabled={initialLoading || profiles.length === 0}>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.name}</option>
              ))}
            </select>
          </label>
          <label>
            <span><History size={12} />历史计算批次</span>
            <select value={selectedRunId ?? ""} onChange={(event) => {
              const nextRunId = Number(event.target.value) || null;
              setSelectedRunId(nextRunId);
              if (nextRunId === null) setResult(null);
              setPage(1);
            }}>
              <option value="">选择历史批次</option>
              {history.map((item) => <option key={item.id} value={item.id}>{runOption(item)}</option>)}
            </select>
          </label>
        </div>
        {selectedProfile && (
          <div className="recommendation-weight-row">
            <div className="recommendation-profile-description">
              <strong>{selectedProfile.name}</strong>
              <span>{selectedProfile.description}</span>
            </div>
            {dimensions.map((dimension) => (
              <div className="recommendation-weight-chip" key={dimension.key}>
                <span>{dimension.label}</span>
                <strong>{selectedProfile.weights_percent[dimension.weightKey]}</strong>
                <small>%</small>
              </div>
            ))}
          </div>
        )}
      </section>

      {initialLoading ? (
        <section className="surface-card analytics-empty">正在读取推荐配置与历史批次…</section>
      ) : !run ? (
        <section className="surface-card recommendation-empty">
          <div className="recommendation-empty-icon"><Award size={27} /></div>
          <h3>还没有推荐计算结果</h3>
          <p>选择一个权重方案，生成第一批推荐。系统将从最近一次成功 Stars 扫描和评分窗口内的日榜、周榜、月榜快照构建候选池。</p>
          <button className="button button-primary" onClick={() => void calculate()} disabled={calculating || profiles.length === 0}>
            <Sparkles size={14} />生成第一批推荐
          </button>
        </section>
      ) : (
        <>
          <section className="recommendation-run-meta">
            <div><span>计算批次</span><strong>#{run.id}</strong></div>
            <div><span>算法版本</span><strong>{run.algorithm_version}</strong></div>
            <div><span>权重方案</span><strong>{run.profile_name || "已删除方案"}</strong></div>
            <div><span>数据截止</span><strong>{date(run.data_cutoff_at)}</strong></div>
            <div><span>候选项目</span><strong>{number(summary?.candidate_count ?? 0)}</strong></div>
          </section>

          {dataWarnings.length > 0 && (
            <div className="recommendation-warning">
              <AlertTriangle size={16} />
              <div>
                <strong>数据覆盖提示</strong>
                {dataWarnings.map((warning) => <span key={warning}>{warning}</span>)}
                {latestStarsScan && (
                  <small>最近 Stars 扫描：{date(latestStarsScan.finished_at)} · {statusLabel(latestStarsScan.status)} · 获取 {number(latestStarsScan.fetched_count)} / {number(latestStarsScan.total_count)} 条</small>
                )}
              </div>
            </div>
          )}

          <section className="recommendation-summary-grid">
            <div className="recommendation-summary-card">
              <span>已评分候选</span><strong>{number(summary?.scored_count ?? 0)}</strong>
              <small>来自 Stars 与日 / 周 / 月榜去重合并</small>
            </div>
            <div className="recommendation-summary-card">
              <span>优先关注</span><strong>{number(summary?.priority_count ?? 0)}</strong>
              <small>综合分 ≥ 85</small>
            </div>
            <div className="recommendation-summary-card">
              <span>新兴潜力</span><strong>{number(summary?.emerging_count ?? 0)}</strong>
              <small>日榜活跃、Stars 尚未进入高位</small>
            </div>
            <div className="recommendation-summary-card">
              <span>长期稳定</span><strong>{number(summary?.stable_count ?? 0)}</strong>
              <small>周榜与月榜表现均较高</small>
            </div>
          </section>

          <section className="surface-card recommendation-source-card">
            <div className="card-heading">
              <div><h3>数据窗口与完整性</h3><p>仅使用成功快照作为上榜比例的有效样本分母</p></div>
              <span className="recommendation-source-badge"><Database size={12} />本地历史数据</span>
            </div>
            <div className="recommendation-window-grid">
              {(["daily", "weekly", "monthly"] as const).map((period) => {
                const window = summary?.data_coverage[period];
                const label = period === "daily" ? "日榜窗口" : period === "weekly" ? "周榜窗口" : "月榜窗口";
                return (
                  <div key={period}>
                    <span>{label}</span>
                    <strong>{window ? number(window.sample_count) + " / " + number(window.window_limit) : "0"}</strong>
                    <small>{window ? "最低需要 " + window.minimum_samples + " 次成功快照" : "暂无成功快照"}</small>
                  </div>
                );
              })}
              <div>
                <span>Stars 总榜</span>
                <strong>{latestStarsScan ? statusLabel(latestStarsScan.status) : "尚未采集"}</strong>
                <small>{latestStarsScan ? date(latestStarsScan.finished_at) : "候选池仍可由 Trending 快照构成"}</small>
              </div>
            </div>
          </section>

          <section className="surface-card recommendation-results-card">
            <div className="recommendation-results-heading">
              <div><h3>推荐项目</h3><p>按未四舍五入的综合分排序；并列时依次比较 Stars 排名和最近上榜时间。</p></div>
              <button className="button button-quiet" onClick={() => void exportResults()}
                disabled={exporting || loading || !pagination || pagination.total === 0}>
                <Download size={13} />{exporting ? "导出中…" : "导出 CSV"}
              </button>
            </div>

            <div className="recommendation-filter-row">
              <div className="recommendation-category-tabs">
                {categories.map((item) => (
                  <button key={item.value} className={category === item.value ? "period-tab active" : "period-tab"}
                    onClick={() => { setCategory(item.value); setPage(1); }}>{item.label}</button>
                ))}
              </div>
              <div className="recommendation-filter-controls">
              <form className="recommendation-search" onSubmit={applySearch}>
                <label><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索仓库名称或简介…" /></label>
                <label className="recommendation-language-input"><input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="语言，如 Python" /></label>
                <button className="button button-filter" type="submit"><Filter size={13} />筛选</button>
              </form>
              <label className="recommendation-dimension-filter">
                <span>主要贡献维度</span>
                <select value={dimension} onChange={(event) => { setDimension(event.target.value as RecommendationDimension); setPage(1); }}>
                  <option value="all">全部维度</option>
                  <option value="stars">Stars</option>
                  <option value="daily">日榜</option>
                  <option value="weekly">周榜</option>
                  <option value="monthly">月榜</option>
                </select>
              </label>
            </div>
            </div>

            {loading ? <div className="analytics-empty">正在读取推荐项目…</div> : result?.items.length ? (
              <div className="table-scroll">
                <table className="recommendation-table">
                  <thead>
                    <tr>
                      <th>排名 / 项目</th><th>综合分</th><th>推荐等级</th>
                      <th>Stars</th><th>日榜</th><th>周榜</th><th>月榜</th><th>推荐理由</th><th>工作区</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((item) => (
                      <tr key={item.repository_id}>
                        <td className="recommendation-project-cell">
                          <span className="recommendation-rank">#{item.rank}</span>
                          <div>
                            <Link className="repo-link" to={"/repositories/" + item.repository_id}>{item.full_name}</Link>
                            <small>{item.description || "暂无项目简介"}</small>
                            <span className="recommendation-project-meta">{item.language || "未知语言"} · {number(item.stars_count)} Stars</span>
                          </div>
                        </td>
                        <td><strong className="recommendation-total-score">{item.total_score.toFixed(1)}</strong></td>
                        <td><span className={gradeClass(item.grade)}>{item.grade_label}</span></td>
                        {dimensions.map((dimension) => {
                          const value = item[dimension.key];
                          const periodKey = dimension.key === "daily_score" ? "daily" : dimension.key === "weekly_score" ? "weekly" : "monthly";
                          const coverage = dimension.key === "stars_score" ? null : item.coverage.periods[periodKey];
                          return (
                            <td key={dimension.key} className="recommendation-score-cell">
                              <strong>{score(value)}</strong>
                              {coverage && <small>{coverage.appearance_count}/{coverage.sample_count}</small>}
                            </td>
                          );
                        })}
                        <td className="recommendation-reasons-cell">
                          {item.reasons.length ? item.reasons.map((reason) => <span key={reason}>{reason}</span>) : <small>暂无理由</small>}
                          {item.coverage.available_dimensions.length < 4 && (
                            <small className="recommendation-na-note">部分指标样本不足，已按可用权重重新归一化</small>
                          )}
                        </td>
                        <td className="recommendation-workspace-cell">
                          <RepositoryWorkspaceActions
                            repositoryId={item.repository_id}
                            interested={item.interested}
                            researchStatus={item.research_status}
                            sourcePage="recommendations"
                            compact
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="analytics-empty">
                {summary?.candidate_count === 0
                  ? "候选池为空。先完成一次 Stars 总榜采集或 Trending 成功采集，再生成推荐。"
                  : "没有符合当前筛选条件的项目。"}
              </div>
            )}

            <div className="table-pagination">
              <span>第 {pagination?.page ?? 1} / {Math.max(pagination?.total_pages ?? 0, 1)} 页 · 共 {number(pagination?.total ?? 0)} 条</span>
              <div>
                <button className="button" disabled={!pagination || page <= 1 || loading}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
                <button className="button" disabled={!pagination || page >= pagination.total_pages || loading}
                  onClick={() => setPage((value) => value + 1)}>下一页</button>
              </div>
            </div>
          </section>

          <div className="recommendation-footnote">
            <span><Clock3 size={12} />计算时间：{date(run.finished_at || run.created_at)}</span>
            <span><TrendingUp size={12} />推荐分仅用于项目发现，不代表项目质量结论。</span>
            <span><ArrowUp size={12} /><ArrowDown size={12} />并列排序规则已固定在算法版本 {run.algorithm_version}。</span>
          </div>
        </>
      )}
    </div>
  );
}
