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
      <div className="w-full min-w-0">
        <div className="max-w-6xl mx-auto text-muted-foreground">Loading repository details...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-w-0">
        <div className="max-w-6xl mx-auto space-y-4">
          <p className="text-danger">{error}</p>
          <Link href="/portfolio" className="text-primary hover:text-accent-foreground">
            Back to Portfolio
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-w-0">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-muted-foreground text-sm uppercase tracking-wider mb-1">
              Repository Detail
            </p>
            <h1 className="text-3xl font-bold text-foreground">
              {params.repo.join('/')}
            </h1>
            <a
              href={repoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:text-accent-foreground text-sm"
            >
              Open on GitHub
            </a>
          </div>
          <div className="flex gap-3">
            <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
              Back to Scanner
            </Link>
            <Link href="/portfolio" className="text-sm text-primary hover:text-accent-foreground">
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
          {richTrend?.active_trend && <ActiveDebtChart points={richTrend.active_trend} />}
        </div>

        {unresolved && <UnresolvedFindingsList findings={unresolved.items} />}

        {history && history.scans.length > 0 && (
          <div className="bg-surface-raised rounded-xl p-6 border border-border">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Recent Scans</h3>
                <p className="text-muted-foreground text-sm">
                  Navigate directly into scan-level findings and roadmap data
                </p>
              </div>
              <p className="text-muted-foreground text-sm">{history.scans.length} scans</p>
            </div>
            <div className="space-y-3">
              {history.scans.slice(0, 6).map((scan, idx) => {
                const nextScan = history.scans[idx + 1];
                return (
                  <div
                    key={scan.scan_id}
                    className="bg-card rounded-lg p-4 border border-border flex flex-wrap items-center justify-between gap-4"
                  >
                    <div>
                      <p className="text-foreground font-medium">{scan.date_display}</p>
                      <p className="text-muted-foreground text-sm">
                        Score {scan.debt_score.toFixed(1)} · ${Math.round(scan.total_cost).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-muted-foreground">{scan.total_hours.toFixed(1)}h</span>
                      {nextScan && (
                        <Link
                          href={`/compare/${nextScan.scan_id}/${scan.scan_id}`}
                          className="text-warning hover:text-warning"
                        >
                          Compare with previous
                        </Link>
                      )}
                      <Link
                        href={`/scans/${scan.scan_id}`}
                        className="text-primary hover:text-accent-foreground"
                      >
                        Open scan
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {richTrend?.category_deltas && Object.keys(richTrend.category_deltas).length > 0 && (
          <div className="bg-surface-raised rounded-xl p-6 border border-border">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Category Movement
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(richTrend.category_deltas).map(([category, delta]) => (
                <div
                  key={category}
                  className="bg-card rounded-lg p-4 border border-border"
                >
                  <p className="text-foreground font-medium capitalize">
                    {category.replace(/_/g, ' ')}
                  </p>
                  <p className="text-muted-foreground text-sm mt-1">
                    Count delta: {delta.count_delta > 0 ? '+' : ''}
                    {delta.count_delta}
                  </p>
                  <p
                    className={`text-sm mt-2 ${
                      delta.cost_delta_usd > 0
                        ? 'text-danger'
                        : delta.cost_delta_usd < 0
                        ? 'text-success'
                        : 'text-muted-foreground'
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
    </div>
  );
}
