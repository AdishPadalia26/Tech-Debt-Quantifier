'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type DebugJob = {
  job_id: string;
  status: string;
  url?: string;
};

export default function DebugIndexPage() {
  const [jobId, setJobId] = useState('');
  const [jobs, setJobs] = useState<DebugJob[]>([]);

  useEffect(() => {
    fetch(`${API}/jobs`).then(r => r.json()).then(d => setJobs(d.jobs || [])).catch(() => {});
  }, []);

  return (
    <div className="w-full min-w-0 text-foreground">
      <h1 className="text-2xl font-bold mb-4">Debug Results</h1>

      <div className="mb-6">
        <input
          value={jobId}
          onChange={e => setJobId(e.target.value)}
          placeholder="Enter job_id"
          className="bg-card border border-border rounded px-3 py-2 text-sm w-96 mr-2"
        />
        <Link
          href={`/debug/${jobId}`}
          className="bg-primary hover:bg-primary/90 px-4 py-2 rounded text-sm text-primary-foreground"
        >
          Inspect
        </Link>
      </div>

      {jobs.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-2 text-primary">Recent Jobs</h2>
          {jobs.map(j => (
            <div key={j.job_id} className="mb-1">
              <Link href={`/debug/${j.job_id}`} className="text-info hover:underline text-sm">
                {j.job_id}
              </Link>
              <span className="ml-2 text-muted-foreground text-sm">{j.status} — {j.url}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
