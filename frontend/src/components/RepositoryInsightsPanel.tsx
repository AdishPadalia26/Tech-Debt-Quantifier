'use client';

import { RepoSummaryRollup } from '@/types';

interface Props {
  summary: RepoSummaryRollup;
}

function metricTone(value: number) {
  if (value > 0) return 'text-danger';
  if (value < 0) return 'text-success';
  return 'text-muted-foreground';
}

export default function RepositoryInsightsPanel({ summary }: Props) {
  const changes = summary.changes;
  const topModule = summary.top_modules[0];
  const ownership = summary.ownership_summary;

  return (
    <div className="bg-surface-raised rounded-xl p-6 border border-border">
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h3 className="text-lg font-semibold text-foreground">Repository Signals</h3>
          <p className="text-muted-foreground text-sm">
            Triage posture, ownership concentration, and latest scan deltas
          </p>
        </div>
        <div className="text-right">
          <p className="text-foreground font-semibold">
            {summary.finding_count} findings across {summary.module_count} modules
          </p>
          <p className="text-muted-foreground text-sm">
            {summary.quick_wins} quick wins · {summary.strategic_items} strategic items
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-5">
        <div className="bg-card rounded-lg p-4 border border-border">
          <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
            Active
          </p>
          <p className="text-2xl font-bold text-foreground">
            {summary.triage.active_findings}
          </p>
          <p className="text-muted-foreground text-xs">Open findings</p>
        </div>
        <div className="bg-card rounded-lg p-4 border border-border">
          <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
            Reviewed
          </p>
          <p className="text-2xl font-bold text-foreground">
            {summary.triage.reviewed_findings}
          </p>
          <p className="text-muted-foreground text-xs">
            {summary.triage.review_rate.toFixed(1)}% review rate
          </p>
        </div>
        <div className="bg-card rounded-lg p-4 border border-border">
          <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
            Suppressed
          </p>
          <p className="text-2xl font-bold text-foreground">
            {summary.triage.suppressed_findings}
          </p>
          <p className="text-muted-foreground text-xs">
            {summary.triage.suppression_rate.toFixed(1)}% suppression rate
          </p>
        </div>
        <div className="bg-card rounded-lg p-4 border border-border">
          <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
            Contributors
          </p>
          <p className="text-2xl font-bold text-foreground">
            {ownership?.unique_contributors ?? 0}
          </p>
          <p className="text-muted-foreground text-xs">
            bus factor {ownership?.bus_factor ?? 0}
          </p>
        </div>
        <div className="bg-card rounded-lg p-4 border border-border">
          <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
            Ownership
          </p>
          <p className="text-lg font-semibold text-foreground truncate">
            {topModule?.module || 'N/A'}
          </p>
          <p className="text-muted-foreground text-xs">
            {topModule?.ownership_risk || 'n/a'} risk ·{' '}
            {topModule?.owner_count ?? 0} owners
          </p>
        </div>
      </div>

      {changes && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card rounded-lg p-4 border border-border">
            <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
              New Debt
            </p>
            <p className="text-2xl font-bold text-foreground">{changes.new_debt.count}</p>
            <p className="text-muted-foreground text-xs">
              ${Math.round(changes.new_debt.cost_usd).toLocaleString()}
            </p>
          </div>
          <div className="bg-card rounded-lg p-4 border border-border">
            <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
              Resolved
            </p>
            <p className="text-2xl font-bold text-foreground">{changes.resolved_debt.count}</p>
            <p className="text-muted-foreground text-xs">
              ${Math.round(changes.resolved_debt.cost_usd).toLocaleString()}
            </p>
          </div>
          <div className="bg-card rounded-lg p-4 border border-border">
            <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
              Cost Delta
            </p>
            <p className={`text-2xl font-bold ${metricTone(changes.summary.cost_delta_usd)}`}>
              {changes.summary.cost_delta_usd > 0 ? '+' : ''}
              ${Math.round(changes.summary.cost_delta_usd).toLocaleString()}
            </p>
            <p className="text-muted-foreground text-xs">vs previous scan</p>
          </div>
          <div className="bg-card rounded-lg p-4 border border-border">
            <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">
              Score Delta
            </p>
            <p className={`text-2xl font-bold ${metricTone(changes.summary.debt_score_delta)}`}>
              {changes.summary.debt_score_delta > 0 ? '+' : ''}
              {changes.summary.debt_score_delta.toFixed(1)}
            </p>
            <p className="text-muted-foreground text-xs">
              {changes.severity_worsened.length} worsened · {changes.severity_improved.length} improved
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
