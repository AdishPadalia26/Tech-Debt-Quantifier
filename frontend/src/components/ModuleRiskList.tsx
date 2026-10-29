'use client';

import { formatHours, formatUsd, severityChip } from '@/lib/format';
import { ModuleSummaryDetail } from '@/types';

interface Props {
  modules: ModuleSummaryDetail[];
}

function ownershipTone(risk?: string | null) {
  switch (risk) {
    case 'critical':
      return 'text-severity-critical';
    case 'high':
      return 'text-severity-high';
    case 'medium':
      return 'text-severity-medium';
    default:
      return 'text-muted-foreground';
  }
}

export default function ModuleRiskList({ modules }: Props) {
  const topModules = modules.slice(0, 6);

  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Riskiest modules</h2>
          <p className="text-sm text-muted-foreground">Ranked by estimated cost</p>
        </div>
        <p className="tabular text-sm text-muted-foreground">
          {topModules.length} of {modules.length}
        </p>
      </div>

      {topModules.length === 0 ? (
        <p className="text-sm text-muted-foreground">No module summaries available.</p>
      ) : (
        <ul className="divide-y divide-border">
          {topModules.map((module) => (
            <li key={module.module} className="py-3 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 break-all font-mono text-sm text-foreground">
                  {module.module}
                </p>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${severityChip(
                    module.max_severity
                  )}`}
                >
                  {module.max_severity}
                </span>
              </div>
              <div className="tabular mt-1.5 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
                <span className="font-medium text-foreground">
                  {formatUsd(module.total_cost_usd)}
                </span>
                <span className="text-muted-foreground">
                  {module.finding_count.toLocaleString()} findings ·{' '}
                  {formatHours(module.total_effort_hours)}
                </span>
                <span className="text-muted-foreground">
                  {Math.round(module.avg_confidence * 100)}% confidence
                </span>
              </div>
              {module.ownership_risk && (
                <p className="tabular mt-1 text-xs text-muted-foreground">
                  <span className={ownershipTone(module.ownership_risk)}>
                    {module.ownership_risk} ownership risk
                  </span>
                  {' · '}
                  {module.owner_count ?? 0} owners, top contributor{' '}
                  {Math.round((module.top_contributor_share ?? 0) * 100)}%
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
