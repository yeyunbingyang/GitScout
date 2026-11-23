-- M2: preserve retry lineage for collection jobs.
ALTER TABLE collection_jobs
ADD COLUMN retry_of_job_id TEXT REFERENCES collection_jobs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_collection_jobs_retry_of
ON collection_jobs(retry_of_job_id);
