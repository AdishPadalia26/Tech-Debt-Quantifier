'use client';

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { DollarSign, LayoutDashboard, ShieldAlert, Workflow } from 'lucide-react';

import AnalyzeForm from '@/components/AnalyzeForm';
import { ErrorBoundary } from '@/components/error-boundary';
import ProgressBar from '@/components/ProgressBar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DebtReport,
  JobResult,
  RepoHistory,
  RepoSummaryRollup,
  RichRepoTrend,
  ScanFindingsResponse,
  ScanModulesResponse,
  ScanRoadmapResponse,
  UnresolvedFindingsResponse,
} from '@/types';
import {
  getRepoHistory,
  getRepoHistoryRich,
  getRepositorySummary,
  getRepositoryUnresolved,
  getScanFindings,
  getScanModules,
  getScanRoadmap,
} from '@/lib/api';
import { ResultsView } from './ResultsView';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── State & actions ──────────────────────────────────────────

type AppState = 'idle' | 'analyzing' | 'complete' | 'error';

type IntegrationsConfig = {
  slack: { configured: boolean; channel: string };
  jira: { configured: boolean; server: string; project: string };
};

type AnalyzeState = {
  appState: AppState;
  jobId: string;
  result: DebtReport | null;
  error: string;
  repoHistory: RepoHistory | null;
  repoSummary: RepoSummaryRollup | null;
  richRepoHistory: RichRepoTrend | null;
  unresolvedFindings: UnresolvedFindingsResponse | null;
  scanModules: ScanModulesResponse | null;
  scanRoadmap: ScanRoadmapResponse | null;
  scanFindings: ScanFindingsResponse | null;
  currentGithubUrl: string;
  integrations: IntegrationsConfig | null;
};

type AnalyzeAction =
  | { type: 'JOB_STARTED'; jobId: string; githubUrl: string }
  | { type: 'ANALYSIS_COMPLETE'; result: DebtReport }
  | { type: 'ANALYSIS_ERROR'; error: string }
  | { type: 'RESET' }
  | {
      type: 'SET_SECONDARY';
      history: RepoHistory | null;
      summary: RepoSummaryRollup | null;
      rich: RichRepoTrend | null;
      unresolved: UnresolvedFindingsResponse | null;
    }
  | {
      type: 'SET_SCAN_DATA';
      modules: ScanModulesResponse | null;
      roadmap: ScanRoadmapResponse | null;
      findings: ScanFindingsResponse | null;
    }
  | { type: 'SET_INTEGRATIONS'; integrations: IntegrationsConfig };

const INITIAL_STATE: AnalyzeState = {
  appState: 'idle',
  jobId: '',
  result: null,
  error: '',
  repoHistory: null,
  repoSummary: null,
  richRepoHistory: null,
  unresolvedFindings: null,
  scanModules: null,
  scanRoadmap: null,
  scanFindings: null,
  currentGithubUrl: '',
  integrations: null,
};

function analyzeReducer(state: AnalyzeState, action: AnalyzeAction): AnalyzeState {
  switch (action.type) {
    case 'JOB_STARTED':
      return {
        ...INITIAL_STATE,
        integrations: state.integrations,
        appState: 'analyzing',
        jobId: action.jobId,
        currentGithubUrl: action.githubUrl,
      };
    case 'ANALYSIS_COMPLETE':
      return { ...state, appState: 'complete', result: action.result };
    case 'ANALYSIS_ERROR':
      return { ...state, appState: 'error', error: action.error };
    case 'RESET':
      return { ...INITIAL_STATE, integrations: state.integrations };
    case 'SET_SECONDARY':
      return {
        ...state,
        repoHistory: action.history,
        repoSummary: action.summary,
        richRepoHistory: action.rich,
        unresolvedFindings: action.unresolved,
      };
    case 'SET_SCAN_DATA':
      return {
        ...state,
        scanModules: action.modules,
        scanRoadmap: action.roadmap,
        scanFindings: action.findings,
      };
    case 'SET_INTEGRATIONS':
      return { ...state, integrations: action.integrations };
    default:
      return state;
  }
}

// ─── Component ────────────────────────────────────────────────

