import axios from 'axios';
import {
  AnalyzeResponse,
  GitHubImportResponse,
  GitHubOrg,
  GitHubRepo,
  JobResult,
  RepoHistory,
  RepositorySummary,
  RepoSummaryRollup,
  RichRepoTrend,
  ScanComparisonResponse,
  ScanDetailResponse,
  ScanFindingsResponse,
  ScanModulesResponse,
  ScanRoadmapResponse,
  ScanSummaryResponse,
  UnresolvedFindingsResponse,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const MAX_POLL_ATTEMPTS = 120;
const INITIAL_POLL_DELAY_MS = 1500;
const MAX_POLL_DELAY_MS = 7000;
export const AUTH_CHANGED_EVENT = 'tdq-auth-changed';

function notifyAuthChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  }
}

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
  withCredentials: true,
});

export type CurrentUser = {
  id: number;
  login: string;
  name?: string;
  avatar_url?: string;
  html_url?: string;
};

export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    const { data } = await api.get<CurrentUser>('/auth/me');
    return data;
  } catch {
    return null;
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post('/auth/logout');
  } catch {
    // best effort
  }
  notifyAuthChanged();
}

export async function startAnalysis(
  github_url: string
): Promise<AnalyzeResponse> {
  const parts = github_url.replace(/\/$/, '').split('/');
  const repo_id = parts.slice(-2).join('/') || parts.pop() || 'repo';
  const { data } = await api.post<AnalyzeResponse>('/analyze', {
    github_url,
    repo_id,
  });
  return data;
}

export async function getResults(job_id: string): Promise<JobResult> {
  const { data } = await api.get<JobResult>(`/results/${job_id}`);
  const analysis = (data?.raw_analysis ?? {}) as Record<string, unknown>;
  const safeNum = (value: unknown, fallback = 0): number =>
    typeof value === 'number' && Number.isFinite(value) ? value : fallback;

  return {
    ...data,
    raw_analysis: {
      ...analysis,
      debt_score: safeNum(analysis.debt_score),
      total_cost_usd: safeNum(analysis.total_cost_usd),
      total_remediation_hours: safeNum(analysis.total_remediation_hours),
      total_remediation_sprints: safeNum(analysis.total_remediation_sprints),
      debt_items: Array.isArray(analysis.debt_items) ? analysis.debt_items : [],
      cost_by_category:
        analysis.cost_by_category && typeof analysis.cost_by_category === 'object'
          ? analysis.cost_by_category
          : {},
    } as JobResult['raw_analysis'],
    priority_actions: Array.isArray(data.priority_actions)
      ? data.priority_actions.filter(
          (action): action is NonNullable<typeof action> =>
            Boolean(action) && typeof action === 'object' && !('error' in action)
        )
      : [],
    roi_analysis:
      data.roi_analysis && typeof data.roi_analysis === 'object'
        ? data.roi_analysis
        : undefined,
  };
}

export async function getStatus(job_id: string): Promise<{
  job_id: string;
  status: string;
  progress?: number;
  phase?: string;
  error?: string;
}> {
  const { data } = await api.get(`/status/${job_id}`);
  return data;
}

export async function pollResults(
  job_id: string,
  onUpdate: (result: JobResult) => void,
): Promise<JobResult> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let delay = INITIAL_POLL_DELAY_MS;

    const poll = async () => {
      if (attempts >= MAX_POLL_ATTEMPTS) {
        reject(new Error('Analysis timed out. The repository may be too large.'));
        return;
      }
      attempts += 1;

      try {
        const status = await getStatus(job_id);
        onUpdate({
          job_id,
          status: status.status as JobResult['status'],
          error: status.error,
          progress: status.progress,
          phase: status.phase,
        });

        if (status.status === 'complete') {
          resolve(await getResults(job_id));
          return;
        }

        if (status.status === 'error' || status.status === 'failed') {
          reject(new Error(status.error || 'Analysis failed. Please try again.'));
          return;
        }

        setTimeout(() => { void poll(); }, delay);
        delay = Math.min(delay * 1.4, MAX_POLL_DELAY_MS);
      } catch (err) {
        const isAxiosError =
          typeof err === 'object' &&
          err !== null &&
          'response' in err &&
          typeof (err as { response?: { status?: number } }).response?.status === 'number';
        const statusCode = isAxiosError
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;

        if (statusCode === 404) {
          reject(new Error('Job not found. Please try again.'));
          return;
        }

        if (attempts >= 10) {
          reject(new Error('Lost connection to server. Please refresh and try again.'));
          return;
        }

        setTimeout(() => { void poll(); }, Math.min(delay * 3, MAX_POLL_DELAY_MS));
      }
    };

    void poll();
  });
}

