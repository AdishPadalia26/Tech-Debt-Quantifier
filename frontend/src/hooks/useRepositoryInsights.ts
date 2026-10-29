'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

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

type InsightsBundle = [
  RepoHistory,
  RepoSummaryRollup,
  RichRepoTrend,
  UnresolvedFindingsResponse,
];

// These endpoints are expensive. Concurrent callers for the same repo (e.g. React
// strict-mode double effects, or two panels) share one in-flight request set
// instead of making the backend do the work twice.
const inflight = new Map<string, Promise<InsightsBundle>>();

function fetchInsights(repoUrl: string, unresolvedLimit: number): Promise<InsightsBundle> {
  const key = `${repoUrl}::${unresolvedLimit}`;
  const existing = inflight.get(key);
  if (existing) return existing;
  const request = Promise.all([
    getRepoHistory(repoUrl),
    getRepositorySummary(repoUrl),
    getRepoHistoryRich(repoUrl),
    getRepositoryUnresolved(repoUrl, unresolvedLimit),
  ]).finally(() => inflight.delete(key));
  inflight.set(key, request);
  return request;
}

export function useRepositoryInsights(repoUrl: string, unresolvedLimit: number = 10) {
  const [history, setHistory] = useState<RepoHistory | null>(null);
  const [summary, setSummary] = useState<RepoSummaryRollup | null>(null);
  const [richTrend, setRichTrend] = useState<RichRepoTrend | null>(null);
  const [unresolved, setUnresolved] = useState<UnresolvedFindingsResponse | null>(null);
  const [comparison, setComparison] = useState<ScanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Only the most recent load may write state; earlier (or aborted) ones are ignored.
  const loadId = useRef(0);

  const load = useCallback(async () => {
    const id = ++loadId.current;
    const isCurrent = () => id === loadId.current;
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
      const [historyData, summaryData, richData, unresolvedData] = await fetchInsights(
        repoUrl,
        unresolvedLimit
      );
      if (!isCurrent()) return;

      setHistory(historyData);
      setSummary(summaryData);
      setRichTrend(richData);
      setUnresolved(unresolvedData);

      // Comparison is optional (and requires sign-in); never let it fail the page.
      if (historyData.scans.length >= 2) {
        const [latest, previous] = historyData.scans;
        const comparisonData = await getScanComparison(previous.scan_id, latest.scan_id).catch(
          () => null
        );
        if (isCurrent()) setComparison(comparisonData);
      } else {
        setComparison(null);
      }
    } catch (err) {
      if (!isCurrent()) return;
      console.error(err);
      setError('Failed to load repository details');
    } finally {
      if (isCurrent()) setLoading(false);
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
