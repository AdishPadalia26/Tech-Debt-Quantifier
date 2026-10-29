'use client';

import { formatHours, formatUsd, severityChip } from '@/lib/format';
import { ScanRoadmapResponse } from '@/types';

interface Props {
  roadmap: ScanRoadmapResponse['roadmap'];
}

const BUCKETS: Record<string, { title: string; hint: string }> = {
  quick_wins: { title: 'Quick wins', hint: 'Low effort, do this sprint' },
  next_up: { title: 'Next up', hint: 'Plan for the next few sprints' },
  strategic: { title: 'Strategic', hint: 'Larger refactors to schedule' },
};

export default function RoadmapBoard({ roadmap }: Props) {
  const buckets = Object.entries(roadmap);

  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-6">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-foreground">Remediation roadmap</h2>
        <p className="text-sm text-muted-foreground">Findings grouped by when to tackle them</p>
      </div>

      {buckets.length === 0 ? (
        <p className="text-sm text-muted-foreground">No roadmap data available.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:gap-0 lg:divide-x lg:divide-border">
          {buckets.map(([bucket, items]) => (
            <div key={bucket} className="min-w-0 lg:px-5 lg:first:pl-0 lg:last:pr-0">
              <div className="mb-3 flex items-baseline justify-between gap-2">
                <div>
                  <h3 className="font-medium text-foreground">
                    {BUCKETS[bucket]?.title || bucket}
                  </h3>
                  {BUCKETS[bucket] && (
                    <p className="text-xs text-muted-foreground">{BUCKETS[bucket].hint}</p>
                  )}
                </div>
                <span className="tabular text-xs text-muted-foreground">{items.length} items</span>
              </div>
              <ul className="divide-y divide-border">
                {items.slice(0, 4).map((item) => (
                  <li key={`${bucket}-${item.finding_id}`} className="py-3 first:pt-0">
                    <p className="text-sm font-medium text-foreground [overflow-wrap:anywhere]">{item.title}</p>
                    <p className="mt-0.5 break-all font-mono text-xs text-muted-foreground">
                      {item.file_path}
                    </p>
                    <div className="tabular mt-2 flex flex-wrap items-center gap-3 text-xs">
                      <span className="font-medium text-foreground">{formatUsd(item.cost_usd)}</span>
                      <span className="text-muted-foreground">{formatHours(item.effort_hours)}</span>
                      <span
                        className={`rounded-full px-1.5 py-0.5 capitalize ${severityChip(item.severity)}`}
                      >
                        {item.severity}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              {items.length > 4 && (
                <p className="tabular pt-1 text-xs text-muted-foreground">
                  +{items.length - 4} more
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
