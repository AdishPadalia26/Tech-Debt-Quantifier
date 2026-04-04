export interface AnalyzeRequest {
  github_url: string;
  repo_id: string;
}

export interface AnalyzeResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface DebtItem {
  file: string;
  function: string;
  category: string;
  severity: string;
  complexity?: number;
  cost_usd: number;
  adjusted_minutes: number;
  churn_multiplier: number;
  hourly_rate: number;
}

export interface CostByCategory {
  cost_usd: number;
  hours: number;
  item_count: number;
}

export interface RepoProfile {
  tech_stack: {
    primary_language: string;
    frameworks: string[];
    ai_ml_libraries: string[];
    databases: string[];
    has_tests: boolean;
    has_ci_cd: boolean;
  };
  team: {
    estimated_team_size: number;
    bus_factor: number;
    repo_age_days: number;
    active_contributors: number;
  };
  multipliers: {
    combined_multiplier: number;
    bus_factor_multiplier: number;
    repo_age_multiplier: number;
    ai_code_multiplier: number;
  };
  ai_detection: {
    total_suspected: number;
    suspected_files: Array<{ file: string; probability: number }>;
  };
}

export interface DebtReport {
  job_id?: string;
  status?: string;
  scan_id?: string;
  repo_path?: string;
  analysis_timestamp?: string;
  total_cost_usd?: number;
  total_remediation_hours?: number;
  total_remediation_sprints?: number;
  debt_score?: number;
  cost_by_category?: Record<string, CostByCategory>;
  debt_items?: DebtItem[];
  repo_profile?: RepoProfile;
  sanity_check?: {
    your_cost_per_function: number;
    industry_avg: number;
    variance_pct: number;
    is_reasonable: boolean;
    assessment: string;
  };
  executive_summary?: string;
  priority_actions?: PriorityAction[];
  roi_analysis?: ROIAnalysis;
  data_sources_used?: string[];
  hourly_rates?: {
    blended_rate: number;
    confidence: string;
  };
  raw_analysis?: DebtReport;
  raw?: any;
}

export interface PriorityAction {
  rank: number;
  title: string;
  file_or_module: string;
  why: string;
  estimated_hours: number;
  estimated_cost: number;
  saves_per_month: number;
  sprint: string;
}

export interface ROIAnalysis {
  total_fix_cost: number;
  annual_maintenance_savings: number;
  payback_months: number;
  "3_year_roi_pct": number;
  recommended_budget: number;
  recommendation: string;
}

export interface JobResult {
  job_id: string;
  status: "queued" | "running" | "complete" | "failed";
  scan_id?: string;
  error?: string;
  // Flat keys (normalized response)
  debt_score?: number;
  total_cost_usd?: number;
  total_remediation_hours?: number;
  total_remediation_sprints?: number;
  cost_by_category?: Record<string, CostByCategory>;
  debt_items?: DebtItem[];
  executive_summary?: string;
  priority_actions?: PriorityAction[];
  roi_analysis?: ROIAnalysis;
  sanity_check?: DebtReport['sanity_check'];
  hourly_rates?: DebtReport['hourly_rates'];
  repo_profile?: RepoProfile;
  data_sources_used?: string[];
  // Nested for backward compat
  raw_analysis?: DebtReport;
  raw?: any;
}

// ─── History & Trend Types ───────────────────────────────────

export interface ScanSummary {
  scan_id: string;
  date: string;
  date_display: string;
  total_cost: number;
  debt_score: number;
  total_hours: number;
  executive_summary?: string;
  cost_by_category?: Record<string, CostByCategory>;
}

export interface TrendPoint {
  date: string;
  date_display: string;
  total_cost: number;
  debt_score: number;
  scan_id: string;
}

export interface TrendData {
  trend: TrendPoint[];
  change_pct: number;
  direction: "up" | "down" | "stable";
  total_scans: number;
  first_scan_cost: number;
  latest_cost: number;
}

export interface RepoHistory {
  github_url: string;
  scans: ScanSummary[];
  trend: TrendData;
  total_scans: number;
}

export interface RepositorySummary {
  github_url: string;
  repo_name: string;
  repo_owner: string;
  last_scanned: string | null;
  latest_cost: number | null;
  latest_score: number | null;
  total_scans: number;
  language: string | null;
}
