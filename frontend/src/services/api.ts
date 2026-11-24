export interface HealthResponse {
  status: string;
  service: string;
  database: string;
  schema_version: string | null;
}

export interface DashboardSummary {
  repositories: number;
  successful_trending_snapshots: number;
  interested_projects: number;
  research_projects: number;
  latest_trending_at: string | null;
  latest_stars_scan_at: string | null;
}

export interface Repository {
  id: number;
  github_repo_id: number | null;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  stars_count: number;
  forks_count: number;
  open_issues_count: number;
  last_synced_at: string | null;
}


export interface DashboardAnalytics {
  period_type: TrendingPeriod;
  summary: {
    repositories: number;
    successful_trending_snapshots: number;
    latest_period_items: number;
    new_items_vs_previous: number;
    cross_period_hot_projects: number;
    interested_projects: number;
    research_projects: number;
  };
  period_snapshots: Record<TrendingPeriod, {
    latest: TrendingSnapshot | null;
    previous: TrendingSnapshot | null;
  }>;
  trend_series: {
    id: number;
    period_key: string;
    collected_at: string;
    item_count: number;
    average_stars: number | null;
    total_stars_delta: number;
  }[];
  language_distribution: { name: string; value: number }[];
  topic_distribution: { name: string; value: number }[];
  cross_period_items: {
    repository_id: number;
    full_name: string;
    description: string | null;
    html_url: string;
    language: string | null;
    stars_count: number;
    rank_daily: number | null;
    rank_weekly: number | null;
    rank_monthly: number | null;
    period_count: number;
  }[];
  latest_stars_scan: {
    id: number;
    finished_at: string;
    status: string;
    fetched_count: number;
    total_count: number;
    incomplete_results: boolean | number;
    coverage_description: string | null;
  } | null;
  latest_stars_top: { full_name: string; stars_count: number } | null;
}

export interface RepositoryProfile extends Repository {
  license_spdx_id: string | null;
  github_created_at: string | null;
  github_updated_at: string | null;
  pushed_at: string | null;
  created_at: string;
  updated_at: string;
  topics: string[];
  interested: {
    marked_at: string;
    source_page: string | null;
    tags_json: string;
    tags: string[];
    notes: string | null;
  } | null;
  research: {
    id: number;
    status: "pending" | "in_progress" | "completed" | "paused";
    priority: "high" | "medium" | "low";
    research_goal: string | null;
    next_action: string | null;
    conclusion: string | null;
    added_at: string;
    started_at: string | null;
    completed_at: string | null;
    updated_at: string;
    tags: ResearchTag[];
    notes_count: number;
  } | null;
}


export type ResearchStatus = "pending" | "in_progress" | "completed" | "paused";
export type ResearchPriority = "high" | "medium" | "low";

export interface InterestedProject extends Repository {
  repository_id: number;
  marked_at: string;
  source_page: string | null;
  tags: string[];
  notes: string | null;
  research_status: ResearchStatus | null;
}

export interface ResearchTag {
  id: number;
  name: string;
  color: string | null;
}

export interface ResearchNote {
  id: number;
  title: string;
  content: string;
  note_type: string;
  created_at: string;
  updated_at: string;
}

export interface ResearchProject extends Omit<Repository, "id"> {
  id: number;
  repository_id: number;
  status: ResearchStatus;
  priority: ResearchPriority;
  research_goal: string | null;
  next_action: string | null;
  conclusion: string | null;
  added_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  tags: ResearchTag[];
  notes_count: number;
}

export interface ResearchProjectDetail {
  id: number;
  repository_id: number;
  status: ResearchStatus;
  priority: ResearchPriority;
  research_goal: string | null;
  next_action: string | null;
  conclusion: string | null;
  added_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  repository: Repository;
  tags: ResearchTag[];
  notes: ResearchNote[];
}

