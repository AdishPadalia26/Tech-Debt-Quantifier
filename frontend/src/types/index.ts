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
  raw?: unknown;
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
  raw?: unknown;
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

export interface StructuredFinding {
  id: string;
  file_path: string;
  module?: string;
  category: string;
  subcategory?: string;
  symbol_name?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  severity: string;
  business_impact?: string;
  effort_hours?: number;
  cost_usd: number;
  confidence?: number;
  status?: string;
  suppressed?: boolean;
}

export interface RepoTriageStats {
  scan_id: string;
  total_findings: number;
  active_findings: number;
  suppressed_findings: number;
  reviewed_findings: number;
  suppression_rate: number;
  review_rate: number;
  by_category: Record<string, number>;
}

export interface RepoChangeGroup {
  count: number;
  cost_usd: number;
  items: StructuredFinding[];
}

export interface SeverityChange {
  id: string;
  file_path?: string;
  from_severity: string;
  to_severity: string;
}

export interface RepoChangeRollup {
  latest_scan_id: string;
  previous_scan_id: string | null;
  summary: {
    cost_delta_usd: number;
    debt_score_delta: number;
    hours_delta: number;
    finding_count_delta: number;
  };
  new_debt: RepoChangeGroup;
  existing_debt: RepoChangeGroup;
  resolved_debt: RepoChangeGroup;
  severity_worsened: SeverityChange[];
  severity_improved: SeverityChange[];
  category_deltas: Record<
    string,
    { new: number; resolved: number; net: number }
  >;
}

export interface ModuleSummaryDetail {
  module: string;
  finding_count: number;
  total_cost_usd: number;
  total_effort_hours: number;
  max_severity: string;
  avg_confidence: number;
}

export interface RepoSummaryRollup {
  scan_id: string;
  github_url: string;
  total_cost_usd: number;
  debt_score: number;
  total_hours: number;
  finding_count: number;
  module_count: number;
  quick_wins: number;
  strategic_items: number;
  triage: RepoTriageStats;
  changes: RepoChangeRollup | null;
  top_modules: ModuleSummaryDetail[];
}

export interface RichRepoTrendPoint {
  scan_id: string;
  date: string;
  date_display: string;
  total_cost_usd: number;
  debt_score: number;
  finding_count: number;
  module_count: number;
  quick_wins: number;
  strategic_items: number;
}

export interface ActiveTrendPoint {
  scan_id: string;
  date: string;
  date_display: string;
  active_finding_count: number;
  active_cost_usd: number;
}

export interface CategoryTrendPoint {
  scan_id: string;
  date: string;
  count: number;
  cost_usd: number;
}

export interface ModuleTrendPoint {
  scan_id: string;
  date: string;
  finding_count: number;
  total_cost_usd: number;
  max_severity: string;
}

export interface RichRepoTrend {
  github_url: string;
  trend: RichRepoTrendPoint[];
  active_trend: ActiveTrendPoint[];
  category_trends: Record<string, CategoryTrendPoint[]>;
  module_trends: Record<string, ModuleTrendPoint[]>;
  category_deltas: Record<string, { count_delta: number; cost_delta_usd: number }>;
  module_deltas: Record<
    string,
    { finding_count_delta: number; cost_delta_usd: number; latest_max_severity: string }
  >;
  total_scans: number;
  latest: RichRepoTrendPoint | null;
  latest_active: ActiveTrendPoint | null;
}

export interface UnresolvedFindingsResponse {
  github_url: string;
  items: StructuredFinding[];
  total: number;
  limit: number;
}
