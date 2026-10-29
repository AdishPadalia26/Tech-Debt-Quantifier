'use client';

import { Cell, Pie, PieChart } from 'recharts';

import { ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart';
import { categoryColor, categoryLabel } from '@/lib/categories';
import { formatHours, formatUsd, formatUsdCompact } from '@/lib/format';
import { CostByCategory } from '@/types';

interface Props {
  costByCategory?: Record<string, CostByCategory>;
}

interface Slice {
  key: string;
  label: string;
  color: string;
  cost: number;
  hours: number;
  share: number;
}

function buildSlices(costByCategory: Record<string, CostByCategory>): {
  slices: Slice[];
  total: number;
} {
  const rows = Object.entries(costByCategory)
    .filter(([, v]) => v && typeof v === 'object')
    .map(([key, v]) => ({
      key,
      label: categoryLabel(key),
      color: categoryColor(key),
      cost: Math.max(v.cost_usd ?? 0, 0),
      hours: v.hours ?? 0,
    }));
  const total = rows.reduce((sum, r) => sum + r.cost, 0);
  const slices = rows
    .map((r) => ({ ...r, share: total > 0 ? (r.cost / total) * 100 : 0 }))
    .sort((a, b) => b.cost - a.cost);
  return { slices, total };
}

/** Donut of cost by category with a $ / % legend that lists every category. */
export function CostCategoryDonut({ costByCategory = {} }: Props) {
  const { slices, total } = buildSlices(costByCategory);
  const visible = slices.filter((s) => s.cost > 0);

  if (visible.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        No category data available
      </div>
    );
  }

  const config: ChartConfig = Object.fromEntries(
    slices.map((s) => [s.key, { label: s.label, color: s.color }]),
  );

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative h-56 w-full">
        <ChartContainer
          config={config}
          className="aspect-auto h-full w-full"
          role="img"
          aria-label={`Cost by category, ${formatUsd(total)} total. ${visible
            .map((s) => `${s.label} ${formatUsd(s.cost)}, ${s.share.toFixed(0)}%`)
            .join('; ')}`}
        >
          <PieChart>
            <Pie
              data={visible}
              dataKey="cost"
              nameKey="label"
              innerRadius={64}
              outerRadius={100}
              paddingAngle={visible.length > 1 ? 3 : 0}
              stroke="var(--card)"
              strokeWidth={2}
            >
              {visible.map((s) => (
                <Cell key={s.key} fill={s.color} />
              ))}
            </Pie>
            <ChartTooltip
              content={({ active, payload }) => {
                const slice = payload?.[0]?.payload as Slice | undefined;
                if (!active || !slice) return null;
                return (
                  <div className="min-w-[10rem] rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
                    <p className="flex items-center gap-2 font-medium text-foreground">
                      <span
                        aria-hidden
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: slice.color }}
                      />
                      {slice.label}
                    </p>
                    <p className="tabular mt-1 font-mono text-sm font-semibold text-foreground">
                      {formatUsd(slice.cost)}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {slice.share.toFixed(1)}% of total
                      </span>
                    </p>
                    <p className="tabular mt-0.5 text-muted-foreground">
                      {formatHours(slice.hours)} of work
                    </p>
                  </div>
                );
              }}
            />
          </PieChart>
        </ChartContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Total
          </span>
          <span className="tabular font-mono text-xl font-semibold text-foreground">
            {formatUsdCompact(total)}
          </span>
        </div>
      </div>

      <ul className="w-full space-y-1.5 text-sm" aria-label="Cost by category legend">
        {slices.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="min-w-0 flex-1 truncate text-foreground">{s.label}</span>
            <span className="tabular font-mono text-foreground">
              {s.cost > 0 ? formatUsd(s.cost) : '$0'}
            </span>
            <span className="tabular w-12 text-right text-xs text-muted-foreground">
              {s.cost > 0 ? `${s.share.toFixed(s.share < 1 ? 1 : 0)}%` : '0%'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
