'use client';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { TrendData } from '@/types';

interface Props {
  trend: TrendData;
  currentCost?: number;
}

export default function DebtTrendChart({ trend, currentCost }: Props) {
  if (!trend.trend || trend.trend.length < 2) {
    return (
      <div className="bg-surface-raised rounded-xl p-6 border border-border">
        <h3 className="text-lg font-semibold text-foreground mb-2">
          Debt Over Time
        </h3>
        <p className="text-muted-foreground text-sm">
          Run more scans to see trend data.
        </p>
      </div>
    );
  }

  const directionColor =
    trend.direction === 'up'
      ? 'text-danger'
      : trend.direction === 'down'
      ? 'text-success'
      : 'text-muted-foreground';

  const directionIcon =
    trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→';

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: Array<{ payload: (typeof trend.trend)[0] }>;
  }) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      return (
        <div className="bg-surface-raised border border-border-strong rounded-lg p-3">
          <p className="text-muted-foreground text-sm">{d.date_display}</p>
          <p className="text-primary font-medium">
            ${d.total_cost.toLocaleString()}
          </p>
          <p className="text-muted-foreground text-sm">
            Score: {d.debt_score.toFixed(0)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-surface-raised rounded-xl p-6 border border-border">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">Debt Over Time</h3>
          <p className="text-muted-foreground text-sm">
            {trend.total_scans} scan{trend.total_scans !== 1 ? 's' : ''}
            {currentCost !== undefined && (
              <span className="ml-2 text-primary">
                Current: ${currentCost.toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <div className="text-right">
          <p className={`text-lg font-bold ${directionColor}`}>
            {directionIcon} {Math.abs(trend.change_pct).toFixed(1)}%
          </p>
          <p className="text-muted-foreground text-xs">vs previous scan</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={trend.trend}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-strong)" />
          <XAxis
            dataKey="date_display"
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border-strong)' }}
          />
          <YAxis
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border-strong)' }}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="total_cost"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={{ fill: 'var(--chart-6)', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
