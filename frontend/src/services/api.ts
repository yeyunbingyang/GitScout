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
  retry_of_job_id?: string | null;
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
