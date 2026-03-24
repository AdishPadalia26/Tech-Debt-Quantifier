'use client';
import { useEffect, useState } from 'react';
import { pollResults } from '@/lib/api';
import { JobResult } from '@/types';

interface Props {
  jobId: string;
  onComplete: (result: JobResult) => void;
}

const STEPS = [
  { key: 'queued',    label: 'Queued',              pct: 5  },
  { key: 'running',   label: 'Cloning repository',  pct: 20 },
  { key: 'analyzing', label: 'Running analysis',    pct: 60 },
  { key: 'reporting', label: 'Generating report',   pct: 85 },
  { key: 'complete',  label: 'Complete',            pct: 100},
];

export default function ProgressBar({ jobId, onComplete }: Props) {
  const [status, setStatus] = useState('queued');
  const [error, setError] = useState('');

  useEffect(() => {
    pollResults(
      jobId,
      (result) => {
        setStatus(result.status);
        if (result.status === 'failed') {
          setError(result.error || 'Analysis failed');
        }
      }
    )
    .then(onComplete)
    .catch((err) => setError(err.message));
  }, [jobId, onComplete]);

  const currentStep = STEPS.find(s => s.key === status) || STEPS[0];
  const pct = currentStep.pct;

  if (error) {
    return (
      <div className="p-4 bg-red-900/30 border border-red-500 rounded-lg">
        <p className="text-red-400">❌ {error}</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <div className="flex justify-between text-sm text-gray-400">
        <span>{currentStep.label}...</span>
        <span>{pct}%</span>
      </div>
      
      {/* Progress bar */}
      <div className="w-full bg-gray-700 rounded-full h-2">
        <div
          className="bg-purple-500 h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Step indicators */}
      <div className="flex justify-between">
        {STEPS.filter(s => s.key !== 'queued').map((step) => {
          const done = STEPS.indexOf(currentStep) >= STEPS.indexOf(step);
          return (
            <div key={step.key} className="flex flex-col items-center gap-1">
              <div className={`w-3 h-3 rounded-full ${
                done ? 'bg-purple-500' : 'bg-gray-600'
              }`} />
              <span className="text-xs text-gray-500">{step.label}</span>
            </div>
          );
        })}
      </div>

      <p className="text-center text-sm text-gray-400 animate-pulse">
        This takes 2–5 minutes for a full analysis...
      </p>
    </div>
  );
}
