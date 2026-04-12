'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';

import { pollResults } from '@/lib/api';
import { JobResult } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

interface Props {
  jobId: string;
  onComplete: (result: JobResult) => void;
}

const STEPS = [
  { key: 'queued', label: 'Queued', pct: 5 },
  { key: 'running', label: 'Cloning repository', pct: 20 },
  { key: 'analyzing', label: 'Running analysis', pct: 60 },
  { key: 'reporting', label: 'Generating report', pct: 85 },
  { key: 'complete', label: 'Complete', pct: 100 },
];

export default function ProgressBar({ jobId, onComplete }: Props) {
  const [status, setStatus] = useState('queued');
  const [error, setError] = useState('');

  useEffect(() => {
    pollResults(jobId, (result) => {
      setStatus(result.status);
      if (result.status === 'failed') {
        setError(result.error || 'Analysis failed');
      }
    })
      .then(onComplete)
      .catch((err) => setError(err.message));
  }, [jobId, onComplete]);

  const currentStep = STEPS.find((s) => s.key === status) || STEPS[0];
  const pct = currentStep.pct;

  if (error) {
    return (
      <Card className="mx-auto w-full max-w-2xl border-destructive/30 bg-card">
        <CardContent className="p-6">
          <p className="text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mx-auto w-full max-w-2xl border-border bg-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-4">
          <CardTitle className="text-base font-medium">Analysis in progress</CardTitle>
          <span className="font-mono text-sm tabular-nums text-muted-foreground">
            {pct}%
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{currentStep.label}</span>
            <span>Job {jobId.slice(0, 8)}</span>
          </div>
          <Progress value={pct} />
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          {STEPS.filter((s) => s.key !== 'queued').map((step) => {
            const done = STEPS.indexOf(currentStep) >= STEPS.indexOf(step);
            return (
              <div
                key={step.key}
                className="rounded-lg border border-border bg-muted/20 p-3"
              >
                <div className="mb-2 flex items-center gap-2">
                  <CheckCircle2
                    className={`size-4 ${done ? 'text-primary' : 'text-muted-foreground/40'}`}
                  />
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
                    {step.pct}%
                  </span>
                </div>
                <p className={`text-sm ${done ? 'text-foreground' : 'text-muted-foreground'}`}>
                  {step.label}
                </p>
              </div>
            );
          })}
        </div>

        <p className="text-sm text-muted-foreground">
          Running clone, static analysis, git mining, and report generation. Most
          scans complete in 2 to 5 minutes.
        </p>
      </CardContent>
    </Card>
  );
}
