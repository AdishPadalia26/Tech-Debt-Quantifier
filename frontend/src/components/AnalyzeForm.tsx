'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, GitBranch, Loader2 } from 'lucide-react';

import {
  AUTH_CHANGED_EVENT,
  getCurrentUser,
  getGitHubRepos,
  startAnalysis,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

interface Props {
  onJobStarted: (jobId: string, githubUrl: string) => void;
}

type GitHubPickerRepo = {
  id: number;
  full_name: string;
  html_url: string;
  private: boolean;
};

export default function AnalyzeForm({ onJobStarted }: Props) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [githubRepos, setGithubRepos] = useState<GitHubPickerRepo[]>([]);
  const [repoError, setRepoError] = useState('');

  useEffect(() => {
    const syncAuthState = async () => {
      try {
        const user = await getCurrentUser();
        setIsSignedIn(Boolean(user));
        if (!user) {
          setGithubRepos([]);
          setPickerOpen(false);
        }
      } catch {
        setIsSignedIn(false);
        setGithubRepos([]);
        setPickerOpen(false);
      }
    };

    void syncAuthState();

    const handleAuthChanged = () => {
      void syncAuthState();
    };

    window.addEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
    window.addEventListener('focus', handleAuthChanged);

    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, handleAuthChanged);
      window.removeEventListener('focus', handleAuthChanged);
    };
  }, []);

  const pickerRepos = useMemo(() => githubRepos.slice(0, 12), [githubRepos]);

  const handleOpenPicker = async () => {
    if (!isSignedIn) {
      setRepoError('Sign in with GitHub first to browse your repositories.');
      return;
    }

    setPickerOpen((current) => !current);
    if (githubRepos.length > 0 || pickerOpen) {
      return;
    }

    setLoadingRepos(true);
    setRepoError('');
    try {
      const response = await getGitHubRepos();
      setGithubRepos(response.repositories || []);
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { data?: { detail?: string } };
        message?: string;
      };
      setRepoError(
        axiosErr.response?.data?.detail ||
          axiosErr.message ||
          'Failed to load your GitHub repositories.'
      );
    } finally {
      setLoadingRepos(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      setError("Paste a GitHub repository URL, or pick an example below.");
      return;
    }

    if (!url.includes('github.com')) {
      setError('Please enter a valid GitHub repository URL');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await startAnalysis(url.trim());
      onJobStarted(response.job_id, url.trim());
    } catch (err: unknown) {
      const axiosErr = err as {
        message?: string;
        response?: { data?: { detail?: string } };
      };
      setError(
        axiosErr.response?.data?.detail ||
          axiosErr.message ||
          'Failed to start analysis'
      );
    } finally {
      setLoading(false);
    }
  };

  const exampleRepos = [
    'https://github.com/pallets/flask',
    'https://github.com/django/django',
    'https://github.com/fastapi/fastapi',
  ];

  return (
    <Card className="mx-auto w-full max-w-2xl border-border bg-card">
      <CardHeader>
        <CardTitle>Analyze a repository</CardTitle>
        <CardDescription>
          Public repos work without signing in. Most scans finish in a few minutes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <label htmlFor="analyze-repo-url" className="sr-only">
            GitHub repository URL
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <GitBranch
                aria-hidden
                className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                id="analyze-repo-url"
                type="url"
                aria-invalid={Boolean(error)}
                aria-describedby={error ? "analyze-repo-error" : undefined}
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  if (error) setError("");
                }}
                placeholder="https://github.com/owner/repository"
                className="w-full rounded-md border border-input bg-input py-2.5 pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                disabled={loading}
              />
            </div>
            <Button type="submit" disabled={loading} className="min-w-28">
              {loading ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  Analyzing
                </>
              ) : (
                'Analyze'
              )}
            </Button>
          </div>
          {error && (
            <p id="analyze-repo-error" role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </form>

        <div className="space-y-3 rounded-lg border border-border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                Pick from your GitHub repos
              </p>
              <p className="text-xs text-muted-foreground">
                {isSignedIn
                  ? 'Use your connected GitHub account to analyze personal and private repositories.'
                  : 'Sign in with GitHub to browse repositories instead of pasting a URL.'}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void handleOpenPicker();
              }}
              disabled={loadingRepos}
            >
              {loadingRepos ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  Loading
                </>
              ) : (
                <>
                  Browse repos
                  <ChevronDown className="ml-2 size-4" />
                </>
              )}
            </Button>
          </div>
          {repoError ? <p className="text-sm text-destructive">{repoError}</p> : null}
          {pickerOpen ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {pickerRepos.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {loadingRepos
                    ? 'Loading repositories...'
                    : 'No GitHub repositories available yet.'}
                </p>
              ) : (
                pickerRepos.map((repo) => (
                  <button
                    key={repo.id}
                    type="button"
                    onClick={() => {
                      setUrl(repo.html_url);
                      setPickerOpen(false);
                    }}
                    className="rounded-md border border-border bg-background/40 px-3 py-2 text-left transition-colors hover:bg-muted/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs text-foreground">
                        {repo.full_name}
                      </span>
                      {repo.private ? (
                        <span className="rounded-full border border-warning/20 bg-warning/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-warning">
                          Private
                        </span>
                      ) : null}
                    </div>
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>

        <div>
          <p className="mb-2 text-sm text-muted-foreground">Or try an open-source repo</p>
          <div className="flex flex-wrap gap-2">
            {exampleRepos.map((repo) => (
              <Button
                key={repo}
                type="button"
                onClick={() => setUrl(repo)}
                variant="outline"
                size="sm"
                className="font-mono text-xs tabular-nums"
              >
                {repo.split('/').slice(-2).join('/')}
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
