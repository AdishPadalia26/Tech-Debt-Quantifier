'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import ActiveDebtChart from '@/components/ActiveDebtChart';
import RepositoryInsightsPanel from '@/components/RepositoryInsightsPanel';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import {
  getRepoHistoryRich,
  getRepositorySummary,
  getRepositoryUnresolved,
} from '@/lib/api';
import {
  RepoSummaryRollup,
  RichRepoTrend,
  UnresolvedFindingsResponse,
} from '@/types';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('tdq_token');
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return fetch(url, { ...options, headers });
}

interface RepoSummary {
  repo_id: string;
  github_url: string;
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

const RISK_STYLES = {
  critical: 'bg-red-900/40 text-red-400 border border-red-800',
  high:     'bg-orange-900/40 text-orange-400 border border-orange-800',
  medium:   'bg-yellow-900/40 text-yellow-400 border border-yellow-800',
  low:      'bg-green-900/40 text-green-400 border border-green-800',
};

const RISK_DOT = {
  critical: 'bg-red-500',
  high:     'bg-orange-500',
  medium:   'bg-yellow-500',
  low:      'bg-green-500',
};

export default function PortfolioPage() {
  const [repos, setRepos]         = useState<RepoSummary[]>([]);
  const [summary, setSummary]     = useState<PortfolioSummary | null>(null);
  const [sortBy, setSortBy]       = useState<'debt_score'|'total_cost'|'scanned_at'>('debt_score');
  const [sortDir, setSortDir]     = useState<'asc'|'desc'>('desc');
  const [loading, setLoading]     = useState(true);
  const [scanning, setScanning]   = useState<string | null>(null);
  const [newRepo, setNewRepo]     = useState('');
  const [adding, setAdding]       = useState(false);
  const [selectedRepoUrl, setSelectedRepoUrl] = useState<string | null>(null);
  const [selectedSummary, setSelectedSummary] = useState<RepoSummaryRollup | null>(null);
  const [selectedTrend, setSelectedTrend] = useState<RichRepoTrend | null>(null);
  const [selectedUnresolved, setSelectedUnresolved] =
    useState<UnresolvedFindingsResponse | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [pr, ps] = await Promise.all([
        authFetch(`${API}/portfolio`).then(r => r.json()),
        authFetch(`${API}/portfolio/summary`).then(r => r.json()),
      ]);
      setRepos(pr.repos || []);
      setSummary(ps);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const loadRepoInsights = useCallback(async (repoUrl: string) => {
    setInsightLoading(true);
    setSelectedRepoUrl(repoUrl);
    try {
      const [summaryData, trendData, unresolvedData] = await Promise.all([
        getRepositorySummary(repoUrl),
        getRepoHistoryRich(repoUrl),
        getRepositoryUnresolved(repoUrl, 6),
      ]);
      setSelectedSummary(summaryData);
      setSelectedTrend(trendData);
      setSelectedUnresolved(unresolvedData);
    } catch (e) {
      console.error(e);
      setSelectedSummary(null);
      setSelectedTrend(null);
      setSelectedUnresolved(null);
    } finally {
      setInsightLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!repos.length) {
      setSelectedRepoUrl(null);
      setSelectedSummary(null);
      setSelectedTrend(null);
      setSelectedUnresolved(null);
      return;
    }

    const currentStillExists = selectedRepoUrl
      ? repos.some((repo) => repo.github_url === selectedRepoUrl)
      : false;
    const nextRepo = currentStillExists ? selectedRepoUrl : repos[0].github_url;

    if (nextRepo && nextRepo !== selectedRepoUrl) {
      void loadRepoInsights(nextRepo);
    } else if (nextRepo && !selectedSummary && !insightLoading) {
      void loadRepoInsights(nextRepo);
    }
  }, [repos, selectedRepoUrl, selectedSummary, insightLoading, loadRepoInsights]);

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
    s >= 7 ? 'text-red-400' :
    s >= 5 ? 'text-orange-400' :
    s >= 3 ? 'text-yellow-400' : 'text-green-400';

  const sortIcon = (col: string) =>
    sortBy === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ' ↕';

  if (loading) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-purple-400 text-xl animate-pulse">
        Loading portfolio...
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">
            Repository Portfolio
          </h1>
          <p className="text-gray-400 mt-1">
            Track and compare tech debt across all your repos
          </p>
        </div>
        <Link
          href="/"
          className="text-purple-400 hover:text-purple-300 text-sm"
        >
          ← Back to Scanner
        </Link>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Repos Tracked',  value: summary.total_repos,
              fmt: (v: number) => v.toString() },
            { label: 'Avg Debt Score', value: summary.avg_debt_score,
              fmt: (v: number) => `${v.toFixed(1)}/10` },
            { label: 'Total Debt Cost', value: summary.total_cost_usd,
              fmt: (v: number) => `$${(v/1000).toFixed(0)}k` },
            { label: 'Total Fix Hours', value: summary.total_hours,
              fmt: (v: number) => `${v.toFixed(0)}h` },
          ].map(card => (
            <div key={card.label}
                 className="bg-gray-900 rounded-xl p-5 border border-gray-800">
              <div className="text-gray-400 text-xs uppercase tracking-wider mb-1">
                {card.label}
              </div>
              <div className="text-2xl font-bold text-white">
                {card.fmt(card.value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Repo Bar */}
      <form onSubmit={handleAddRepo}
            className="flex gap-3 mb-6">
        <input
          type="url"
          value={newRepo}
          onChange={e => setNewRepo(e.target.value)}
          placeholder="https://github.com/owner/repo"
          className="flex-1 bg-gray-900 border border-gray-700
                     rounded-lg px-4 py-2.5 text-white text-sm
                     placeholder-gray-500 focus:outline-none
                     focus:border-purple-500"
        />
        <button
          type="submit"
          disabled={adding}
          className="px-5 py-2.5 bg-purple-600 hover:bg-purple-700
                     disabled:bg-gray-700 text-white text-sm
                     font-medium rounded-lg transition-colors"
        >
          {adding ? 'Starting...' : '+ Add & Scan Repo'}
        </button>
      </form>

      {(selectedSummary || insightLoading) && (
        <div className="space-y-6 mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">
                Selected Repository Insights
              </h2>
              <p className="text-gray-400 text-sm">
                Deep view powered by the new structured backend rollups
              </p>
            </div>
            {selectedRepoUrl && (
              <p className="text-sm text-purple-400">
                {selectedRepoUrl.split('/').slice(-2).join('/')}
              </p>
            )}
          </div>

          {insightLoading ? (
            <div className="bg-gray-900 rounded-xl p-8 border border-gray-800 text-gray-400">
              Loading repository insights...
            </div>
          ) : (
            <>
              {selectedSummary && (
                <RepositoryInsightsPanel summary={selectedSummary} />
              )}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {selectedTrend && (
                  <ActiveDebtChart points={selectedTrend.active_trend} />
                )}
                {selectedUnresolved && (
                  <UnresolvedFindingsList
                    findings={selectedUnresolved.items}
                    title="Selected Repo Unresolved Findings"
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Repo Table */}
      {repos.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-12 text-center
                        border border-gray-800">
          <div className="text-4xl mb-3">📭</div>
          <div className="text-gray-400">No repos scanned yet.</div>
          <div className="text-gray-500 text-sm mt-1">
            Add a GitHub URL above or scan from the main dashboard.
          </div>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-800/50">
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Repository
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Risk
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium
                               cursor-pointer hover:text-white"
                    onClick={() => handleSort('debt_score')}>
                  Score{sortIcon('debt_score')}
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium
                               cursor-pointer hover:text-white"
                    onClick={() => handleSort('total_cost')}>
                  Cost{sortIcon('total_cost')}
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Language
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Top Issue
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Health
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium
                               cursor-pointer hover:text-white"
                    onClick={() => handleSort('scanned_at')}>
                  Scanned{sortIcon('scanned_at')}
                </th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">
                  Actions
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
                      className={`border-b border-gray-800/50
                        ${idx % 2 === 0 ? '' : 'bg-gray-800/20'}
                        hover:bg-gray-800/40 transition-colors`}>

                    {/* Repo name */}
                    <td className="px-4 py-3">
                      <a href={repo.github_url}
                         target="_blank" rel="noopener noreferrer"
                         className="text-purple-400 hover:text-purple-300
                                    font-medium">
                        {name}
                      </a>
                    </td>

                    {/* Risk badge */}
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs
                                        font-medium ${RISK_STYLES[repo.risk_level]}`}>
                        <span className={`inline-block w-1.5 h-1.5 rounded-full
                                          mr-1.5 ${RISK_DOT[repo.risk_level]}`} />
                        {repo.risk_level}
                      </span>
                    </td>

                    {/* Debt score */}
                    <td className="px-4 py-3">
                      <span className={`text-lg font-bold
                                        ${scoreColor(repo.debt_score)}`}>
                        {repo.debt_score.toFixed(1)}
                      </span>
                      <span className="text-gray-600 text-xs">/10</span>
                    </td>

                    {/* Cost */}
                    <td className="px-4 py-3 text-white font-medium">
                      ${(repo.total_cost / 1000).toFixed(0)}k
                    </td>

                    {/* Language */}
                    <td className="px-4 py-3 text-gray-300">
                      {repo.language}
                    </td>

                    {/* Top issue */}
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {repo.top_category}
                    </td>

                    {/* Health indicators */}
                    <td className="px-4 py-3">
                      <div className="flex gap-1.5">
                        <span title={repo.has_tests ? 'Has tests' : 'No tests'}
                              className={repo.has_tests ? 'text-green-400' : 'text-red-400'}>
                          {repo.has_tests ? '✓' : '✗'}
                        </span>
                        <span className="text-gray-600 text-xs">tests</span>
                        <span title={repo.has_ci_cd ? 'Has CI/CD' : 'No CI/CD'}
                              className={repo.has_ci_cd ? 'text-green-400' : 'text-red-400'}>
                          {repo.has_ci_cd ? '✓' : '✗'}
                        </span>
                        <span className="text-gray-600 text-xs">CI</span>
                      </div>
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {date}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => void loadRepoInsights(repo.github_url)}
                          className={`text-xs px-2.5 py-1 rounded transition-colors ${
                            selectedRepoUrl === repo.github_url
                              ? 'bg-cyan-900/40 text-cyan-300'
                              : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                          }`}
                        >
                          Inspect
                        </button>
                        <button
                          onClick={() => handleRescan(repo.github_url)}
                          disabled={scanning === repo.github_url}
                          className="text-xs px-2.5 py-1 rounded
                                     bg-purple-900/40 text-purple-400
                                     hover:bg-purple-900/70 transition-colors
                                     disabled:opacity-50"
                        >
                          {scanning === repo.github_url ? '...' : 'Scan'}
                        </button>
                        <button
                          onClick={() => handleRemove(repo.repo_id)}
                          className="text-xs px-2.5 py-1 rounded
                                     bg-red-900/30 text-red-400
                                     hover:bg-red-900/60 transition-colors"
                        >
                          X
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

      {/* Footer note */}
      <p className="text-gray-600 text-xs text-center mt-6">
        Scores update automatically after each scan · Click column headers to sort
      </p>
    </div>
  );
}
