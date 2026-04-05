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
  points: ActiveTrendPoint[];
}

export default function ActiveDebtChart({ points }: Props) {
  if (!points.length) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-lg font-semibold text-white mb-2">
          Active Debt Trend
        </h3>
        <p className="text-gray-400 text-sm">
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
      <div className="bg-gray-800 border border-gray-600 rounded-lg p-3">
        <p className="text-gray-300 text-sm">{point.date_display}</p>
        <p className="text-cyan-400 font-medium">
          ${point.active_cost_usd.toLocaleString()}
        </p>
        <p className="text-gray-400 text-sm">
          {point.active_finding_count} active findings
        </p>
      </div>
    );
  };

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">Active Debt Trend</h3>
          <p className="text-gray-400 text-sm">
            Unresolved, unsuppressed finding cost over time
          </p>
        </div>
        <div className="text-right">
          <p className="text-cyan-400 text-lg font-semibold">
            ${points[points.length - 1].active_cost_usd.toLocaleString()}
          </p>
          <p className="text-gray-500 text-xs">
            {points[points.length - 1].active_finding_count} active findings
          </p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="date_display"
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            axisLine={{ stroke: '#374151' }}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            axisLine={{ stroke: '#374151' }}
            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="active_cost_usd"
            stroke="#22d3ee"
            strokeWidth={2}
            dot={{ fill: '#22d3ee', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
