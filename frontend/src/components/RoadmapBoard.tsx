'use client';

import { ScanRoadmapResponse } from '@/types';

interface Props {
  roadmap: ScanRoadmapResponse['roadmap'];
}

const BUCKET_TITLES: Record<string, string> = {
  quick_wins: 'Quick Wins',
  next_up: 'Next Up',
  strategic: 'Strategic',
};

export default function RoadmapBoard({ roadmap }: Props) {
  const buckets = Object.entries(roadmap);

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">Remediation Roadmap</h3>
        <p className="text-gray-400 text-sm">
          Structured action buckets from the current scan
        </p>
      </div>

      {buckets.length === 0 ? (
        <p className="text-gray-400 text-sm">No roadmap data available.</p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          {buckets.map(([bucket, items]) => (
            <div
              key={bucket}
              className="bg-gray-900/60 rounded-lg border border-gray-700 p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-white font-medium">
                  {BUCKET_TITLES[bucket] || bucket}
                </h4>
                <span className="text-xs text-gray-500">{items.length} items</span>
              </div>
              <div className="space-y-3">
                {items.slice(0, 4).map((item) => (
                  <div key={`${bucket}-${item.finding_id}`} className="border-t border-gray-800 pt-3 first:border-t-0 first:pt-0">
                    <p className="text-sm font-medium text-white">{item.title}</p>
                    <p className="text-xs text-gray-500 break-all">{item.file_path}</p>
                    <div className="flex flex-wrap gap-3 mt-2 text-xs">
                      <span className="text-purple-400">
                        ${Math.round(item.cost_usd).toLocaleString()}
                      </span>
                      <span className="text-gray-400">
                        {(item.effort_hours || 0).toFixed(1)}h
                      </span>
                      <span className="text-gray-500">{item.severity}</span>
                    </div>
                  </div>
                ))}
                {items.length > 4 && (
                  <p className="text-xs text-gray-500">
                    +{items.length - 4} more items
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
