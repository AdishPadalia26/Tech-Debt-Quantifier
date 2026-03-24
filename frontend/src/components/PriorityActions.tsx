import { PriorityAction, ROIAnalysis } from '@/types';

interface Props {
  actions: PriorityAction[];
  roiAnalysis?: ROIAnalysis;
}

const RANK_COLORS = ['border-red-500', 'border-yellow-500', 'border-blue-500'];
const RANK_BADGES = ['🔴 Fix First', '🟡 Fix Second', '🔵 Fix Third'];

export default function PriorityActions({ actions, roiAnalysis }: Props) {
  if (!actions || actions.length === 0) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-lg font-semibold text-white mb-2">
          Priority Actions
        </h3>
        <p className="text-gray-400">No priority actions available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-white">
        🎯 Top Priority Actions
      </h3>

      {actions.map((action, i) => (
        <div
          key={action.rank}
          className={`bg-gray-800 rounded-xl p-6 border-l-4 
                      border border-gray-700 ${RANK_COLORS[i]}`}
        >
          <div className="flex justify-between items-start mb-3">
            <div>
              <span className="text-xs font-medium text-gray-400">
                {RANK_BADGES[i]}
              </span>
              <h4 className="text-white font-semibold mt-1">
                {action.title}
              </h4>
              <p className="text-sm text-gray-400 font-mono mt-1">
                📁 {action.file_or_module}
              </p>
            </div>
            <span className="text-xs bg-gray-700 text-gray-300 
                             px-2 py-1 rounded-full whitespace-nowrap">
              {action.sprint}
            </span>
          </div>

          <p className="text-sm text-gray-300 mb-4">{action.why}</p>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-gray-500">Fix Cost</p>
              <p className="text-white font-semibold">
                ${action.estimated_cost.toLocaleString()}
              </p>
              <p className="text-xs text-gray-500">
                {action.estimated_hours}h
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Monthly Savings</p>
              <p className="text-green-400 font-semibold">
                ${action.saves_per_month.toLocaleString()}/mo
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Payback</p>
              <p className="text-white font-semibold">
                {action.saves_per_month > 0 
                  ? `${Math.ceil(action.estimated_cost / action.saves_per_month)} months`
                  : 'N/A'}
              </p>
            </div>
          </div>
        </div>
      ))}

      {roiAnalysis && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h4 className="text-white font-semibold mb-4">
            💰 Full ROI Analysis
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Annual Savings', 
                value: `$${roiAnalysis.annual_maintenance_savings?.toLocaleString()}` },
              { label: 'Payback Period', 
                value: `${roiAnalysis.payback_months} months` },
              { label: '3-Year ROI', 
                value: `${roiAnalysis['3_year_roi_pct']}%` },
              { label: 'Quarterly Budget', 
                value: `$${roiAnalysis.recommended_budget?.toLocaleString()}` },
            ].map(({ label, value }) => (
              <div key={label} 
                   className="bg-gray-700/50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-400">{label}</p>
                <p className="text-white font-bold mt-1">{value}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-300 mt-4 italic">
            &ldquo;{roiAnalysis.recommendation}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}
