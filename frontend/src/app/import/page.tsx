'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { GitBranch, Loader2, LockKeyhole, ShieldCheck } from 'lucide-react';

import {
  AUTH_CHANGED_EVENT,
  getCurrentUser,
  getGitHubOrgRepos,
  getGitHubOrgs,
  getGitHubRepos,
  importGitHubRepo,
  startAnalysis,
} from '@/lib/api';
import { GitHubOrg, GitHubRepo } from '@/types';

type SourceMode = 'personal' | 'organization';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function ImportReposPage() {
  const [sourceMode, setSourceMode] = useState<SourceMode>('personal');
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [orgs, setOrgs] = useState<GitHubOrg[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [error, setError] = useState('');
  const [busyRepo, setBusyRepo] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');

      try {
        const user = await getCurrentUser();
        if (!user) {
          setSignedIn(false);
          setRepos([]);
          setOrgs([]);
          return;
        }

        setSignedIn(true);
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
        setSignedIn(false);
        setRepos([]);
        setOrgs([]);
        setError('Connect GitHub to browse repositories.');
      } finally {
        setLoading(false);
      }
    };

    void load();

    const handleAuthChanged = () => {
      void load();
    };

    window.addEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
    window.addEventListener('focus', handleAuthChanged);

    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
      window.removeEventListener('focus', handleAuthChanged);
    };
  }, []);

  useEffect(() => {
    if (!signedIn || sourceMode !== 'organization' || !selectedOrg) return;

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
  }, [selectedOrg, signedIn, sourceMode]);

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
  }, [query, repos]);

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

  const handleLogin = () => {
    window.location.href = `${API_URL}/auth/github/login`;
  };

  return (
    <div className="w-full min-w-0">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="mb-1 text-sm uppercase tracking-wider text-muted-foreground">
              GitHub Import
            </p>
            <h1 className="text-3xl font-bold text-foreground">Import Repositories</h1>
            <p className="mt-2 text-muted-foreground">
              Bring personal or organization repositories into Tech Debt Quantifier without copying URLs manually.
            </p>
          </div>
          <div className="flex gap-3">
            <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
              Back to Scanner
            </Link>
            <Link href="/portfolio" className="text-sm text-primary hover:text-accent-foreground">
              Go to Portfolio
            </Link>
          </div>
        </div>

        {!signedIn && !loading ? (
          <div className="rounded-xl border border-border bg-card p-8">
            <div className="mx-auto max-w-2xl space-y-4 text-center">
              <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-background">
                <LockKeyhole className="size-5 text-primary" />
              </div>
              <div>
                <h2 className="text-2xl font-semibold text-foreground">Connect GitHub to import repositories</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Sign in with GitHub to browse personal and organization repositories, including private repos you can access.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                <button
                  onClick={handleLogin}
                  className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                >
                  <GitBranch className="mr-2 size-4" />
                  Sign in with GitHub
                </button>
                <div className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                  <ShieldCheck className="size-4 text-success" />
                  Your GitHub token stays tied to your own session
                </div>
              </div>
              {error ? <p className="text-sm text-danger">{error}</p> : null}
            </div>
          </div>
        ) : (
          <>
            <div className="space-y-4 rounded-xl border border-border bg-card p-5">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => setSourceMode('personal')}
                  className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                    sourceMode === 'personal'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-surface-raised text-foreground hover:bg-muted'
                  }`}
                >
                  Personal Repos
                </button>
                <button
                  onClick={() => setSourceMode('organization')}
                  className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                    sourceMode === 'organization'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-surface-raised text-foreground hover:bg-muted'
                  }`}
                >
                  Organization Repos
                </button>

                {sourceMode === 'organization' ? (
                  <select
                    value={selectedOrg}
                    onChange={(e) => setSelectedOrg(e.target.value)}
                    className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-foreground"
                  >
                    {orgs.map((org) => (
                      <option key={org.id} value={org.login}>
                        {org.login}
                      </option>
                    ))}
                  </select>
                ) : null}

                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search repos, descriptions, languages..."
                  className="min-w-[220px] flex-1 rounded-lg border border-border bg-surface-raised px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground"
                />
              </div>

              {message ? <p className="text-sm text-success">{message}</p> : null}
              {error ? <p className="text-sm text-danger">{error}</p> : null}
            </div>

            {loading ? (
              <div className="rounded-xl border border-border bg-card p-8 text-muted-foreground">
                <div className="inline-flex items-center gap-2">
                  <Loader2 className="size-4 animate-spin" />
                  Loading repositories...
                </div>
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                <div className="border-b border-border px-5 py-4 text-sm text-muted-foreground">
                  {filteredRepos.length} repositories available
                </div>
                <div className="divide-y divide-border">
                  {filteredRepos.map((repo) => (
                    <div
                      key={repo.id}
                      className="flex flex-wrap items-center justify-between gap-4 px-5 py-4"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <a
                            href={repo.html_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-primary hover:text-accent-foreground"
                          >
                            {repo.full_name}
                          </a>
                          {repo.private ? (
                            <span className="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-warning">
                              Private
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {repo.description || 'No description provided'}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {repo.language || 'Unknown'} · Updated{' '}
                          {repo.updated_at ? new Date(repo.updated_at).toLocaleDateString() : 'N/A'}
                        </p>
                      </div>

                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            void handleImport(repo, false);
                          }}
                          disabled={busyRepo === repo.full_name}
                          className="rounded-lg bg-surface-raised px-4 py-2 text-sm text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                        >
                          {busyRepo === repo.full_name ? 'Working...' : 'Import'}
                        </button>
                        <button
                          onClick={() => {
                            void handleImport(repo, true);
                          }}
                          disabled={busyRepo === repo.full_name}
                          className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                        >
                          Import & Scan
                        </button>
                      </div>
                    </div>
                  ))}

                  {!filteredRepos.length ? (
                    <div className="px-5 py-8 text-sm text-muted-foreground">
                      No repositories matched your filters.
                    </div>
                  ) : null}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
