'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import {
  getGitHubOrgRepos,
  getGitHubOrgs,
  getGitHubRepos,
  importGitHubRepo,
  startAnalysis,
} from '@/lib/api';
import { GitHubOrg, GitHubRepo } from '@/types';

type SourceMode = 'personal' | 'organization';

export default function ImportReposPage() {
  const [sourceMode, setSourceMode] = useState<SourceMode>('personal');
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [orgs, setOrgs] = useState<GitHubOrg[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyRepo, setBusyRepo] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [repoData, orgData] = await Promise.all([
          getGitHubRepos(),
          getGitHubOrgs(),
        ]);
        setRepos(repoData.repositories || []);
        setOrgs(orgData.organizations || []);
        if (orgData.organizations?.length) {
          setSelectedOrg(orgData.organizations[0].login);
        }
      } catch (err) {
        console.error(err);
        setError('Failed to load GitHub repositories. Please sign in again.');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  useEffect(() => {
    if (sourceMode !== 'organization' || !selectedOrg) return;
    const loadOrgRepos = async () => {
      setLoading(true);
      setError('');
      try {
        const repoData = await getGitHubOrgRepos(selectedOrg);
        setRepos(repoData.repositories || []);
      } catch (err) {
        console.error(err);
        setError('Failed to load organization repositories.');
      } finally {
        setLoading(false);
      }
    };
    void loadOrgRepos();
  }, [sourceMode, selectedOrg]);

  const filteredRepos = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return repos;
    return repos.filter((repo) => {
      const haystack = [
        repo.full_name,
        repo.description || '',
        repo.language || '',
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(normalized);
    });
  }, [repos, query]);

  const handleImport = async (repo: GitHubRepo, scanAfterImport: boolean) => {
    setBusyRepo(repo.full_name);
    setMessage('');
    setError('');
    try {
      await importGitHubRepo(repo.html_url);
      if (scanAfterImport) {
        const scan = await startAnalysis(repo.html_url);
        setMessage(`Imported and queued scan for ${repo.full_name}. Job: ${scan.job_id}`);
      } else {
        setMessage(`Imported ${repo.full_name} successfully.`);
      }
    } catch (err) {
      console.error(err);
      setError(`Failed to import ${repo.full_name}.`);
    } finally {
      setBusyRepo(null);
    }
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-gray-500 text-sm uppercase tracking-wider mb-1">
              GitHub Import
            </p>
            <h1 className="text-3xl font-bold text-white">Import Repositories</h1>
            <p className="text-gray-400 mt-2">
              Bring personal or organization repositories into Tech Debt Quantifier without copying URLs manually.
            </p>
          </div>
          <div className="flex gap-3">
            <Link href="/" className="text-sm text-gray-400 hover:text-white">
              Back to Scanner
            </Link>
            <Link href="/portfolio" className="text-sm text-purple-400 hover:text-purple-300">
              Go to Portfolio
            </Link>
          </div>
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setSourceMode('personal')}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                sourceMode === 'personal'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
            >
              Personal Repos
            </button>
            <button
              onClick={() => setSourceMode('organization')}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                sourceMode === 'organization'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
            >
              Organization Repos
            </button>

            {sourceMode === 'organization' && (
              <select
                value={selectedOrg}
                onChange={(e) => setSelectedOrg(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
              >
                {orgs.map((org) => (
                  <option key={org.id} value={org.login}>
                    {org.login}
                  </option>
                ))}
              </select>
            )}

            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search repos, descriptions, languages..."
              className="flex-1 min-w-[220px] bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500"
            />
          </div>

          {message && <p className="text-green-400 text-sm">{message}</p>}
          {error && <p className="text-red-400 text-sm">{error}</p>}
        </div>

        {loading ? (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-gray-400">
            Loading repositories...
          </div>
        ) : (
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-800 text-sm text-gray-400">
              {filteredRepos.length} repositories available
            </div>
            <div className="divide-y divide-gray-800">
              {filteredRepos.map((repo) => (
                <div
                  key={repo.id}
                  className="px-5 py-4 flex flex-wrap items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <a
                        href={repo.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-purple-400 hover:text-purple-300 font-medium"
                      >
                        {repo.full_name}
                      </a>
                      {repo.private && (
                        <span className="text-[10px] uppercase tracking-wider bg-yellow-900/30 text-yellow-400 px-2 py-0.5 rounded-full border border-yellow-800">
                          Private
                        </span>
                      )}
                    </div>
                    <p className="text-gray-400 text-sm mt-1">
                      {repo.description || 'No description provided'}
                    </p>
                    <p className="text-gray-500 text-xs mt-2">
                      {repo.language || 'Unknown'} · Updated{' '}
                      {repo.updated_at ? new Date(repo.updated_at).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => void handleImport(repo, false)}
                      disabled={busyRepo === repo.full_name}
                      className="px-4 py-2 rounded-lg bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm disabled:opacity-50"
                    >
                      {busyRepo === repo.full_name ? 'Working...' : 'Import'}
                    </button>
                    <button
                      onClick={() => void handleImport(repo, true)}
                      disabled={busyRepo === repo.full_name}
                      className="px-4 py-2 rounded-lg bg-purple-600 text-white hover:bg-purple-700 text-sm disabled:opacity-50"
                    >
                      Import & Scan
                    </button>
                  </div>
                </div>
              ))}

              {!filteredRepos.length && (
                <div className="px-5 py-8 text-gray-400 text-sm">
                  No repositories matched your filters.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
