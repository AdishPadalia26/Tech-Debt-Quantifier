'use client';

import { categoryColor, categoryLabel } from '@/lib/categories';
import { formatHours, formatUsd } from '@/lib/format';
import { CostByCategory } from '@/types';

interface Props {
  costByCategory?: Record<string, CostByCategory>;
}

/**
 * Ranked horizontal bars: categories are compared by magnitude, which bars
 * show more accurately than pie/donut slices, and every value stays visible.
 */
export default function CostBreakdownChart({ costByCategory = {} }: Props) {
  const data = Object.entries(costByCategory)
    .filter(([, v]) => v && typeof v === 'object' && (v.cost_usd ?? 0) > 0)
    .map(([key, value]) => ({
      key,
      name: categoryLabel(key),
      color: categoryColor(key),
      cost: value.cost_usd ?? 0,
      hours: value.hours ?? 0,
      items: value.item_count ?? 0,
    }))
    .sort((a, b) => b.cost - a.cost);

  const total = data.reduce((sum, d) => sum + d.cost, 0);
  const max = data[0]?.cost ?? 0;

  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-6">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-foreground">Cost by category</h2>
        <p className="tabular text-sm text-muted-foreground">{formatUsd(total)} total</p>
      </div>

      {data.length === 0 ? (
        <p className="text-sm text-muted-foreground">No categorized cost for this scan.</p>
      ) : (
        <ul className="space-y-4">
          {data.map((d) => {
            const share = total > 0 ? (d.cost / total) * 100 : 0;
            return (
              <li key={d.key}>
                <div className="tabular mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-foreground">{d.name}</span>
                  <span className="shrink-0 font-medium text-foreground">
                    {formatUsd(d.cost)}
                    <span className="ml-2 w-12 font-normal text-muted-foreground">
                      {share.toFixed(0)}%
                    </span>
                  </span>
                </div>
                <div
                  className="h-2 overflow-hidden rounded-full bg-muted"
                  role="img"
                  aria-label={`${d.name}: ${formatUsd(d.cost)}, ${share.toFixed(1)}% of total`}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${max > 0 ? Math.max((d.cost / max) * 100, 1) : 0}%`,
                      backgroundColor: d.color,
                    }}
                  />
                </div>
                <p className="tabular mt-1 text-xs text-muted-foreground">
                  {d.items.toLocaleString()} findings · {formatHours(d.hours)}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
