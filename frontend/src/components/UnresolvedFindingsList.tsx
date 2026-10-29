'use client';

import { formatHours, formatUsd, humanize, severityChip } from '@/lib/format';
import { StructuredFinding } from '@/types';

interface Props {
  findings: StructuredFinding[];
  title?: string;
}

export default function UnresolvedFindingsList({
  findings,
  title = 'Top unresolved findings',
}: Props) {
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          <p className="text-sm text-muted-foreground">
            Highest-priority unresolved work, ranked by cost and severity
          </p>
        </div>
        <p className="tabular text-sm text-muted-foreground">{findings.length} shown</p>
      </div>

      {findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">No unresolved findings. Nice.</p>
      ) : (
        <ul className="divide-y divide-border">
          {findings.map((finding) => (
            <li key={finding.id} className="py-3 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-foreground">
                    {humanize(finding.subcategory || finding.category)}
                    <span className="font-normal text-muted-foreground">
                      {' '}in {finding.module || 'root'}
                    </span>
                  </p>
                  <p className="mt-0.5 break-all font-mono text-xs text-muted-foreground">
                    {finding.file_path}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${severityChip(
                    finding.severity
                  )}`}
                >
                  {finding.severity}
                </span>
              </div>
              <dl className="tabular mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                <div className="flex gap-1">
                  <dt className="sr-only">Cost</dt>
                  <dd className="font-medium text-foreground">{formatUsd(finding.cost_usd)}</dd>
                </div>
                <div className="flex gap-1">
                  <dt className="sr-only">Effort</dt>
                  <dd className="text-muted-foreground">{formatHours(finding.effort_hours)}</dd>
                </div>
                <div className="flex gap-1 text-muted-foreground">
                  <dt>Impact</dt>
                  <dd className="capitalize">{finding.business_impact || 'n/a'}</dd>
                </div>
                <div className="flex gap-1 text-muted-foreground">
                  <dt>Confidence</dt>
                  <dd>{Math.round((finding.confidence || 0) * 100)}%</dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
