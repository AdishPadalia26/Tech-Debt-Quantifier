'use client';

import { useState } from 'react';
import { GitBranch, Loader2, Sparkles } from 'lucide-react';

import { startAnalysis } from '@/lib/api';
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

export default function AnalyzeForm({ onJobStarted }: Props) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

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
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to start analysis');
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
        <div className="mb-3 inline-flex w-fit items-center gap-2 rounded-full border border-border bg-muted/40 px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="size-3.5 text-primary" />
          Explainable debt scoring for engineering and leadership
        </div>
        <CardTitle>Analyze Repository</CardTitle>
        <CardDescription>
          Paste a GitHub URL to quantify tech debt cost and remediation effort.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <GitBranch className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                className="w-full rounded-md border border-input bg-input py-2.5 pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                disabled={loading}
              />
            </div>
            <Button type="submit" disabled={loading || !url.trim()} className="min-w-28">
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
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>

        <div>
          <p className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
            Try an example
          </p>
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
