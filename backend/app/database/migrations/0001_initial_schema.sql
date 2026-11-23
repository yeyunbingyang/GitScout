-- GitScout initial relational schema.
-- All timestamps are stored as ISO-8601 UTC strings.

CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_repo_id INTEGER UNIQUE,
    full_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    html_url TEXT NOT NULL,
    language TEXT,
    license_spdx_id TEXT,
    stars_count INTEGER NOT NULL DEFAULT 0 CHECK (stars_count >= 0),
    forks_count INTEGER NOT NULL DEFAULT 0 CHECK (forks_count >= 0),
    open_issues_count INTEGER NOT NULL DEFAULT 0 CHECK (open_issues_count >= 0),
    github_created_at TEXT,
    github_updated_at TEXT,
    pushed_at TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS repository_topics (
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    topic TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (repository_id, topic)
);

CREATE TABLE IF NOT EXISTS repository_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    captured_at TEXT NOT NULL,
    source TEXT NOT NULL,
    stars_count INTEGER NOT NULL CHECK (stars_count >= 0),
    forks_count INTEGER NOT NULL CHECK (forks_count >= 0),
    open_issues_count INTEGER NOT NULL DEFAULT 0 CHECK (open_issues_count >= 0),
    UNIQUE (repository_id, captured_at, source)
);

CREATE TABLE IF NOT EXISTS trending_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_type TEXT NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
    period_key TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial_success', 'failed')),
    source_url TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    error_summary TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS trending_snapshot_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES trending_snapshots(id) ON DELETE CASCADE,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    rank INTEGER NOT NULL CHECK (rank > 0),
    stars_count INTEGER NOT NULL DEFAULT 0 CHECK (stars_count >= 0),
    stars_delta INTEGER NOT NULL DEFAULT 0,
    forks_count INTEGER NOT NULL DEFAULT 0 CHECK (forks_count >= 0),
    UNIQUE (snapshot_id, repository_id),
    UNIQUE (snapshot_id, rank)
);

CREATE TABLE IF NOT EXISTS stars_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('manual', 'scheduled', 'startup')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'partial_success', 'failed', 'interrupted')),
    query_plan TEXT,
    incomplete_results INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_results IN (0, 1)),
    total_count INTEGER NOT NULL DEFAULT 0,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    deduplicated_count INTEGER NOT NULL DEFAULT 0,
    coverage_description TEXT,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS stars_scan_shards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES stars_scans(id) ON DELETE CASCADE,
    shard_key TEXT NOT NULL,
    query_text TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'partial_success', 'failed')),
    total_count INTEGER NOT NULL DEFAULT 0,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    incomplete_results INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_results IN (0, 1)),
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    UNIQUE (scan_id, shard_key)
);

CREATE TABLE IF NOT EXISTS stars_scan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES stars_scans(id) ON DELETE CASCADE,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    rank INTEGER NOT NULL CHECK (rank > 0),
    stars_count INTEGER NOT NULL CHECK (stars_count >= 0),
    forks_count INTEGER NOT NULL DEFAULT 0 CHECK (forks_count >= 0),
    language TEXT,
    UNIQUE (scan_id, repository_id),
    UNIQUE (scan_id, rank)
);

CREATE TABLE IF NOT EXISTS recommendation_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    stars_weight REAL NOT NULL CHECK (stars_weight >= 0 AND stars_weight <= 1),
    daily_weight REAL NOT NULL CHECK (daily_weight >= 0 AND daily_weight <= 1),
    weekly_weight REAL NOT NULL CHECK (weekly_weight >= 0 AND weekly_weight <= 1),
    monthly_weight REAL NOT NULL CHECK (monthly_weight >= 0 AND monthly_weight <= 1),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (abs(stars_weight + daily_weight + weekly_weight + monthly_weight - 1.0) < 0.000001)
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES recommendation_profiles(id) ON DELETE SET NULL,
    algorithm_version TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    window_config_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    data_cutoff_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS recommendation_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES recommendation_runs(id) ON DELETE CASCADE,
    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    stars_score REAL,
    daily_score REAL,
    weekly_score REAL,
    monthly_score REAL,
    total_score REAL NOT NULL,
    rank INTEGER NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    sample_coverage_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (run_id, repository_id),
    UNIQUE (run_id, rank)
);

CREATE TABLE IF NOT EXISTS interested_projects (
    repository_id INTEGER PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
    marked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    source_page TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS research_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL UNIQUE REFERENCES repositories(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'paused')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
    research_goal TEXT,
    next_action TEXT,
    conclusion TEXT,
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    research_project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    note_type TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS research_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    color TEXT
);

CREATE TABLE IF NOT EXISTS research_project_tags (
    research_project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES research_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (research_project_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collection_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    interval_seconds INTEGER,
    cron_expression TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    next_run_at TEXT,
    last_run_at TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('manual', 'scheduled', 'startup')),
    schedule_id INTEGER REFERENCES collection_schedules(id) ON DELETE SET NULL,
    idempotency_key TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'partial_success', 'failed', 'cancelled', 'interrupted')),
    progress REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    started_at TEXT,
    finished_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    deduplicated_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    related_snapshot_id INTEGER REFERENCES trending_snapshots(id) ON DELETE SET NULL,
    related_stars_scan_id INTEGER REFERENCES stars_scans(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS collection_job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES collection_jobs(id) ON DELETE CASCADE,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_repositories_stars ON repositories(stars_count DESC);
CREATE INDEX IF NOT EXISTS idx_repositories_language ON repositories(language);
CREATE INDEX IF NOT EXISTS idx_trending_snapshots_period_time ON trending_snapshots(period_type, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_trending_items_snapshot_rank ON trending_snapshot_items(snapshot_id, rank);
CREATE INDEX IF NOT EXISTS idx_trending_items_repo_snapshot ON trending_snapshot_items(repository_id, snapshot_id);
CREATE INDEX IF NOT EXISTS idx_stars_scans_time_status ON stars_scans(started_at DESC, status);
CREATE INDEX IF NOT EXISTS idx_stars_items_scan_rank ON stars_scan_items(scan_id, rank);
CREATE INDEX IF NOT EXISTS idx_collection_jobs_status_time ON collection_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_logs_job_time ON collection_job_logs(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_research_projects_status_priority ON research_projects(status, priority, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_notes_project_time ON research_notes(research_project_id, updated_at DESC);
