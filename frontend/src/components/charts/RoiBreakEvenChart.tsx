'use client';

import { useId } from 'react';
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from 'recharts';

import { ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart';
import { formatUsd, formatUsdCompact } from '@/lib/format';

const HORIZON_MONTHS = 36;
const TICKS = [0, 6, 12, 18, 24, 30, 36];

interface Props {
  totalFixCost?: number;
  annualSavings?: number;
  /** Backend payback estimate; used only when it can't be derived from the inputs. */
  paybackMonths?: number;
  /** 3-year ROI percentage from the backend. */
  roi3yPct?: number;
}

const config: ChartConfig = {
  net: { label: 'Cumulative net', color: 'var(--success)' },
};

/**
 * Break-even chart: cumulative net = monthly savings x month - total fix cost.
 * Red area is money still to recover, green is net gain after payback.
 */
export function RoiBreakEvenChart({
  totalFixCost = 0,
  annualSavings = 0,
  paybackMonths,
  roi3yPct,
}: Props) {
  const gradientId = useId().replace(/:/g, '');
  const fix = Math.max(totalFixCost, 0);
  const monthly = Math.max(annualSavings, 0) / 12;

  const derivedPayback = fix <= 0 ? 0 : monthly > 0 ? fix / monthly : null;
  const payback =
    derivedPayback ?? (paybackMonths && paybackMonths > 0 ? paybackMonths : null);
  const paysBack = payback !== null && payback <= HORIZON_MONTHS;

  const data = Array.from({ length: HORIZON_MONTHS + 1 }, (_, m) => ({
    month: m,
    net: Math.round(monthly * m - fix),
  }));

  const max = Math.max(...data.map((d) => d.net));
  const min = Math.min(...data.map((d) => d.net));
  // Gradient stop where the series crosses zero (0 = top of the area box).
  const zeroOffset = max <= 0 ? 0 : min >= 0 ? 1 : max / (max - min);

  const paybackText = paysBack
    ? `Break-even · month ${Math.ceil(payback)}`
    : payback !== null
      ? `Doesn't pay back within 3 years (≈ ${Math.ceil(payback)} months)`
      : "Doesn't pay back: no projected savings";

  const finalNet = data[data.length - 1].net;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <p
            className={`mb-2 inline-flex rounded-md px-2 py-1 text-xs font-medium ${
              paysBack ? 'bg-success/15 text-success' : 'bg-danger/15 text-danger'
            }`}
          >
            {paybackText}
          </p>
          <ChartContainer
            config={config}
            className="aspect-auto h-60 w-full"
            role="img"
            aria-label={`Break-even projection over 36 months. Fix cost ${formatUsd(
              fix,
            )}, savings ${formatUsd(annualSavings)} per year. ${paybackText}. Net after 36 months: ${formatUsd(
              finalNet,
            )}.`}
          >
            <AreaChart data={data} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`${gradientId}-fill`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset={zeroOffset} stopColor="var(--success)" stopOpacity={0.4} />
                  <stop offset={zeroOffset} stopColor="var(--danger)" stopOpacity={0.4} />
                </linearGradient>
                <linearGradient id={`${gradientId}-stroke`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset={zeroOffset} stopColor="var(--success)" />
                  <stop offset={zeroOffset} stopColor="var(--danger)" />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.5} />
              <XAxis
                type="number"
                dataKey="month"
                domain={[0, HORIZON_MONTHS]}
                ticks={TICKS}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `${v}`}
                label={{
                  value: 'Months',
                  position: 'insideBottomRight',
                  offset: -2,
                  fill: 'var(--muted-foreground)',
                  fontSize: 11,
                }}
                height={32}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={52}
                domain={[(min: number) => Math.min(min, 0), (max: number) => Math.max(max, 0)]}
                tickFormatter={(v: number) => formatUsdCompact(v)}
              />
              <ChartTooltip
                cursor={{ stroke: 'var(--border-strong)' }}
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as { month: number; net: number } | undefined;
                  if (!active || !point) return null;
                  const positive = point.net >= 0;
                  return (
                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
                      <p className="font-medium text-foreground">Month {point.month}</p>
                      <p
                        className={`tabular mt-1 font-mono text-sm font-semibold ${
                          positive ? 'text-success' : 'text-danger'
                        }`}
                      >
                        {point.net < 0 ? '-' : '+'}
                        {formatUsd(Math.abs(point.net))}
                      </p>
                      <p className="text-muted-foreground">
                        {positive ? 'Net gain after fix cost' : 'Still to recover'}
                      </p>
                    </div>
                  );
                }}
              />
              <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
              {paysBack && payback! > 0 && (
                <ReferenceLine
                  x={payback!}
                  stroke="var(--foreground)"
                  strokeDasharray="4 4"
                  label={{
                    value: paybackText,
                    position: payback! > HORIZON_MONTHS / 2 ? 'insideTopLeft' : 'insideTopRight',
                    fill: 'var(--foreground)',
                    fontSize: 11,
                  }}
                />
              )}
              <Area
                type="linear"
                dataKey="net"
                stroke={`url(#${gradientId}-stroke)`}
                strokeWidth={2.5}
                fill={`url(#${gradientId}-fill)`}
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ChartContainer>
        </div>

        <dl className="tabular grid shrink-0 grid-cols-2 gap-3 text-sm sm:w-40 sm:grid-cols-1">
          <div className="rounded-lg border border-border bg-muted/20 p-3">
            <dt className="text-xs text-muted-foreground">3-year ROI</dt>
            <dd
              className={`mt-1 font-mono text-xl font-semibold ${
                (roi3yPct ?? 0) < 0 ? 'text-danger' : 'text-success'
              }`}
            >
              {typeof roi3yPct === 'number' ? `${Math.round(roi3yPct)}%` : 'N/A'}
            </dd>
          </div>
          <div className="rounded-lg border border-border bg-muted/20 p-3">
            <dt className="text-xs text-muted-foreground">Net after 3 years</dt>
            <dd
              className={`mt-1 font-mono text-xl font-semibold ${
                finalNet < 0 ? 'text-danger' : 'text-success'
              }`}
            >
              {finalNet < 0 ? '-' : ''}
              {formatUsdCompact(Math.abs(finalNet))}
            </dd>
          </div>
        </dl>
      </div>
      <p className="text-xs text-muted-foreground">Projection assumes constant savings.</p>
    </div>
  );
}
