-- M2: one schedule per Trending period.
CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_schedules_job_type
ON collection_schedules(job_type);
