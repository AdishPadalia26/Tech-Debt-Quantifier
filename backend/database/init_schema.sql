-- Initial schema for Tech Debt Quantifier
-- Run this after starting PostgreSQL via docker-compose

CREATE TABLE IF NOT EXISTS repositories (
    id VARCHAR PRIMARY KEY,
    github_url VARCHAR UNIQUE NOT NULL,
    repo_name VARCHAR NOT NULL,
    repo_owner VARCHAR NOT NULL,
    primary_language VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_scanned_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_repositories_github_url ON repositories(github_url);

CREATE TABLE IF NOT EXISTS scans (
    id VARCHAR PRIMARY KEY,
    repository_id VARCHAR NOT NULL REFERENCES repositories(id),
    job_id VARCHAR UNIQUE,

    -- Core metrics
    total_cost_usd FLOAT NOT NULL DEFAULT 0,
    debt_score FLOAT NOT NULL DEFAULT 0,
    total_hours FLOAT DEFAULT 0,
    total_sprints FLOAT DEFAULT 0,

    -- Category breakdown
    cost_by_category JSONB,

    -- Rate info
    hourly_rate FLOAT,
    rate_confidence VARCHAR,

    -- Repo profile snapshot
    team_size INTEGER,
    bus_factor INTEGER,
    repo_age_days INTEGER,
    combined_multiplier FLOAT,
    primary_language VARCHAR,
    frameworks JSONB,

    -- LLM outputs
    executive_summary TEXT,
    priority_actions JSONB,
    roi_analysis JSONB,

    -- Full raw result
    raw_result JSONB,

    -- Metadata
    status VARCHAR DEFAULT 'complete',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    scan_duration_seconds FLOAT
);

CREATE INDEX IF NOT EXISTS ix_scans_repository_id ON scans(repository_id);
CREATE INDEX IF NOT EXISTS ix_scans_job_id ON scans(job_id);
CREATE INDEX IF NOT EXISTS ix_scans_created_at ON scans(created_at);
CREATE INDEX IF NOT EXISTS ix_scans_repo_created ON scans(repository_id, created_at);

CREATE TABLE IF NOT EXISTS debt_items (
    id VARCHAR PRIMARY KEY,
    scan_id VARCHAR NOT NULL REFERENCES scans(id) ON DELETE CASCADE,

    -- Item details
    file_path VARCHAR,
    function_name VARCHAR,
    category VARCHAR,
    severity VARCHAR,

    -- Metrics
    cost_usd FLOAT,
    hours FLOAT,
    complexity INTEGER,
    churn_multiplier FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_debt_items_scan_id ON debt_items(scan_id);
CREATE INDEX IF NOT EXISTS ix_debt_items_file_path ON debt_items(file_path);
CREATE INDEX IF NOT EXISTS ix_debt_items_category ON debt_items(category);