export interface RepositoryDetailResponse {
  repository: RepositoryProfile;
  summary: {
    trending_appearances: number;
    stars_scan_observations: number;
    best_rank_by_period: Partial<Record<TrendingPeriod, number>>;
    current_appearance_streak_by_period: Partial<Record<TrendingPeriod, number>>;
    first_observed_stars: number | null;
    latest_observed_stars: number | null;
    observed_stars_growth: number | null;
    first_trending_at: string | null;
    last_trending_at: string | null;
  };
  trending_history: {
    snapshot_id: number;
    period_type: TrendingPeriod;
    period_key: string;
    collected_at: string;
    snapshot_status: string;
    rank: number;
    stars_count: number;
    stars_delta: number;
    forks_count: number;
  }[];
  stars_history: {
    scan_id: number;
    captured_at: string;
    scan_status: string;
    incomplete_results: number;
    rank: number;
    stars_count: number;
    forks_count: number;
  }[];
  stats_history: {
    captured_at: string;
    source: string;
    stars_count: number;
    forks_count: number;
    open_issues_count: number;
  }[];
}

export type ComparisonChangeType = "all" | "new" | "dropped" | "up" | "down" | "unchanged";

export interface TrendingComparisonResponse {
  base_snapshot: TrendingSnapshot;
  target_snapshot: TrendingSnapshot;
  summary: {
    new: number;
    dropped: number;
    up: number;
    down: number;
    unchanged: number;
    total: number;
  };
  items: {
    repository_id: number;
    full_name: string;
    owner: string;
    name: string;
    description: string | null;
    html_url: string;
    language: string | null;
    base_rank: number | null;
    target_rank: number | null;
    rank_change: number | null;
    change_type: Exclude<ComparisonChangeType, "all">;
    stars_count: number;
    stars_delta: number;
    forks_count: number;
  }[];
  pagination: Pagination;
}


export type RecommendationCategory = "all" | "priority" | "emerging" | "stable";
export type RecommendationDimension = "all" | "stars" | "daily" | "weekly" | "monthly";

export interface RecommendationProfile {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  weights: Record<"stars" | TrendingPeriod, number>;
  weights_percent: Record<"stars" | TrendingPeriod, number>;
  created_at: string;
}

export interface RecommendationPeriodCoverage {
  sample_count: number;
  window_limit: number;
  minimum_samples: number;
  appearance_count: number;
  available: boolean;
  score: number | null;
}

export interface RecommendationStarsCoverage {
  rank: number;
  candidate_count: number;
  stars_count: number;
  last_synced_at: string | null;
  scoring_scan_id: number | null;
  scoring_scan_finished_at: string | null;
  latest_scan_id: number | null;
  latest_scan_status: string | null;
  latest_scan_incomplete_results: boolean | null;
  stale: boolean;
  incomplete: boolean;
  age_days: number | null;
  stale_after_days: number;
}

export interface RecommendationCoverage {
  stars: RecommendationStarsCoverage;
  periods: Record<TrendingPeriod, RecommendationPeriodCoverage>;
  last_appearance_at: string | null;
  available_dimensions: string[];
  effective_weight: number;
  weights: Record<"stars" | TrendingPeriod, number>;
}

export interface RecommendationItem {
  repository_id: number;
  github_repo_id: number | null;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  stars_count: number;
  forks_count: number;
  last_synced_at: string | null;
  stars_score: number | null;
  daily_score: number | null;
  weekly_score: number | null;
  monthly_score: number | null;
  total_score: number;
  rank: number;
  grade: "priority" | "strong" | "watch" | "observe" | "low";
  grade_label: string;
  reason_codes: string[];
  reasons: string[];
  coverage: RecommendationCoverage;
  stars_rank: number | null;
  interested: boolean;
  research_status: "pending" | "in_progress" | "completed" | "paused" | null;
  categories: Exclude<RecommendationCategory, "all">[];
}

