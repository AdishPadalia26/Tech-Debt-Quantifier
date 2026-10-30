'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';

import { pollResults } from '@/lib/api';
import { cn } from '@/lib/utils';
import { JobResult } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

interface Props {
  jobId: string;
  onComplete: (result: JobResult) => void;
}

// The backend keeps status at "processing" for the whole run and only moves
// `progress`, so steps are matched on percentage. Thresholds mirror the
// backend phases (clone 5, analysis 25-88, report 92, done 100).
const STEPS = [
  { key: 'cloning', label: 'Cloning repository', pct: 5 },
  { key: 'analyzing', label: 'Running analysis', pct: 25 },
  { key: 'reporting', label: 'Generating report', pct: 92 },
  { key: 'complete', label: 'Complete', pct: 100 },
];

export default function ProgressBar({ jobId, onComplete }: Props) {
  const [status, setStatus] = useState('queued');
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState('Queued');
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    let cancelled = false;

    pollResults(jobId, (result) => {
      if (cancelled) return;
      setStatus(result.status);
      setProgress(result.progress ?? 0);
      setPhase(result.phase ?? '');
      if (result.status === 'failed' || result.status === 'error') {
        setError(result.error || 'Analysis failed');
      }
    })
      .then((result) => {
        if (!cancelled) {
          void onCompleteRef.current(result);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Analysis failed');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const pct = status === 'complete' ? 100 : Math.max(0, Math.min(100, Math.round(progress)));
  // Index of the step currently running (-1 while still queued).
  const activeIndex = STEPS.reduce((acc, step, i) => (pct >= step.pct ? i : acc), -1);

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
            <span>{phase || STEPS[activeIndex]?.label || 'Queued'}</span>
            <span>Job {jobId.slice(0, 8)}</span>
          </div>
          <Progress value={pct} />
        </div>

        <ol className="grid gap-3 sm:grid-cols-4">
          {STEPS.map((step, i) => {
            const done = i < activeIndex || pct >= 100;
            const active = i === activeIndex && !done;
            return (
              <li
                key={step.key}
                aria-current={active ? 'step' : undefined}
                className={cn(
                  'rounded-lg border p-3 transition-colors duration-300',
                  active
                    ? 'border-primary bg-primary/10'
                    : done
                      ? 'border-primary/40 bg-muted/20'
                      : 'border-border bg-muted/20',
                )}
              >
                <div className="mb-2 flex items-center gap-2">
                  {active ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : (
                    <CheckCircle2
                      className={cn(
                        'size-4 transition-colors duration-300',
                        done ? 'text-primary' : 'text-muted-foreground/40',
                      )}
                    />
                  )}
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
                    {step.pct}%
                  </span>
                </div>
                <p
                  className={cn(
                    'text-sm',
                    done || active ? 'text-foreground' : 'text-muted-foreground',
                    active && 'font-medium',
                  )}
                >
                  {step.label}
                </p>
              </li>
            );
          })}
        </ol>

        <p className="text-sm text-muted-foreground">
          Running clone, static analysis, git mining, and report generation. Most
          scans complete in 2 to 5 minutes.
        </p>
      </CardContent>
    </Card>
  );
}