export function AnalyzeFlow() {
  const [state, dispatch] = useReducer(analyzeReducer, INITIAL_STATE);
  const currentGithubUrlRef = useRef('');

  useEffect(() => {
    fetch(`${API_URL}/integrations/status`)
      .then((r) => r.json())
      .then((data: IntegrationsConfig) =>
        dispatch({ type: 'SET_INTEGRATIONS', integrations: data })
      )
      .catch(console.error);
  }, []);

  const handleJobStarted = useCallback((id: string, githubUrl?: string) => {
    const url = githubUrl ?? '';
    currentGithubUrlRef.current = url;
    dispatch({ type: 'JOB_STARTED', jobId: id, githubUrl: url });
  }, []);

  const handleComplete = useCallback(async (jobResult: JobResult) => {
    if (jobResult.status === 'failed') {
      dispatch({ type: 'ANALYSIS_ERROR', error: jobResult.error || 'Analysis failed' });
      return;
    }
    dispatch({ type: 'ANALYSIS_COMPLETE', result: jobResult });
    try {
      const githubUrl = currentGithubUrlRef.current;
      if (!githubUrl) return;
      const [history, summary, richHistory, unresolved] = await Promise.all([
        getRepoHistory(githubUrl),
        getRepositorySummary(githubUrl),
        getRepoHistoryRich(githubUrl),
        getRepositoryUnresolved(githubUrl, 6),
      ]);
      dispatch({ type: 'SET_SECONDARY', history, summary, rich: richHistory, unresolved });
      if (jobResult.scan_id) {
        const [modules, roadmap, findings] = await Promise.all([
          getScanModules(jobResult.scan_id),
          getScanRoadmap(jobResult.scan_id),
          getScanFindings(jobResult.scan_id, 8),
        ]);
        dispatch({ type: 'SET_SCAN_DATA', modules, roadmap, findings });
      }
    } catch (e) {
      console.log('Secondary data not available yet:', e);
    }
  }, []);

  const handleReset = useCallback(() => dispatch({ type: 'RESET' }), []);

  const {
    appState,
    jobId,
    result,
    error,
    repoHistory,
    repoSummary,
    richRepoHistory,
    unresolvedFindings,
    scanModules,
    scanRoadmap,
    scanFindings,
    currentGithubUrl,
    integrations,
  } = state;

  return (
    <>
      {/* Hero — always visible */}
      <section className="mb-8 grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-5">
          <div className="space-y-4">
            <Badge
              variant="outline"
              className="border-border bg-muted/20 text-muted-foreground"
            >
              Vercel-grade debt visibility for engineering teams
            </Badge>
            <div className="space-y-3">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                Quantify technical debt with executive clarity and engineering detail.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                Scan a GitHub repository, turn hotspots into cost and effort signals, and move
                directly into remediation, reporting, Slack, and Jira.
              </p>
            </div>
          </div>
          <AnalyzeForm onJobStarted={handleJobStarted} />
        </div>

        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle>What ships in one scan</CardTitle>
            <CardDescription>
              Structured debt output designed for CTO reviews, team triage, and roadmap planning.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {[
              {
                icon: DollarSign,
                title: 'Debt economics',
                description: 'Cost, effort, and ROI in business-ready terms.',
              },
              {
                icon: ShieldAlert,
                title: 'Risk signals',
                description: 'Severity, confidence, and maintenance drag surfaced clearly.',
              },
              {
                icon: Workflow,
                title: 'Action planning',
                description:
                  'Priority actions, roadmap buckets, and exportable next steps.',
              },
              {
                icon: LayoutDashboard,
                title: 'Portfolio view',
                description:
                  'Trend and module views across multiple scans and repositories.',
              },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-xl border border-border bg-muted/20 p-4"
              >
                <item.icon className="mb-3 size-4 text-primary" />
                <p className="text-sm font-medium text-foreground">{item.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {item.description}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      {/* Analyzing skeleton */}
      {appState === 'analyzing' ? (
        <section className="space-y-4">
          <ProgressBar
            jobId={jobId}
            onComplete={(r) => {
              void handleComplete(r);
            }}
          />
          <div className="mt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Skeleton className="h-24 rounded-lg" />
              <Skeleton className="h-24 rounded-lg" />
              <Skeleton className="h-24 rounded-lg" />
            </div>
            <Skeleton className="h-64 rounded-lg" />
            <Skeleton className="h-48 rounded-lg" />
            <Skeleton className="h-48 rounded-lg" />
          </div>
        </section>
      ) : null}

      {/* Error state */}
      {appState === 'error' ? (
        <Card className="border-destructive/30 bg-card">
          <CardHeader>
            <CardTitle>Analysis failed</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={handleReset}>Try Again</Button>
          </CardContent>
        </Card>
      ) : null}

      {/* Results */}
      {appState === 'complete' && result ? (
        <ErrorBoundary>
          <ResultsView
            result={result}
            repoHistory={repoHistory}
            repoSummary={repoSummary}
            richRepoHistory={richRepoHistory}
            unresolvedFindings={unresolvedFindings}
            scanModules={scanModules}
            scanRoadmap={scanRoadmap}
            scanFindings={scanFindings}
            currentGithubUrl={currentGithubUrl}
            integrations={integrations}
            onReset={handleReset}
          />
        </ErrorBoundary>
      ) : null}
    </>
  );
}
