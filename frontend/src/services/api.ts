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

export interface RepositoryListResponse {
  items: Repository[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed: " + response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/health"),
  dashboardSummary: () => request<DashboardSummary>("/api/v1/dashboard/summary"),
  repositories: (page = 1) =>
    request<RepositoryListResponse>("/api/v1/repositories?page=" + page + "&page_size=20"),
};