export interface RecommendationRun {
  id: number;
  profile_id: number | null;
  profile_name: string | null;
  profile_description?: string | null;
  algorithm_version: string;
  weights: Record<"stars" | TrendingPeriod, number>;
  window_config: Record<string, unknown>;
  candidate_count: number;
  data_cutoff_at: string | null;
  status: "running" | "success" | "failed";
  created_at: string;
  finished_at: string | null;
  error_summary: string | null;
}

export interface RecommendationStarsScanSummary {
  id: number;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  incomplete_results: boolean | number;
  total_count: number;
  fetched_count: number;
  deduplicated_count: number;
  coverage_description: string | null;
  error_summary?: string | null;
}

export interface RecommendationRunSummary {
  candidate_count: number;
  scored_count: number;
  priority_count: number;
  emerging_count: number;
  stable_count: number;
  grade_counts: Record<RecommendationItem["grade"], number>;
  latest_stars_scan: RecommendationStarsScanSummary | null;
  scoring_stars_scan: RecommendationStarsScanSummary | null;
  stars_stale: boolean;
  stars_incomplete: boolean;
  stars_stale_after_days: number;
  stars_scan_age_days: number | null;
  data_coverage: Partial<Record<TrendingPeriod, {
    sample_count: number;
    minimum_samples: number;
    window_limit: number;
    latest_snapshot: TrendingSnapshot | null;
  }>>;
  candidate_sources: string[];
}

export interface RecommendationRunResponse {
  run: RecommendationRun | null;
  summary: RecommendationRunSummary;
  items: RecommendationItem[];
  pagination: Pagination;
  filters: {
    category: RecommendationCategory;
    category_label: string;
    query: string;
    language: string;
    dimension: RecommendationDimension;
  };
}

export interface RecommendationRunHistoryItem {
  id: number;
  profile_id: number | null;
  profile_name: string | null;
  algorithm_version: string;
  weights: Record<string, number>;
  candidate_count: number;
  data_cutoff_at: string | null;
  status: "running" | "success" | "failed";
  created_at: string;
  finished_at: string | null;
  error_summary: string | null;
}

export interface RecommendationRunHistoryResponse {
  items: RecommendationRunHistoryItem[];
  pagination: Pagination;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type TrendingPeriod = "daily" | "weekly" | "monthly";

export interface TrendingSnapshot {
  id: number;
  period_type: TrendingPeriod;
  period_key: string;
  collected_at: string;
  status: "success" | "partial_success" | "failed";
  source_url: string;
  item_count: number;
  error_summary: string | null;
}

export interface TrendingItem {
  rank: number;
  repository_id: number;
  github_repo_id: number | null;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  stars_count: number;
  stars_delta: number;
  forks_count: number;
  topics: string[];
  interested: boolean;
  research_status: ResearchStatus | null;
}

export interface TrendingResponse {
  snapshot: TrendingSnapshot | null;
  items: TrendingItem[];
  pagination: Pagination;
}

export interface CollectionJob {
  id: string;
  job_type: string;
  trigger_type: string;
  status: "queued" | "running" | "success" | "partial_success" | "failed" | "cancelled" | "interrupted";
  progress: number;
  started_at: string | null;
  finished_at: string | null;
  retry_count: number;
  request_count: number;
  fetched_count: number;
  inserted_count: number;
  updated_count: number;
  deduplicated_count: number;
  error_code: string | null;
  error_message: string | null;
  related_snapshot_id: number | null;
  related_stars_scan_id: number | null;
  retry_of_job_id: string | null;
  created_at: string;
}


export interface CollectionSchedule {
  id: number;
  name: string;
  job_type: string;
  enabled: boolean;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  settings: {
    time?: string;
    weekday?: number;
    day_of_month?: number;
    max_results?: number;
    min_stars?: number;
    include_forks?: boolean;
  };
}

export interface CollectionJobLog {
  id: number;
  level: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface CollectionJobDetail extends CollectionJob {
  logs: CollectionJobLog[];
  stars_scan?: StarsScanDetail | null;
}


export interface StarsScanPlan {
  max_results: number;
  min_stars: number;
  include_forks: boolean;
  sort: string;
  scope: string;
  per_page: number;
  search_result_limit: number;
}

export interface StarsShard {
  id: number;
  shard_key: string;
  query_text: string;
  status: "queued" | "running" | "success" | "partial_success" | "failed";
  total_count: number;
  fetched_count: number;
  incomplete_results: boolean;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

export interface StarsScan {
  id: number;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  status: "queued" | "running" | "success" | "partial_success" | "failed" | "interrupted";
  incomplete_results: boolean;
  total_count: number;
  fetched_count: number;
  deduplicated_count: number;
  coverage_description: string | null;
  error_summary: string | null;
  query_plan: StarsScanPlan;
}

export interface StarsScanDetail extends StarsScan {
  shards: StarsShard[];
}

export interface StarsLeaderboardItem {
  rank: number;
  repository_id: number;
  github_repo_id: number | null;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  stars_count: number;
  forks_count: number;
  topics: string[];
  interested: boolean;
  research_status: ResearchStatus | null;
}

export interface StarsLeaderboardResponse {
  scan: StarsScan | null;
  items: StarsLeaderboardItem[];
  pagination: Pagination;
}

export interface StarsCollectOptions {
  max_results: number;
  min_stars: number;
  include_forks: boolean;
}


export interface ListResponse<T> {
  items: T[];
  pagination: Pagination;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, { ...init, headers });

