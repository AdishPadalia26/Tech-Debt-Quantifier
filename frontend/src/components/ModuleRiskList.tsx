'use client';

import { ModuleSummaryDetail } from '@/types';

interface Props {
  modules: ModuleSummaryDetail[];
}

function severityTone(severity: string) {
  switch (severity) {
    case 'critical':
      return 'text-red-400';
    case 'high':
      return 'text-orange-400';
    case 'medium':
      return 'text-yellow-400';
    default:
      return 'text-green-400';
  }
}

function ownershipTone(risk?: string | null) {
  switch (risk) {
    case 'critical':
      return 'text-red-400';
    case 'high':
      return 'text-orange-400';
    case 'medium':
      return 'text-yellow-400';
    default:
      return 'text-gray-400';
  }
}

export default function ModuleRiskList({ modules }: Props) {
  const topModules = modules.slice(0, 6);

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">Module Risk Map</h3>
          <p className="text-gray-400 text-sm">
            Highest-cost modules from the current scan
          </p>
        </div>
        <p className="text-gray-500 text-sm">{modules.length} modules</p>
      </div>

      {topModules.length === 0 ? (
        <p className="text-gray-400 text-sm">No module summaries available.</p>
      ) : (
        <div className="space-y-3">
          {topModules.map((module) => (
            <div
              key={module.module}
              className="bg-gray-900/60 rounded-lg p-4 border border-gray-700"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <p className="text-white font-medium">{module.module}</p>
                  <p className="text-gray-500 text-sm">
                    {module.finding_count} findings ·{' '}
                    {module.total_effort_hours.toFixed(1)}h
                  </p>
                </div>
                <p
                  className={`text-sm font-medium ${severityTone(
                    module.max_severity
                  )}`}
                >
                  {module.max_severity}
                </p>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-purple-400">
                  ${Math.round(module.total_cost_usd).toLocaleString()}
                </span>
                <span className="text-gray-500">
                  confidence {Math.round(module.avg_confidence * 100)}%
                </span>
              </div>
              <div className="flex items-center justify-between text-xs mt-2">
                <span className={ownershipTone(module.ownership_risk)}>
                  ownership {module.ownership_risk || 'n/a'}
                </span>
                <span className="text-gray-500">
                  {module.owner_count ?? 0} owners · top share{' '}
                  {Math.round((module.top_contributor_share ?? 0) * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
