'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { ArrowDown, ArrowUp, ArrowUpDown, Check, FolderGit2, Trash2, X } from 'lucide-react';
import ActiveDebtChart from '@/components/ActiveDebtChart';
import RepositoryInsightsPanel from '@/components/RepositoryInsightsPanel';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import { useRepositoryInsights } from '@/hooks/useRepositoryInsights';
import { repoDetailPath } from '@/lib/routes';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  return fetch(url, { ...options, headers, credentials: 'include' });
}

interface RepoSummary {
  repo_id: string;
  github_url: string;
  scan_count?: number;
  latest_scan_id?: string | null;
  previous_scan_id?: string | null;
  debt_score: number;
  total_cost: number;
  remediation_hours: number;
  language: string;
  team_size: number;
  bus_factor: number;
  has_tests: boolean;
  has_ci_cd: boolean;
  scanned_at: string;
  top_category: string;
  risk_level: 'critical' | 'high' | 'medium' | 'low';
}

interface PortfolioSummary {
  total_repos: number;
  total_scans: number;
  avg_debt_score: number;
  total_cost_usd: number;
  total_hours: number;
  worst_score: number;
  best_score: number;
}

function asNumber(value: unknown, fallback: number = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

const RISK_STYLES = {
  critical: 'border border-danger/30 bg-danger/10 text-danger',
  high:     'border border-severity-high/30 bg-severity-high/10 text-severity-high',
  medium:   'border border-warning/30 bg-warning/10 text-warning',
  low:      'border border-success/30 bg-success/10 text-success',
};

const RISK_DOT = {
  critical: 'bg-severity-critical',
  high:     'bg-severity-high',
  medium:   'bg-severity-medium',
  low:      'bg-success',
};

export default function PortfolioPage() {
  const [repos, setRepos]         = useState<RepoSummary[]>([]);
  const [summary, setSummary]     = useState<PortfolioSummary | null>(null);
  const [sortBy, setSortBy]       = useState<'debt_score'|'total_cost'|'scanned_at'>('debt_score');
  const [sortDir, setSortDir]     = useState<'asc'|'desc'>('desc');
  const [loading, setLoading]     = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);
  const [scanning, setScanning]   = useState<string | null>(null);
  const [newRepo, setNewRepo]     = useState('');
  const [adding, setAdding]       = useState(false);
  const [selectedRepoUrl, setSelectedRepoUrl] = useState<string | null>(null);
  const {
    summary: selectedSummary,
    richTrend: selectedTrend,
    unresolved: selectedUnresolved,
    loading: insightLoading,
  } = useRepositoryInsights(selectedRepoUrl ?? '', 6);

  const fetchData = useCallback(async () => {
    try {
      const [prRes, psRes] = await Promise.all([
        authFetch(`${API}/portfolio`),
        authFetch(`${API}/portfolio/summary`),
      ]);
      if (prRes.status === 401) {
        setUnauthorized(true);
        setRepos([]);
        setSummary(null);
        return;
      }
      setUnauthorized(false);
      const [pr, ps] = await Promise.all([prRes.json(), psRes.json()]);
      setRepos(pr.repos || []);
      setSummary(ps);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (!repos.length) {
      setSelectedRepoUrl(null);
      return;
    }

    const currentStillExists = selectedRepoUrl
      ? repos.some((repo) => repo.github_url === selectedRepoUrl)
      : false;
    const nextRepo = currentStillExists ? selectedRepoUrl : repos[0].github_url;

    if (nextRepo && nextRepo !== selectedRepoUrl) {
      setSelectedRepoUrl(nextRepo);
    } else if (nextRepo && !selectedRepoUrl) {
      setSelectedRepoUrl(nextRepo);
    }
  }, [repos, selectedRepoUrl]);

  const sorted = [...repos].sort((a, b) => {
    const av = a[sortBy] as number | string;
    const bv = b[sortBy] as number | string;
    if (sortDir === 'desc') return av > bv ? -1 : 1;
    return av < bv ? -1 : 1;
  });

  const handleSort = (col: typeof sortBy) => {
    if (sortBy === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortBy(col); setSortDir('desc'); }
  };

  const handleRescan = async (url: string) => {
    setScanning(url);
    try {
      const repoId = url.replace('https://github.com/', '');
      const r = await authFetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: url, repo_id: repoId }),
      });
      if (r.ok) {
        alert('Re-scan started! Check the main dashboard for progress.');
      }
    } finally {
      setScanning(null);
    }
  };

  const handleRemove = async (repoId: string) => {
    if (!confirm(`Remove ${repoId} from portfolio?`)) return;
    await authFetch(`${API}/portfolio/${repoId}`, { method: 'DELETE' });
    fetchData();
  };

  const handleAddRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRepo.trim()) return;
    setAdding(true);
    try {
      const url = newRepo.trim();
      const repoId = url.replace('https://github.com/', '');
      const r = await authFetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: url, repo_id: repoId }),
      });
      if (r.ok) {
        setNewRepo('');
        const pollInterval = setInterval(async () => {
          await fetchData();
        }, 30000);
        setTimeout(() => clearInterval(pollInterval), 600000);
        alert('Scan started! This page will refresh automatically every 30s.');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setAdding(false);
    }
  };

  const scoreColor = (s: number) =>
    s >= 7 ? 'text-danger' :
    s >= 5 ? 'text-severity-high' :
    s >= 3 ? 'text-warning' : 'text-success';

  const SortHeader = ({ col, label }: { col: typeof sortBy; label: string }) => {
    const active = sortBy === col;
    const Icon = !active ? ArrowUpDown : sortDir === 'desc' ? ArrowDown : ArrowUp;
    return (
      <th
        scope="col"
        aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
        className="px-4 py-3 text-left font-medium text-muted-foreground"
      >
        <button
          type="button"
          onClick={() => handleSort(col)}
          className="inline-flex items-center gap-1 rounded hover:text-foreground"
        >
          {label}
          <Icon className={`size-3.5 ${active ? 'text-foreground' : 'opacity-60'}`} aria-hidden />
        </button>
      </th>
    );
  };

  if (loading) return (
    <div className="mx-auto w-full max-w-7xl space-y-6" aria-busy="true">
      <div className="h-9 w-64 animate-pulse rounded-md bg-muted" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-card" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-card" />
      <span className="sr-only">Loading portfolio</span>
    </div>
  );

  const hasRepos = repos.length > 0;

  return (
    <div className="mx-auto w-full max-w-7xl text-foreground">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Portfolio
        </h1>
        <p className="mt-1 text-muted-foreground">
          Debt cost and risk across every repository you&apos;ve scanned.
        </p>
      </div>

      {/* Summary Cards — only meaningful once something is tracked */}
      {summary && hasRepos && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            {
              label: 'Repos Tracked',
              value: asNumber(summary.total_repos),
              fmt: (v: number) => v.toString(),
            },
            {
              label: 'Avg Debt Score',
              value: asNumber(summary.avg_debt_score),
              fmt: (v: number) => `${v.toFixed(1)}/10`,
            },
            {
              label: 'Total Debt Cost',
              value: asNumber(summary.total_cost_usd),
              fmt: (v: number) => `$${(v / 1000).toFixed(0)}k`,
            },
            {
              label: 'Total Fix Hours',
              value: asNumber(summary.total_hours),
              fmt: (v: number) => `${v.toFixed(0)}h`,
            },
          ].map(card => (
            <div key={card.label}
                 className="bg-card rounded-xl p-5 border border-border">
              <div className="text-muted-foreground text-sm mb-1">
                {card.label}
              </div>
              <div className="tabular text-2xl font-semibold text-foreground">
                {card.fmt(card.value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Repo Bar */}
      {!unauthorized && (
        <form onSubmit={handleAddRepo}
              className="flex flex-col gap-3 mb-6 sm:flex-row">
          <label htmlFor="portfolio-add-repo" className="sr-only">
            GitHub repository URL
          </label>
          <input
            id="portfolio-add-repo"
            type="url"
            required
            value={newRepo}
            onChange={e => setNewRepo(e.target.value)}
            placeholder="https://github.com/owner/repo"
            className="min-w-0 flex-1 bg-card border border-border
                       rounded-lg px-4 py-2.5 text-foreground text-sm
                       placeholder:text-muted-foreground
                       focus:border-primary"
          />
          <button
            type="submit"
            disabled={adding}
            className="px-5 py-2.5 bg-primary hover:bg-primary/90
                       disabled:opacity-50 text-primary-foreground text-sm
                       font-medium rounded-lg transition-colors"
          >
            {adding ? 'Starting scan…' : 'Add and scan'}
          </button>
        </form>
      )}

      {(selectedSummary || insightLoading) && (
        <div className="space-y-6 mb-8">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xl font-semibold text-foreground">
              {selectedRepoUrl
                ? selectedRepoUrl.split('/').slice(-2).join('/')
                : 'Repository insights'}
            </h2>
            <p className="text-muted-foreground text-sm">
              Select a repository below to inspect it here.
            </p>
          </div>

          {insightLoading ? (
            <div className="bg-card rounded-xl p-8 border border-border text-muted-foreground">
              Loading repository insights...
            </div>
          ) : (
            <>
              {selectedSummary && (
                <RepositoryInsightsPanel summary={selectedSummary} />
              )}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {selectedTrend && (
                  <ActiveDebtChart points={selectedTrend.active_trend ?? []} />
                )}
                {selectedUnresolved && (
                  <UnresolvedFindingsList
                    findings={selectedUnresolved.items}
                    title="Unresolved findings"
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Repo Table */}
      {!hasRepos ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-card px-6 py-12 text-center">
          <FolderGit2 className="mx-auto mb-4 size-8 text-muted-foreground" aria-hidden />
          {unauthorized ? (
            <>
              <h2 className="text-lg font-medium text-foreground">
                Sign in to see your portfolio
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                Scans are saved to your GitHub account. Sign in from the top bar, or run
                a one-off scan from the Analyzer without saving it.
              </p>
            </>
          ) : (
            <>
              <h2 className="text-lg font-medium text-foreground">No repositories yet</h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                Add a GitHub URL above. Each completed scan appears here with its cost,
                score, and trend.
              </p>
            </>
          )}
          <Link
            href="/"
            className="mt-6 inline-flex items-center rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-foreground hover:bg-surface-raised"
          >
            Go to Analyzer
          </Link>
        </div>
      ) : (
        <div className="bg-card rounded-xl border border-border overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-raised">
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  Repository
                </th>
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  Risk
                </th>
                <SortHeader col="debt_score" label="Score" />
                <SortHeader col="total_cost" label="Cost" />
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  Language
                </th>
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  Top issue
                </th>
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  Health
                </th>
                <SortHeader col="scanned_at" label="Scanned" />
                <th scope="col" className="text-left px-4 py-3 text-muted-foreground font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((repo, idx) => {
                const name = repo.github_url.split('/').slice(-2).join('/');
                const date = repo.scanned_at
                  ? new Date(repo.scanned_at).toLocaleDateString()
                  : 'N/A';

                return (
                  <tr key={repo.repo_id}
                      className={`border-b border-border last:border-b-0
                        ${idx % 2 === 0 ? '' : 'bg-surface-raised/50'}
                        hover:bg-surface-raised transition-colors`}>

                    {/* Repo name */}
                    <td className="px-4 py-3">
                      <Link
                         href={repoDetailPath(repo.github_url)}
                         className="text-primary hover:text-accent-foreground
                                    font-medium">
                        {name}
                      </Link>
                    </td>

                    {/* Risk badge */}
                    <td className="px-4 py-3 align-middle">
                      <span
                        className={`inline-flex min-w-fit items-center gap-2 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold capitalize tracking-wide ${RISK_STYLES[repo.risk_level]}`}
                      >
                        <span
                          className={`inline-block h-2 w-2 shrink-0 rounded-full ${RISK_DOT[repo.risk_level]}`}
                        />
                        {repo.risk_level}
                      </span>
                    </td>

                    {/* Debt score */}
                    <td className="px-4 py-3">
                      <span className={`tabular text-lg font-semibold
                                        ${scoreColor(repo.debt_score)}`}>
                        {repo.debt_score.toFixed(1)}
                      </span>
                      <span className="text-muted-foreground text-xs">/10</span>
                    </td>

                    {/* Cost */}
                    <td className="tabular px-4 py-3 text-foreground font-medium">
                      ${(repo.total_cost / 1000).toFixed(0)}k
                    </td>

                    {/* Language */}
                    <td className="px-4 py-3 text-foreground">
                      {repo.language}
                    </td>

                    {/* Top issue */}
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {repo.top_category}
                    </td>

                    {/* Health indicators */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        {([
                          ['Tests', repo.has_tests],
                          ['CI', repo.has_ci_cd],
                        ] as const).map(([label, ok]) => {
                          const Icon = ok ? Check : X;
                          return (
                            <span key={label} className="inline-flex items-center gap-1">
                              <Icon
                                className={`size-3.5 ${ok ? 'text-success' : 'text-danger'}`}
                                aria-hidden
                              />
                              {label}
                              <span className="sr-only">{ok ? 'present' : 'missing'}</span>
                            </span>
                          );
                        })}
                      </div>
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {date}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => setSelectedRepoUrl(repo.github_url)}
                          className={`text-xs px-2.5 py-1 rounded transition-colors ${
                            selectedRepoUrl === repo.github_url
                              ? 'bg-accent text-primary'
                              : 'bg-surface-raised text-foreground hover:bg-muted'
                          }`}
                        >
                          Inspect
                        </button>
                        <Link
                          href={repoDetailPath(repo.github_url)}
                          className="text-xs px-2.5 py-1 rounded
                                     bg-surface-raised text-foreground
                                     hover:bg-muted transition-colors"
                        >
                          Open
                        </Link>
                        {repo.scan_count && repo.scan_count >= 2 &&
                         repo.previous_scan_id && repo.latest_scan_id ? (
                          <Link
                            href={`/compare/${repo.previous_scan_id}/${repo.latest_scan_id}`}
                            title="Compare the two most recent scans"
                            className="text-xs px-2.5 py-1 rounded
                                       bg-surface-raised text-foreground
                                       hover:bg-muted transition-colors"
                          >
                            Compare
                          </Link>
                        ) : (
                          <span
                            title="Run at least 2 scans of this repo to compare"
                            className="text-xs px-2.5 py-1 rounded
                                       bg-surface-raised text-muted-foreground cursor-not-allowed"
                          >
                            Compare
                          </span>
                        )}
                        <button
                          onClick={() => handleRescan(repo.github_url)}
                          disabled={scanning === repo.github_url}
                          className="text-xs px-2.5 py-1 rounded
                                     bg-accent text-accent-foreground
                                     hover:bg-primary/25 transition-colors
                                     disabled:opacity-50"
                        >
                          {scanning === repo.github_url ? 'Starting…' : 'Rescan'}
                        </button>
                        <button
                          onClick={() => handleRemove(repo.repo_id)}
                          aria-label={`Remove ${name} from portfolio`}
                          title="Remove from portfolio"
                          className="rounded p-1 text-muted-foreground
                                     hover:bg-danger/15 hover:text-danger transition-colors"
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