  if (!response.ok) {
    const body = await response.text();
    let message = body || "Request failed: " + response.status;
    try {
      const payload = JSON.parse(body) as {
        detail?: string | { message?: string } | unknown;
      };
      if (typeof payload.detail === "string") message = payload.detail;
      else if (payload.detail && typeof payload.detail === "object" && "message" in payload.detail) {
        message = String(payload.detail.message);
      }
    } catch {
      // Keep the raw response body as the most useful error message.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/health"),
  dashboardSummary: () => request<DashboardSummary>("/api/v1/dashboard/summary"),
  dashboardAnalytics: (periodType: TrendingPeriod = "daily") =>
    request<DashboardAnalytics>("/api/v1/dashboard/analytics?period_type=" + periodType),
  repositoryDetail: (repositoryId: number) =>
    request<RepositoryDetailResponse>("/api/v1/repositories/" + repositoryId),

  searchRepositories: (q: string, page = 1) => {
    const params = new URLSearchParams({ q, page: String(page), page_size: "20" });
    return request<ListResponse<Repository>>("/api/v1/repositories?" + params.toString());
  },
  interestedProjects: (filters: {
    q?: string;
    language?: string;
    tag?: string;
    research?: "all" | "added" | "not_added";
    sort?: "marked_at" | "stars" | "name";
    page?: number;
    pageSize?: number;
  } = {}) => {
    const params = new URLSearchParams({
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 30),
      sort: filters.sort ?? "marked_at",
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    if (filters.tag) params.set("tag", filters.tag);
    if (filters.research) params.set("research", filters.research);
    return request<ListResponse<InterestedProject>>("/api/v1/interested?" + params.toString());
  },
  markInterested: (payload: {
    repository_id: number;
    source_page?: string;
    tags?: string[];
    notes?: string | null;
  }) => postJson<{ item: InterestedProject; created: boolean }>("/api/v1/interested", payload),
  updateInterested: (repositoryId: number, payload: {
    source_page?: string | null;
    tags?: string[];
    notes?: string | null;
  }) => request<{ item: InterestedProject }>(
    "/api/v1/interested/" + repositoryId,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
  ),
  removeInterested: (repositoryId: number) =>
    request<{ deleted: boolean; repository_id: number }>(
      "/api/v1/interested/" + repositoryId,
      { method: "DELETE" },
    ),
  researchProjects: (filters: {
    q?: string;
    status?: ResearchStatus;
    priority?: ResearchPriority;
    tag?: string;
    sort?: "updated_at" | "added_at" | "priority";
    page?: number;
    pageSize?: number;
  } = {}) => {
    const params = new URLSearchParams({
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 30),
      sort: filters.sort ?? "updated_at",
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.status) params.set("research_status", filters.status);
    if (filters.priority) params.set("priority", filters.priority);
    if (filters.tag) params.set("tag", filters.tag);
    return request<ListResponse<ResearchProject>>("/api/v1/research?" + params.toString());
  },
  createResearchProject: (payload: {
    repository_id: number;
    status?: ResearchStatus;
    priority?: ResearchPriority;
    research_goal?: string | null;
    next_action?: string | null;
    conclusion?: string | null;
  }) => postJson<{ item: ResearchProjectDetail }>("/api/v1/research", payload),
  researchProject: (researchId: number) =>
    request<{ item: ResearchProjectDetail }>("/api/v1/research/" + researchId),
  updateResearchProject: (researchId: number, payload: {
    status?: ResearchStatus;
    priority?: ResearchPriority;
    research_goal?: string | null;
    next_action?: string | null;
    conclusion?: string | null;
  }) => request<{ item: ResearchProjectDetail }>(
    "/api/v1/research/" + researchId,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
  ),
  deleteResearchProject: (researchId: number) =>
    request<{ deleted: boolean; research_id: number }>(
      "/api/v1/research/" + researchId,
      { method: "DELETE" },
    ),
  setResearchTags: (researchId: number, tags: string[]) =>
    request<{ item: ResearchProjectDetail }>(
      "/api/v1/research/" + researchId + "/tags",
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tags }) },
    ),
  createResearchNote: (researchId: number, payload: {
    title?: string;
    content: string;
    note_type?: string;
  }) => postJson<{ item: ResearchNote }>(
    "/api/v1/research/" + researchId + "/notes",
    payload,
  ),
  updateResearchNote: (researchId: number, noteId: number, payload: {
    title?: string;
    content?: string;
    note_type?: string;
  }) => request<{ item: ResearchNote }>(
    "/api/v1/research/" + researchId + "/notes/" + noteId,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
  ),
  deleteResearchNote: (researchId: number, noteId: number) =>
    request<{ deleted: boolean; note_id: number }>(
      "/api/v1/research/" + researchId + "/notes/" + noteId,
      { method: "DELETE" },
    ),

