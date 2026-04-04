'use client';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { CostByCategory } from '@/types';

interface Props {
  costByCategory?: Record<string, CostByCategory>;
}

const COLORS = {
  code_quality:  '#8b5cf6',
  security:      '#ef4444',
  documentation: '#3b82f6',
  dependency:    '#f59e0b',
  test_debt:     '#10b981',
};

export default function CostBreakdownChart({ costByCategory = {} }: Props) {
  const data = Object.entries(costByCategory)
    .filter(([, v]) => v && typeof v === 'object' && (v.cost_usd ?? 0) > 0)
    .map(([key, value]) => ({
      name: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      value: Math.round(value.cost_usd ?? 0),
      hours: (value.hours ?? 0).toFixed(1),
      items: value.item_count ?? 0,
      key,
    }));

  const total = data.reduce((sum, d) => sum + d.value, 0);

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: typeof data[0] }> }) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      return (
        <div className="bg-gray-800 border border-gray-600 rounded-lg p-3">
          <p className="font-medium text-white">{d.name}</p>
          <p className="text-purple-400">${d.value.toLocaleString()}</p>
          <p className="text-gray-400 text-sm">{d.hours} hours</p>
          <p className="text-gray-400 text-sm">{d.items} issues</p>
          <p className="text-gray-400 text-sm">
            {((d.value / total) * 100).toFixed(1)}% of total
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h3 className="text-lg font-semibold text-white mb-4">
        Cost by Category
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((entry) => (
              <Cell 
                key={entry.key} 
                fill={COLORS[entry.key as keyof typeof COLORS] || '#6b7280'} 
              />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value) => (
              <span className="text-gray-300 text-sm">{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
