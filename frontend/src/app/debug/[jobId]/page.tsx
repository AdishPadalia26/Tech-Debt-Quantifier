'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function DebugResultsPage({ params }: { params: { jobId: string } }) {
  const { jobId } = params;
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API}/debug/results/${jobId}`);
        if (!res.ok) {
          setError(`Status ${res.status}: ${await res.text()}`);
          return;
        }
        const json = await res.json();
        setData(json);
      } catch (e: any) {
        setError(e.message || 'Request failed');
      }
    };
    fetchData();
  }, [jobId]);

  if (error) {
    return (
      <div className="min-h-screen bg-gray-950 text-red-400 p-6">
        <h1 className="text-xl font-bold mb-4">Debug Results</h1>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-950 text-purple-300 p-6">
        <h1 className="text-xl font-bold mb-4">Debug Results</h1>
        <p>Loading {jobId}...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <h1 className="text-2xl font-bold mb-4">
        Debug Results — {jobId}
      </h1>

      <section className="mb-6">
        <h2 className="text-lg font-semibold mb-2 text-purple-300">
          raw_analysis snapshot
        </h2>
        <pre className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-xs overflow-auto">
          {JSON.stringify({
            debt_score: data.raw_analysis?.debt_score,
            total_cost_usd: data.raw_analysis?.total_cost_usd,
            total_remediation_hours: data.raw_analysis?.total_remediation_hours,
            cost_by_category: data.raw_analysis?.cost_by_category,
          }, null, 2)}
        </pre>
      </section>

      <section className="mb-6">
        <h2 className="text-lg font-semibold mb-2 text-purple-300">
          first priority_action
        </h2>
        <pre className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-xs overflow-auto">
          {JSON.stringify((data.priority_actions || []), null, 2)}
        </pre>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-2 text-purple-300">
          full JSON
        </h2>
        <pre className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-xs overflow-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      </section>
    </div>
  );
}