  compareTrending: (filters: {
    baseSnapshotId: number;
    targetSnapshotId: number;
    changeType?: ComparisonChangeType;
    q?: string;
    language?: string;
    page?: number;
    pageSize?: number;
  }) => {
    const params = new URLSearchParams({
      base_snapshot_id: String(filters.baseSnapshotId),
      target_snapshot_id: String(filters.targetSnapshotId),
      change_type: filters.changeType ?? "all",
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 50),
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    return request<TrendingComparisonResponse>("/api/v1/trending/compare?" + params.toString());
  },

  recommendationProfiles: () =>
    request<{ items: RecommendationProfile[] }>("/api/v1/recommendations/profiles"),
  recommendationRuns: (page = 1) =>
    request<RecommendationRunHistoryResponse>(
      "/api/v1/recommendations/runs?page=" + page + "&page_size=30",
    ),
  createRecommendationRun: (profileId?: number | null) =>
    postJson<RecommendationRunResponse>(
      "/api/v1/recommendations/runs",
      profileId ? { profile_id: profileId } : {},
    ),
  latestRecommendationRun: (filters: {
    category?: RecommendationCategory;
    q?: string;
    language?: string;
    dimension?: RecommendationDimension;
    page?: number;
    pageSize?: number;
  } = {}) => {
    const params = new URLSearchParams({
      category: filters.category ?? "all",
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 50),
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    if (filters.dimension) params.set("dimension", filters.dimension);
    return request<RecommendationRunResponse>(
      "/api/v1/recommendations/runs/latest?" + params.toString(),
    );
  },
  recommendationRun: (
    runId: number,
    filters: {
      category?: RecommendationCategory;
      q?: string;
      language?: string;
      dimension?: RecommendationDimension;
      page?: number;
      pageSize?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      category: filters.category ?? "all",
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 50),
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    if (filters.dimension) params.set("dimension", filters.dimension);
    return request<RecommendationRunResponse>(
      "/api/v1/recommendations/runs/" + runId + "?" + params.toString(),
    );
  },
  repositories: (page = 1) =>
    request<ListResponse<Repository>>("/api/v1/repositories?page=" + page + "&page_size=20"),
  trendingSnapshots: (periodType: TrendingPeriod) =>
    request<ListResponse<TrendingSnapshot>>(
      "/api/v1/trending/snapshots?period_type=" + periodType + "&page_size=50",
    ),
  trending: (
    periodType: TrendingPeriod,
    filters: {
      snapshotId?: number | null;
      q?: string;
      language?: string;
      topic?: string;
      sortBy?: "rank" | "stars" | "delta" | "forks";
      sortOrder?: "asc" | "desc";
      page?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({ period_type: periodType, page: String(filters.page ?? 1) });
    if (filters.snapshotId) params.set("snapshot_id", String(filters.snapshotId));
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    if (filters.topic) params.set("topic", filters.topic);
    if (filters.sortBy) params.set("sort_by", filters.sortBy);
    if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
    return request<TrendingResponse>("/api/v1/trending?" + params.toString());
  },
  collectTrending: (periodType: TrendingPeriod) =>
    postJson<{ job: CollectionJob }>("/api/v1/trending/collect", { period_type: periodType }),
  starsScans: (page = 1) =>
    request<ListResponse<StarsScan>>("/api/v1/stars/scans?page=" + page + "&page_size=30"),
  starsScan: (scanId: number) =>
    request<StarsScanDetail>("/api/v1/stars/scans/" + scanId),
  starsLeaderboard: (filters: { scanId?: number | null; q?: string; language?: string; page?: number } = {}) => {
    const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: "50" });
    if (filters.scanId) params.set("scan_id", String(filters.scanId));
    if (filters.q) params.set("q", filters.q);
    if (filters.language) params.set("language", filters.language);
    return request<StarsLeaderboardResponse>("/api/v1/stars/leaderboard?" + params.toString());
  },
  collectStars: (options: StarsCollectOptions) =>
    postJson<{ job: CollectionJob; scan_id: number }>("/api/v1/stars/collect", options),
  retryStarsScan: (scanId: number) =>
    postJson<{ job: CollectionJob; scan_id: number; retry_of_job_id: string }>(
      "/api/v1/stars/scans/" + scanId + "/retry",
      {},
    ),
  collectionSchedules: () =>
    request<{ items: CollectionSchedule[] }>("/api/v1/collections/schedules"),
  saveCollectionSchedule: (
    periodType: TrendingPeriod,
    payload: { enabled: boolean; time: string; timezone: string; weekday: number; day_of_month: number },
  ) => request<{ schedule: CollectionSchedule }>(
    "/api/v1/collections/schedules/" + periodType,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
  ),
  saveStarsSchedule: (payload: StarsCollectOptions & { enabled: boolean; time: string; timezone: string }) =>
    request<{ schedule: CollectionSchedule }>(
      "/api/v1/collections/schedules/stars",
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    ),
  collectionJobs: (page = 1) =>
    request<ListResponse<CollectionJob>>(
      "/api/v1/collections/jobs?page=" + page + "&page_size=50",
    ),
  collectionJob: (jobId: string) =>
    request<CollectionJobDetail>("/api/v1/collections/jobs/" + encodeURIComponent(jobId)),
  retryCollectionJob: (jobId: string) =>
    postJson<{ job: CollectionJob; retry_of_job_id: string }>(
      "/api/v1/collections/jobs/" + encodeURIComponent(jobId) + "/retry",
      {},
    ),
};