export async function getRepoHistory(
  github_url: string
): Promise<RepoHistory> {
  const urlPath = github_url.replace(/^https?:\/\//, '');
  const { data } = await api.get<RepoHistory>(`/history/${urlPath}`);
  return data;
}

export async function getRepoHistoryRich(
  github_url: string
): Promise<RichRepoTrend> {
  const urlPath = github_url.replace(/^https?:\/\//, '');
  const { data } = await api.get<RichRepoTrend>(`/history/${urlPath}/rich`);
  return data;
}

export async function getRepositorySummary(
  github_url: string
): Promise<RepoSummaryRollup> {
  const urlPath = github_url.replace(/^https?:\/\//, '');
  const { data } = await api.get<RepoSummaryRollup>(
    `/repositories/${urlPath}/summary`
  );
  return data;
}

export async function getRepositoryUnresolved(
  github_url: string,
  limit: number = 8
): Promise<UnresolvedFindingsResponse> {
  const urlPath = github_url.replace(/^https?:\/\//, '');
  const { data } = await api.get<UnresolvedFindingsResponse>(
    `/repositories/${urlPath}/unresolved`,
    { params: { limit } }
  );
  return data;
}

export async function getScanModules(
  scanId: string
): Promise<ScanModulesResponse> {
  const { data } = await api.get<ScanModulesResponse>(`/scan/${scanId}/modules`);
  return data;
}

export async function getScanDetail(
  scanId: string
): Promise<ScanDetailResponse> {
  const { data } = await api.get<ScanDetailResponse>(`/scan/${scanId}`);
  return data;
}

export async function getScanSummary(
  scanId: string
): Promise<ScanSummaryResponse> {
  const { data } = await api.get<ScanSummaryResponse>(`/scan/${scanId}/summary`);
  return data;
}

export async function getScanRoadmap(
  scanId: string
): Promise<ScanRoadmapResponse> {
  const { data } = await api.get<ScanRoadmapResponse>(`/scan/${scanId}/roadmap`);
  return data;
}

export async function getScanFindings(
  scanId: string,
  limit: number = 8
): Promise<ScanFindingsResponse> {
  const { data } = await api.get<ScanFindingsResponse>(`/scan/${scanId}/findings`, {
    params: { limit, offset: 0 },
  });
  return data;
}

export async function getScanComparison(
  baseScanId: string,
  targetScanId: string
): Promise<ScanComparisonResponse> {
  const { data } = await api.get<ScanComparisonResponse>('/scan/compare', {
    params: {
      base_scan_id: baseScanId,
      target_scan_id: targetScanId,
    },
  });
  return data;
}

export async function getAllRepositories(): Promise<{
  repositories: RepositorySummary[];
  total: number;
}> {
  const { data } = await api.get('/repositories');
  return data;
}

export async function getGitHubRepos(): Promise<{
  repositories: GitHubRepo[];
  total: number;
}> {
  const { data } = await api.get('/github/repos');
  return data;
}

export async function getGitHubOrgs(): Promise<{
  organizations: GitHubOrg[];
  total: number;
}> {
  const { data } = await api.get('/github/orgs');
  return data;
}

export async function getGitHubOrgRepos(org: string): Promise<{
  organization: string;
  repositories: GitHubRepo[];
  total: number;
}> {
  const { data } = await api.get(`/github/orgs/${org}/repos`);
  return data;
}

export async function importGitHubRepo(
  github_url: string
): Promise<GitHubImportResponse> {
  const { data } = await api.post<GitHubImportResponse>('/github/import', {
    github_url,
  });
  return data;
}

export async function getDebugResults(job_id: string): Promise<unknown> {
  const { data } = await api.get(`/debug/results/${job_id}`);
  return data;
}

export async function listJobs(): Promise<unknown> {
  const { data } = await api.get('/jobs');
  return data;
}
