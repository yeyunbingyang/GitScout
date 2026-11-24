-- M6: indexes for the interest library and research workspace.
CREATE INDEX IF NOT EXISTS idx_interested_projects_marked
ON interested_projects(marked_at DESC, repository_id);

CREATE INDEX IF NOT EXISTS idx_research_projects_status_updated
ON research_projects(status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_research_projects_priority_updated
ON research_projects(priority, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_research_notes_project_updated
ON research_notes(research_project_id, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_research_project_tags_tag
ON research_project_tags(tag_id, research_project_id);
