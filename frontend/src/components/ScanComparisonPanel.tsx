'use client';

import Link from 'next/link';

import { ScanComparisonResponse } from '@/types';

interface Props {
  comparison: ScanComparisonResponse;
}

function tone(value: number) {
  if (value > 0) return 'text-red-400';
  if (value < 0) return 'text-green-400';
  return 'text-gray-400';
}

export default function ScanComparisonPanel({ comparison }: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h3 className="text-lg font-semibold text-white">Latest Scan Delta</h3>
          <p className="text-gray-400 text-sm">
            Comparison between the last two completed scans
          </p>
        </div>
        <Link
          href={`/scans/${comparison.target_scan_id}`}
          className="text-sm text-purple-400 hover:text-purple-300"
        >
          Open latest scan
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">Cost</p>
          <p className={`text-2xl font-bold ${tone(comparison.summary.cost_delta_usd)}`}>
            {comparison.summary.cost_delta_usd > 0 ? '+' : ''}$
            {Math.round(comparison.summary.cost_delta_usd).toLocaleString()}
          </p>
        </div>
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">Score</p>
          <p className={`text-2xl font-bold ${tone(comparison.summary.debt_score_delta)}`}>
            {comparison.summary.debt_score_delta > 0 ? '+' : ''}
            {comparison.summary.debt_score_delta.toFixed(1)}
          </p>
        </div>
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">Findings</p>
          <p className={`text-2xl font-bold ${tone(comparison.summary.finding_count_delta)}`}>
            {comparison.summary.finding_count_delta > 0 ? '+' : ''}
            {comparison.summary.finding_count_delta}
          </p>
        </div>
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">Hours</p>
          <p className={`text-2xl font-bold ${tone(comparison.summary.hours_delta)}`}>
            {comparison.summary.hours_delta > 0 ? '+' : ''}
            {comparison.summary.hours_delta.toFixed(1)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-white font-medium mb-2">Added Findings</p>
          <p className="text-3xl font-bold text-red-400">{comparison.added_findings.length}</p>
          <p className="text-gray-500 text-xs mt-1">
            {comparison.added_findings[0]?.subcategory || 'No new findings'}
          </p>
        </div>
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-white font-medium mb-2">Resolved Findings</p>
          <p className="text-3xl font-bold text-green-400">{comparison.removed_findings.length}</p>
          <p className="text-gray-500 text-xs mt-1">
            {comparison.removed_findings[0]?.subcategory || 'No removals'}
          </p>
        </div>
        <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
          <p className="text-white font-medium mb-2">Severity Changes</p>
          <p className="text-3xl font-bold text-yellow-400">{comparison.severity_changed.length}</p>
          <p className="text-gray-500 text-xs mt-1">
            {comparison.severity_changed[0]
              ? `${comparison.severity_changed[0].from_severity} → ${comparison.severity_changed[0].to_severity}`
              : 'No severity changes'}
          </p>
        </div>
      </div>
    </div>
  );
}
