'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';

import CostBreakdownChart from '@/components/CostBreakdownChart';
import DebtScoreCard from '@/components/DebtScoreCard';
import { EstimateQuality } from '@/components/analyze/EstimateQuality';
import { HeadlineHero } from '@/components/analyze/HeadlineHero';
import { ViewModeToggle, useViewMode } from '@/components/analyze/ViewModeToggle';
import ModuleRiskList from '@/components/ModuleRiskList';
import PriorityActions from '@/components/PriorityActions';
import RoadmapBoard from '@/components/RoadmapBoard';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import {
  getScanDetail,
  getScanFindings,
  getScanModules,
  getScanRoadmap,
  getScanSummary,
} from '@/lib/api';
import { repoDetailPath } from '@/lib/routes';
import { cn } from '@/lib/utils';
import {
  ScanDetailResponse,
  ScanFindingsResponse,
  ScanModulesResponse,
  ScanRoadmapResponse,
  ScanSummaryResponse,
} from '@/types';

interface Props {
  params: { scanId: string };
}

function SectionSkeleton({ className = 'h-48' }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-card ${className}`} />;
}

function repoNameFrom(detail: ScanDetailResponse | null): string | null {
  const raw = detail?.raw_result as { github_url?: string; repo_id?: string } | undefined;
  const url = detail?.github_url ?? raw?.github_url;
  if (url) return url.split('/').slice(-2).join('/');
  return detail?.repo_id ?? raw?.repo_id ?? null;
}

export default function ScanDetailPage({ params }: Props) {
  const [detail, setDetail] = useState<ScanDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [summary, setSummary] = useState<ScanSummaryResponse | null>(null);
  const [modules, setModules] = useState<ScanModulesResponse | null>(null);
  const [roadmap, setRoadmap] = useState<ScanRoadmapResponse | null>(null);
  const [findings, setFindings] = useState<ScanFindingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useViewMode();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDetailLoading(true);
    setError('');

    // Fast, small endpoints render the page; the heavy detail payload
    // (executive summary, priority actions) fills in when it arrives.
    Promise.all([
      getScanSummary(params.scanId),
      getScanModules(params.scanId).catch(() => null),
      getScanRoadmap(params.scanId).catch(() => null),
      getScanFindings(params.scanId, 12).catch(() => null),
    ])
      .then(([summaryData, modulesData, roadmapData, findingsData]) => {
        if (cancelled) return;
        setSummary(summaryData);
        setModules(modulesData);
        setRoadmap(roadmapData);
        setFindings(findingsData);
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) {
          setError(
            'We couldn’t load this scan. It may have been removed, or it belongs to another account.'
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    getScanDetail(params.scanId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => console.error(err))
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [params.scanId]);

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-6xl space-y-6" aria-busy="true">
        <div className="space-y-2">
          <div className="h-4 w-24 animate-pulse rounded bg-muted" />
          <div className="h-9 w-72 animate-pulse rounded bg-muted" />
        </div>
        <SectionSkeleton className="h-36" />
        <div className="grid gap-6 xl:grid-cols-2">
          <SectionSkeleton className="h-80" />
          <SectionSkeleton className="h-80" />
        </div>
        <span className="sr-only">Loading scan</span>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="mx-auto w-full max-w-xl py-12">
        <div role="alert" className="rounded-xl border border-destructive/30 bg-card p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
            <div>
              <h1 className="font-medium text-foreground">Scan not available</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {error || 'This scan could not be found.'}
              </p>
              <Link
                href="/"
                className="mt-4 inline-block text-sm font-medium text-primary hover:text-accent-foreground"
              >
                Run a new scan
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isEngineer = viewMode === 'engineer';
  const repoName = repoNameFrom(detail);
  const repoUrl =
    detail?.github_url ??
    (detail?.raw_result as { github_url?: string } | undefined)?.github_url;
  const scannedAt = summary.created_at
    ? new Date(summary.created_at).toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : null;
  const stats = summary.summary as { files_scanned?: number; issues_found?: number };

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">Scan report</p>
          {repoName ? (
            <h1 className="truncate text-3xl font-semibold tracking-tight text-foreground">
              {repoName}
            </h1>
          ) : detailLoading ? (
            <div
              className="mt-1 h-9 w-64 animate-pulse rounded bg-muted"
              aria-label="Loading repository name"
            />
          ) : (
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              Scan report
            </h1>
          )}
          <p className="mt-1 flex flex-wrap gap-x-3 text-sm text-muted-foreground">
            {scannedAt && <span>{scannedAt}</span>}
            {typeof stats?.files_scanned === 'number' && (
              <span className="tabular">{stats.files_scanned.toLocaleString()} files</span>
            )}
            {typeof stats?.issues_found === 'number' && (
              <span className="tabular">{stats.issues_found.toLocaleString()} findings</span>
            )}
          </p>
        </div>
        {repoUrl && (
          <Link
            href={repoDetailPath(repoUrl)}
            className="rounded-lg border border-border-strong px-3 py-1.5 text-sm font-medium text-foreground hover:bg-surface-raised"
          >
            Repository history
          </Link>
        )}
      </header>

      <ViewModeToggle mode={viewMode} onChange={setViewMode} />

      <HeadlineHero
        repoName={repoName?.split('/').pop()}
        totalCost={summary.total_cost_usd}
        range={detail?.total_cost_range ?? undefined}
        hours={summary.total_hours}
      />

      <DebtScoreCard
        score={summary.debt_score}
        totalCost={summary.total_cost_usd}
        hours={summary.total_hours}
        sprints={summary.total_sprints}
      />

      {detail && (
        <EstimateQuality
          estimation_stats={detail.estimation_stats ?? undefined}
          warnings={detail.warnings ?? undefined}
          total_cost_range={detail.total_cost_range ?? undefined}
          non_principal_cost={detail.non_principal_cost ?? undefined}
          hourly_rates={detail.hourly_rates ?? undefined}
          model_version={detail.model_version ?? undefined}
        />
      )}

      {detail?.executive_summary ? (
        <section className="rounded-xl border border-border bg-card p-6">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Executive summary</h2>
          <p className="max-w-prose leading-relaxed text-foreground">
            {detail.executive_summary}
          </p>
        </section>
      ) : detailLoading ? (
        <SectionSkeleton className="h-28" />
      ) : null}

      <div
        className={cn(
          'grid min-w-0 grid-cols-1 gap-6',
          isEngineer && modules && 'xl:grid-cols-2',
        )}
      >
        <CostBreakdownChart costByCategory={summary.cost_by_category} />
        {isEngineer && modules && <ModuleRiskList modules={modules.modules} />}
      </div>

      {detail?.priority_actions ? (
        <PriorityActions actions={detail.priority_actions} roiAnalysis={detail.roi_analysis} />
      ) : detailLoading ? (
        <SectionSkeleton className="h-64" />
      ) : null}

      {roadmap && <RoadmapBoard roadmap={roadmap.roadmap} />}

      {isEngineer && findings && <UnresolvedFindingsList findings={findings.findings} title="Top findings" />}
    </div>
  );
}
