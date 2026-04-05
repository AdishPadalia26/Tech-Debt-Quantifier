'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  getRepoHistory,
  getRepoHistoryRich,
  getRepositorySummary,
  getRepositoryUnresolved,
  getScanComparison,
} from '@/lib/api';
import {
  RepoHistory,
  RepoSummaryRollup,
  RichRepoTrend,
  ScanComparisonResponse,
  UnresolvedFindingsResponse,
} from '@/types';

export function useRepositoryInsights(repoUrl: string, unresolvedLimit: number = 10) {
  const [history, setHistory] = useState<RepoHistory | null>(null);
  const [summary, setSummary] = useState<RepoSummaryRollup | null>(null);
  const [richTrend, setRichTrend] = useState<RichRepoTrend | null>(null);
  const [unresolved, setUnresolved] = useState<UnresolvedFindingsResponse | null>(null);
  const [comparison, setComparison] = useState<ScanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!repoUrl) {
      setHistory(null);
      setSummary(null);
      setRichTrend(null);
      setUnresolved(null);
      setComparison(null);
      setError('');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');
    try {
      const [historyData, summaryData, richData, unresolvedData] =
        await Promise.all([
          getRepoHistory(repoUrl),
          getRepositorySummary(repoUrl),
          getRepoHistoryRich(repoUrl),
          getRepositoryUnresolved(repoUrl, unresolvedLimit),
        ]);

      setHistory(historyData);
      setSummary(summaryData);
      setRichTrend(richData);
      setUnresolved(unresolvedData);

      if (historyData.scans.length >= 2) {
        const [latest, previous] = historyData.scans;
        const comparisonData = await getScanComparison(previous.scan_id, latest.scan_id);
        setComparison(comparisonData);
      } else {
        setComparison(null);
      }
    } catch (err) {
      console.error(err);
      setError('Failed to load repository details');
    } finally {
      setLoading(false);
    }
  }, [repoUrl, unresolvedLimit]);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    history,
    summary,
    richTrend,
    unresolved,
    comparison,
    loading,
    error,
    reload: load,
  };
}
