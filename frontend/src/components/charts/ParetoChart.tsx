'use client';

import { useEffect, useState } from 'react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts';

import { ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart';
import { formatUsd, formatUsdCompact } from '@/lib/format';

const MAX_BARS = 20;

export interface ParetoItem {
  file?: string;
  function?: string;
  cost_usd?: number;
  principal?: boolean;
}

export interface ParetoRow {
  rank: number;
  name: string;
  full: string;
  cost: number;
  cumulativePct: number;
}

export interface ParetoStats {
  rows: ParetoRow[];
  total: number;
  /** Items needed to reach 80% of total cost, or null if beyond the shown rows. */
  countFor80: number | null;
  /** Share of total cost removed by the top `n` items (0-100). */
  shareOfTop: (n: number) => number;
}

function cleanPath(value?: string | null): string {
  return (value ?? '').replace(/\\/g, '/').replace(/:$/, '');
}

function shorten(value: string, max = 14): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

/** Rank principal items by cost and compute the cumulative-share curve. */
export function paretoStats(items: ParetoItem[], limit = MAX_BARS): ParetoStats {
  const sorted = items
    .filter((i) => i.principal !== false && (i.cost_usd ?? 0) > 0)
    .sort((a, b) => (b.cost_usd ?? 0) - (a.cost_usd ?? 0));
  const total = sorted.reduce((sum, i) => sum + (i.cost_usd ?? 0), 0);

  let running = 0;
  const cumulative = sorted.map((i) => {
    running += i.cost_usd ?? 0;
    return total > 0 ? (running / total) * 100 : 0;
  });

  const rows: ParetoRow[] = sorted.slice(0, limit).map((i, idx) => {
    const path = cleanPath(i.file);
    const base = path.split('/').filter(Boolean).pop() ?? path;
    const full = [path, i.function].filter(Boolean).join(' · ') || 'Unknown item';
    return {
      rank: idx + 1,
      name: i.function || base || `Item ${idx + 1}`,
      full,
      cost: Math.round(i.cost_usd ?? 0),
      cumulativePct: Math.round(cumulative[idx] * 10) / 10,
    };
  });

  const hit80 = rows.findIndex((r) => r.cumulativePct >= 80);
  return {
    rows,
    total,
    countFor80: hit80 >= 0 ? hit80 + 1 : null,
    shareOfTop: (n) => (n <= 0 || cumulative.length === 0 ? 0 : cumulative[Math.min(n, cumulative.length) - 1]),
  };
}

const config: ChartConfig = {
  cost: { label: 'Item cost', color: 'var(--chart-1)' },
  cumulativePct: { label: 'Cumulative share', color: 'var(--chart-2)' },
};

function useIsNarrow(maxWidth = 640): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [maxWidth]);
  return narrow;
}

/** Pareto (80/20): top items by cost as bars, cumulative share as a line. */
export function ParetoChart({ items }: { items: ParetoItem[] }) {
  const narrow = useIsNarrow();
  const { rows, total, countFor80, shareOfTop } = paretoStats(items);

  if (rows.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        No costed debt items available.
      </div>
    );
  }

  const caption =
    countFor80 !== null
      ? `Fixing the top ${countFor80} ${countFor80 === 1 ? 'item' : 'items'} removes ${Math.round(
          shareOfTop(countFor80),
        )}% of the cost.`
      : `Fixing the top ${rows.length} ${rows.length === 1 ? 'item' : 'items'} removes ${Math.round(
          shareOfTop(rows.length),
        )}% of the cost.`;

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-foreground">{caption}</p>
      <ChartContainer
        config={config}
        className="aspect-auto h-72 w-full"
        role="img"
        aria-label={`Pareto chart of the top ${rows.length} debt items by cost out of ${formatUsd(
          total,
        )} total. ${caption}`}
      >
        <ComposedChart data={rows} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={narrow ? 'rank' : 'name'}
            interval={0}
            tickLine={false}
            axisLine={false}
            angle={narrow ? 0 : -45}
            textAnchor={narrow ? 'middle' : 'end'}
            height={narrow ? 24 : 72}
            tick={{ fontSize: 10 }}
            tickFormatter={(v: string | number) => (narrow ? `${v}` : shorten(String(v)))}
          />
          <YAxis
            yAxisId="left"
            tickLine={false}
            axisLine={false}
            width={narrow ? 40 : 52}
            tickFormatter={(v: number) => formatUsdCompact(v)}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            ticks={[0, 25, 50, 80, 100]}
            tickLine={false}
            axisLine={false}
            width={narrow ? 34 : 40}
            tickFormatter={(v: number) => `${v}%`}
          />
          <ChartTooltip
            cursor={{ fill: 'var(--muted)', fillOpacity: 0.4 }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as ParetoRow | undefined;
              if (!active || !row) return null;
              return (
                <div className="max-w-[16rem] rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
                  <p className="break-all font-medium text-foreground">
                    #{row.rank} {row.full}
                  </p>
                  <p className="tabular mt-1 font-mono text-sm font-semibold text-foreground">
                    {formatUsd(row.cost)}
                  </p>
                  <p className="tabular text-muted-foreground">
                    {row.cumulativePct.toFixed(0)}% of total cost cumulatively
                  </p>
                </div>
              );
            }}
          />
          <ReferenceLine
            yAxisId="right"
            y={80}
            stroke="var(--muted-foreground)"
            strokeDasharray="4 4"
            label={{
              value: '80%',
              position: 'insideTopLeft',
              fill: 'var(--muted-foreground)',
              fontSize: 10,
            }}
          />
          <Bar
            yAxisId="left"
            dataKey="cost"
            fill="var(--color-cost)"
            radius={[3, 3, 0, 0]}
            isAnimationActive={false}
          />
          <Line
            yAxisId="right"
            dataKey="cumulativePct"
            type="monotone"
            stroke="var(--color-cumulativePct)"
            strokeWidth={2}
            dot={{ r: 2.5, fill: 'var(--color-cumulativePct)' }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ChartContainer>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2 rounded-[2px] bg-[var(--chart-1)]" />
          Cost per item (left axis)
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-0.5 w-3 bg-[var(--chart-2)]" />
          Cumulative share of total (right axis)
        </span>
        {narrow && <span>Bars are ranked 1-{rows.length}; tap a bar for the file.</span>}
      </div>

      <table className="sr-only">
        <caption>Top debt items by cost</caption>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Item</th>
            <th>Cost</th>
            <th>Cumulative share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.rank}>
              <td>{r.rank}</td>
              <td>{r.full}</td>
              <td>{formatUsd(r.cost)}</td>
              <td>{r.cumulativePct.toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
