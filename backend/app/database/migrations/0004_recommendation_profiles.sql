-- M5: seed the versioned recommendation weight profiles and query indexes.
INSERT OR IGNORE INTO recommendation_profiles (
    name, description, stars_weight, daily_weight, weekly_weight, monthly_weight, is_default
) VALUES
(
    '综合平衡（默认）',
    '兼顾长期影响力、短期热度、中期持续性与长期趋势。',
    0.30, 0.15, 0.30, 0.25, 1
),
(
    '趋势发现优先',
    '更关注近期快速上升和中期持续出现的新项目。',
    0.20, 0.25, 0.35, 0.20, 0
),
(
    '长期价值优先',
    '更重视累计关注度和长期稳定趋势。',
    0.40, 0.10, 0.25, 0.25, 0
);

UPDATE recommendation_profiles SET is_default = 0;
UPDATE recommendation_profiles SET is_default = 1 WHERE name = '综合平衡（默认）';

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_created
ON recommendation_runs(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_scores_run_rank
ON recommendation_scores(run_id, rank);

CREATE INDEX IF NOT EXISTS idx_recommendation_scores_repository
ON recommendation_scores(repository_id, run_id);
