'use client';

import Link from 'next/link';
import { useMemo } from 'react';

import ActiveDebtChart from '@/components/ActiveDebtChart';
import DebtTrendChart from '@/components/DebtTrendChart';
import RepositoryInsightsPanel from '@/components/RepositoryInsightsPanel';
import ScanComparisonPanel from '@/components/ScanComparisonPanel';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import { useRepositoryInsights } from '@/hooks/useRepositoryInsights';
import { normalizeRepoUrl } from '@/lib/routes';

interface Props {
  params: { repo: string[] };
}

export default function RepositoryDetailPage({ params }: Props) {
  const repoUrl = useMemo(
    () => normalizeRepoUrl(`github.com/${params.repo.join('/')}`),
    [params.repo]
  );
  const { history, summary, richTrend, unresolved, comparison, loading, error } =
    useRepositoryInsights(repoUrl, 10);

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
        <div className="max-w-6xl mx-auto text-gray-400">Loading repository details...</div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
        <div className="max-w-6xl mx-auto space-y-4">
          <p className="text-red-400">{error}</p>
          <Link href="/portfolio" className="text-purple-400 hover:text-purple-300">
            Back to Portfolio
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-gray-500 text-sm uppercase tracking-wider mb-1">
              Repository Detail
            </p>
            <h1 className="text-3xl font-bold text-white">
              {params.repo.join('/')}
            </h1>
            <a
              href={repoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-purple-400 hover:text-purple-300 text-sm"
            >
              Open on GitHub
            </a>
          </div>
          <div className="flex gap-3">
            <Link href="/" className="text-sm text-gray-400 hover:text-white">
              Back to Scanner
            </Link>
            <Link href="/portfolio" className="text-sm text-purple-400 hover:text-purple-300">
              Back to Portfolio
            </Link>
          </div>
        </div>

        {summary && <RepositoryInsightsPanel summary={summary} />}

        {comparison && <ScanComparisonPanel comparison={comparison} />}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {history && (
            <DebtTrendChart
              trend={history.trend}
              currentCost={summary?.total_cost_usd}
            />
          )}
          {richTrend && <ActiveDebtChart points={richTrend.active_trend} />}
        </div>

        {unresolved && <UnresolvedFindingsList findings={unresolved.items} />}

        {history && history.scans.length > 0 && (
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">Recent Scans</h3>
                <p className="text-gray-400 text-sm">
                  Navigate directly into scan-level findings and roadmap data
                </p>
              </div>
              <p className="text-gray-500 text-sm">{history.scans.length} scans</p>
            </div>
            <div className="space-y-3">
              {history.scans.slice(0, 6).map((scan) => (
                <div
                  key={scan.scan_id}
                  className="bg-gray-900/60 rounded-lg p-4 border border-gray-700 flex flex-wrap items-center justify-between gap-4"
                >
                  <div>
                    <p className="text-white font-medium">{scan.date_display}</p>
                    <p className="text-gray-500 text-sm">
                      Score {scan.debt_score.toFixed(1)} · ${Math.round(scan.total_cost).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-gray-400">{scan.total_hours.toFixed(1)}h</span>
                    <Link
                      href={`/scans/${scan.scan_id}`}
                      className="text-purple-400 hover:text-purple-300"
                    >
                      Open scan
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {richTrend && (
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">
              Category Movement
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(richTrend.category_deltas).map(([category, delta]) => (
                <div
                  key={category}
                  className="bg-gray-900/60 rounded-lg p-4 border border-gray-700"
                >
                  <p className="text-white font-medium capitalize">
                    {category.replace(/_/g, ' ')}
                  </p>
                  <p className="text-gray-400 text-sm mt-1">
                    Count delta: {delta.count_delta > 0 ? '+' : ''}
                    {delta.count_delta}
                  </p>
                  <p
                    className={`text-sm mt-2 ${
                      delta.cost_delta_usd > 0
                        ? 'text-red-400'
                        : delta.cost_delta_usd < 0
                        ? 'text-green-400'
                        : 'text-gray-400'
                    }`}
                  >
                    Cost delta: {delta.cost_delta_usd > 0 ? '+' : ''}$
                    {Math.round(delta.cost_delta_usd).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
