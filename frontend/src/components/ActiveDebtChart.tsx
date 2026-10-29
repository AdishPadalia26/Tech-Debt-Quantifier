'use client';

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { ActiveTrendPoint } from '@/types';

interface Props {
  points?: ActiveTrendPoint[] | null;
}

export default function ActiveDebtChart({ points }: Props) {
  const safePoints = Array.isArray(points) ? points : [];

  if (!safePoints.length) {
    return (
      <div className="bg-surface-raised rounded-xl p-6 border border-border">
        <h3 className="text-lg font-semibold text-foreground mb-2">
          Active Debt Trend
        </h3>
        <p className="text-muted-foreground text-sm">
          Active unresolved debt will appear here after more scans.
        </p>
      </div>
    );
  }

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: Array<{ payload: ActiveTrendPoint }>;
  }) => {
    if (!active || !payload?.length) return null;
    const point = payload[0].payload;
    return (
      <div className="bg-surface-raised border border-border-strong rounded-lg p-3">
        <p className="text-foreground text-sm">{point.date_display}</p>
        <p className="text-primary font-medium">
          ${point.active_cost_usd.toLocaleString()}
        </p>
        <p className="text-muted-foreground text-sm">
          {point.active_finding_count} active findings
        </p>
      </div>
    );
  };

  const latestPoint = safePoints[safePoints.length - 1];

  return (
    <div className="bg-surface-raised rounded-xl p-6 border border-border">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">Active Debt Trend</h3>
          <p className="text-muted-foreground text-sm">
            Unresolved, unsuppressed finding cost over time
          </p>
        </div>
        <div className="text-right">
          <p className="text-primary text-lg font-semibold">
            ${latestPoint.active_cost_usd.toLocaleString()}
          </p>
          <p className="text-muted-foreground text-xs">
            {latestPoint.active_finding_count} active findings
          </p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={safePoints}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-strong)" />
          <XAxis
            dataKey="date_display"
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border-strong)' }}
          />
          <YAxis
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border-strong)' }}
            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="active_cost_usd"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={{ fill: 'var(--chart-1)', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
