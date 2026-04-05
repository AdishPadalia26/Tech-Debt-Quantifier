'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import CostBreakdownChart from '@/components/CostBreakdownChart';
import DebtScoreCard from '@/components/DebtScoreCard';
import ModuleRiskList from '@/components/ModuleRiskList';
import PriorityActions from '@/components/PriorityActions';
import RoadmapBoard from '@/components/RoadmapBoard';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import {
  getScanDetail,
  getScanFindings,
  getScanModules,
  getScanRoadmap,
  getScanSummary,
} from '@/lib/api';
import {
  ScanDetailResponse,
  ScanFindingsResponse,
  ScanModulesResponse,
  ScanRoadmapResponse,
  ScanSummaryResponse,
} from '@/types';

interface Props {
  params: { scanId: string };
}

export default function ScanDetailPage({ params }: Props) {
  const [detail, setDetail] = useState<ScanDetailResponse | null>(null);
  const [summary, setSummary] = useState<ScanSummaryResponse | null>(null);
  const [modules, setModules] = useState<ScanModulesResponse | null>(null);
  const [roadmap, setRoadmap] = useState<ScanRoadmapResponse | null>(null);
  const [findings, setFindings] = useState<ScanFindingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [detailData, summaryData, modulesData, roadmapData, findingsData] =
          await Promise.all([
            getScanDetail(params.scanId),
            getScanSummary(params.scanId),
            getScanModules(params.scanId),
            getScanRoadmap(params.scanId),
            getScanFindings(params.scanId, 12),
          ]);
        setDetail(detailData);
        setSummary(summaryData);
        setModules(modulesData);
        setRoadmap(roadmapData);
        setFindings(findingsData);
      } catch (err) {
        console.error(err);
        setError('Failed to load scan details');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [params.scanId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
        <div className="max-w-6xl mx-auto text-gray-400">Loading scan details...</div>
      </main>
    );
  }

  if (error || !detail || !summary) {
    return (
      <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
        <div className="max-w-6xl mx-auto space-y-4">
          <p className="text-red-400">{error || 'Scan not found'}</p>
          <Link href="/" className="text-purple-400 hover:text-purple-300">
            Back to Scanner
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white px-6 py-12">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-gray-500 text-sm uppercase tracking-wider mb-1">
              Scan Detail
            </p>
            <h1 className="text-3xl font-bold text-white">Scan {params.scanId}</h1>
            <p className="text-gray-400 text-sm mt-1">
              {summary.created_at
                ? new Date(summary.created_at).toLocaleString()
                : 'Timestamp unavailable'}
            </p>
          </div>
          <Link href="/" className="text-sm text-purple-400 hover:text-purple-300">
            Back to Scanner
          </Link>
        </div>

        <DebtScoreCard
          score={summary.debt_score}
          totalCost={summary.total_cost_usd}
          hours={summary.total_hours}
          sprints={summary.total_sprints}
        />

        {detail.executive_summary && (
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-sm font-medium text-gray-400 mb-2">
              EXECUTIVE SUMMARY
            </h3>
            <p className="text-white leading-relaxed">{detail.executive_summary}</p>
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <CostBreakdownChart costByCategory={summary.cost_by_category} />
          {modules && <ModuleRiskList modules={modules.modules} />}
        </div>

        {roadmap && <RoadmapBoard roadmap={roadmap.roadmap} />}

        {findings && (
          <UnresolvedFindingsList
            findings={findings.findings}
            title="Structured Findings"
          />
        )}

        {detail.priority_actions && (
          <PriorityActions
            actions={detail.priority_actions}
            roiAnalysis={detail.roi_analysis}
          />
        )}
      </div>
    </main>
  );
}
