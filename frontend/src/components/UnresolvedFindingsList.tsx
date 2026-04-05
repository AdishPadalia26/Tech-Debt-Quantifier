'use client';

import { StructuredFinding } from '@/types';

interface Props {
  findings: StructuredFinding[];
  title?: string;
}

function severityStyle(severity: string) {
  switch (severity) {
    case 'critical':
      return 'text-red-400 bg-red-950/40 border-red-800';
    case 'high':
      return 'text-orange-400 bg-orange-950/40 border-orange-800';
    case 'medium':
      return 'text-yellow-400 bg-yellow-950/40 border-yellow-800';
    default:
      return 'text-green-400 bg-green-950/40 border-green-800';
  }
}

export default function UnresolvedFindingsList({
  findings,
  title = 'Top Unresolved Findings',
}: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <p className="text-gray-400 text-sm">
            Highest-priority unresolved work from the latest scan
          </p>
        </div>
        <p className="text-gray-500 text-sm">{findings.length} shown</p>
      </div>

      {findings.length === 0 ? (
        <p className="text-gray-400 text-sm">
          No unresolved findings available yet.
        </p>
      ) : (
        <div className="space-y-3">
          {findings.map((finding) => (
            <div
              key={finding.id}
              className="bg-gray-900/60 rounded-lg p-4 border border-gray-700"
            >
              <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
                <div>
                  <p className="text-white font-medium">
                    {finding.module || 'root'} · {finding.subcategory || finding.category}
                  </p>
                  <p className="text-gray-400 text-sm break-all">
                    {finding.file_path}
                  </p>
                </div>
                <span
                  className={`px-2 py-1 rounded-full border text-xs font-medium ${severityStyle(
                    finding.severity
                  )}`}
                >
                  {finding.severity}
                </span>
              </div>
              <div className="flex flex-wrap gap-4 text-sm">
                <span className="text-purple-400">
                  ${Math.round(finding.cost_usd).toLocaleString()}
                </span>
                <span className="text-gray-400">
                  {finding.effort_hours?.toFixed(1) || '0.0'}h
                </span>
                <span className="text-gray-500">
                  impact: {finding.business_impact || 'n/a'}
                </span>
                <span className="text-gray-500">
                  confidence: {Math.round((finding.confidence || 0) * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
