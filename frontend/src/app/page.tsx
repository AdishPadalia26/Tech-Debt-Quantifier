'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import AnalyzeForm from '@/components/AnalyzeForm';
import ProgressBar from '@/components/ProgressBar';
import DebtScoreCard from '@/components/DebtScoreCard';
import CostBreakdownChart from '@/components/CostBreakdownChart';
import PriorityActions from '@/components/PriorityActions';
import RepoProfile from '@/components/RepoProfile';
import DebtTrendChart from '@/components/DebtTrendChart';
import ActiveDebtChart from '@/components/ActiveDebtChart';
import ModuleRiskList from '@/components/ModuleRiskList';
import RoadmapBoard from '@/components/RoadmapBoard';
import RepositoryInsightsPanel from '@/components/RepositoryInsightsPanel';
import UnresolvedFindingsList from '@/components/UnresolvedFindingsList';
import {
  JobResult,
  DebtReport,
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
import { repoDetailPath } from '@/lib/routes';

type AppState = 'idle' | 'analyzing' | 'complete' | 'error';

export default function Home() {
  const [appState, setAppState] = useState<AppState>('idle');
  const [jobId, setJobId] = useState<string>('');
  const [result, setResult] = useState<DebtReport | null>(null);
  const [error, setError] = useState('');
  const [repoHistory, setRepoHistory] = useState<RepoHistory | null>(null);
  const [repoSummary, setRepoSummary] = useState<RepoSummaryRollup | null>(null);
  const [richRepoHistory, setRichRepoHistory] = useState<RichRepoTrend | null>(null);
  const [unresolvedFindings, setUnresolvedFindings] =
    useState<UnresolvedFindingsResponse | null>(null);
  const [scanModules, setScanModules] = useState<ScanModulesResponse | null>(null);
  const [scanRoadmap, setScanRoadmap] = useState<ScanRoadmapResponse | null>(null);
  const [scanFindings, setScanFindings] = useState<ScanFindingsResponse | null>(null);
  const [currentGithubUrl, setCurrentGithubUrl] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [slackSending, setSlackSending] = useState(false);
  const [slackSent, setSlackSent] = useState(false);
  const [jiraCreating, setJiraCreating] = useState(false);
  const [jiraResult, setJiraResult] = useState<{
    epic_url?: string;
    total_created?: number;
  } | null>(null);
  const [integrations, setIntegrations] = useState<{
    slack: { configured: boolean; channel: string };
    jira: { configured: boolean; server: string; project: string };
  } | null>(null);

  const handleJobStarted = (id: string, githubUrl?: string) => {
    setJobId(id);
    setAppState('analyzing');
    setResult(null);
    setError('');
    setRepoHistory(null);
    setRepoSummary(null);
    setRichRepoHistory(null);
    setUnresolvedFindings(null);
    setScanModules(null);
    setScanRoadmap(null);
    setScanFindings(null);
    if (githubUrl) setCurrentGithubUrl(githubUrl);
  };

  const handleComplete = async (jobResult: JobResult) => {
    if (jobResult.status === 'failed') {
      setError(jobResult.error || 'Analysis failed');
      setAppState('error');
      return;
    }
    setResult(jobResult);
    setAppState('complete');

    // Fetch scan history for trend chart
    try {
      const [history, summary, richHistory, unresolved] = await Promise.all([
        getRepoHistory(currentGithubUrl),
        getRepositorySummary(currentGithubUrl),
        getRepoHistoryRich(currentGithubUrl),
        getRepositoryUnresolved(currentGithubUrl, 6),
      ]);
      setRepoHistory(history);
      setRepoSummary(summary);
      setRichRepoHistory(richHistory);
      setUnresolvedFindings(unresolved);

      if (jobResult.scan_id) {
        const [modules, roadmap, findings] = await Promise.all([
          getScanModules(jobResult.scan_id),
          getScanRoadmap(jobResult.scan_id),
          getScanFindings(jobResult.scan_id, 8),
        ]);
        setScanModules(modules);
        setScanRoadmap(roadmap);
        setScanFindings(findings);
      }
    } catch (e) {
      console.log('History not available yet:', e);
    }
  };

  const handleDownloadPDF = async () => {
    if (!jobId) return;
    setDownloading(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/report/${jobId}/pdf`
      );
      if (!response.ok) throw new Error('PDF generation failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tech-debt-report-${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('PDF download failed:', err);
    } finally {
      setDownloading(false);
    }
  };

  const handleReset = () => {
    setAppState('idle');
    setJobId('');
    setResult(null);
    setError('');
    setRepoHistory(null);
    setRepoSummary(null);
    setRichRepoHistory(null);
    setUnresolvedFindings(null);
    setScanModules(null);
    setScanRoadmap(null);
    setScanFindings(null);
  };

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/integrations/status`)
      .then(r => r.json())
      .then(setIntegrations)
      .catch(console.error);
  }, []);

  const handleSendSlack = async () => {
    if (!jobId) return;
    setSlackSending(true);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/report/${jobId}/slack`,
        { method: 'POST' }
      );
      if (!r.ok) throw new Error(await r.text());
      setSlackSent(true);
      setTimeout(() => setSlackSent(false), 4000);
    } catch (err) {
      console.error('Slack failed:', err);
    } finally {
      setSlackSending(false);
    }
  };

  const handleCreateJira = async () => {
    if (!jobId) return;
    setJiraCreating(true);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/report/${jobId}/jira`,
        { method: 'POST' }
      );
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setJiraResult(data);
    } catch (err) {
      console.error('Jira failed:', err);
    } finally {
      setJiraCreating(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <div>
            <h1 className="text-xl font-bold text-white">
              🔍 Tech Debt Quantifier
            </h1>
            <p className="text-xs text-gray-400">
              Turn technical debt into business decisions
            </p>
          </div>
          {appState !== 'idle' && (
            <button
              onClick={handleReset}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              ← New Analysis
            </button>
          )}
          <Link
            href="/portfolio"
            className="flex items-center gap-2 px-4 py-2
                       bg-gray-800 hover:bg-gray-700
                       text-gray-300 hover:text-white
                       text-sm rounded-lg transition-colors
                       border border-gray-700"
          >
            Portfolio View
          </Link>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-12">
        
        {/* IDLE STATE — Show form */}
        {appState === 'idle' && (
          <div className="flex flex-col items-center text-center space-y-8">
            <div className="space-y-3">
              <h2 className="text-4xl font-bold text-white">
                How much does your{' '}
                <span className="text-purple-400">technical debt</span>{' '}
                cost?
              </h2>
              <p className="text-gray-400 max-w-xl">
                Paste a GitHub repo URL. Get a full dollar-cost analysis 
                with priority actions, ROI estimates, and an executive 
                summary — powered by live market data.
              </p>
            </div>

            <AnalyzeForm onJobStarted={handleJobStarted} />

            {/* Features */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 
                            w-full max-w-3xl mt-8">
              {[
                { icon: '💰', label: 'Real Dollar Costs',
                  desc: 'BLS + Levels.fyi rates' },
                { icon: '🔥', label: 'Git Hotspot Analysis',
                  desc: 'Churn × complexity' },
                { icon: '🤖', label: 'AI Code Detection',
                  desc: 'Copilot debt flagged' },
                { icon: '📊', label: 'Executive Report',
                  desc: 'Board-ready output' },
              ].map(({ icon, label, desc }) => (
                <div key={label} 
                     className="bg-gray-800 rounded-xl p-4 
                                border border-gray-700 text-center">
                  <p className="text-2xl mb-2">{icon}</p>
                  <p className="text-sm font-medium text-white">{label}</p>
                  <p className="text-xs text-gray-400 mt-1">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ANALYZING STATE — Show progress */}
        {appState === 'analyzing' && (
          <div className="flex flex-col items-center space-y-8">
            <div className="text-center">
              <h2 className="text-2xl font-bold text-white mb-2">
                Analyzing repository...
              </h2>
              <p className="text-gray-400">
                Running static analysis, git mining, 
                and cost estimation
              </p>
            </div>
            <ProgressBar jobId={jobId} onComplete={handleComplete} />
          </div>
        )}

        {/* ERROR STATE */}
        {appState === 'error' && (
          <div className="text-center space-y-4">
            <p className="text-red-400 text-lg">❌ {error}</p>
            <button
              onClick={handleReset}
              className="px-6 py-2 bg-purple-600 rounded-lg text-white"
            >
              Try Again
            </button>
          </div>
        )}

        {/* COMPLETE STATE — Show full report */}
        {appState === 'complete' && result && (
          <div className="space-y-6">

            {/* Executive Summary */}
            {result.executive_summary && (
              <div className="bg-gray-800 rounded-xl p-6 
                              border border-gray-700">
                <h3 className="text-sm font-medium text-gray-400 mb-2">
                  EXECUTIVE SUMMARY
                </h3>
                <p className="text-white leading-relaxed">
                  {result.executive_summary}
                </p>
              </div>
            )}

            {/* PDF Download Button */}
            <div className="flex flex-wrap gap-3 justify-end mt-4">
              {result.scan_id && (
                <Link
                  href={`/scans/${result.scan_id}`}
                  className="flex items-center gap-2 px-5 py-2.5
                             bg-cyan-600 hover:bg-cyan-700
                             text-white font-medium rounded-lg
                             transition-colors text-sm"
                >
                  Open Scan Detail
                </Link>
              )}

              {currentGithubUrl && (
                <Link
                  href={repoDetailPath(currentGithubUrl)}
                  className="flex items-center gap-2 px-5 py-2.5
                             bg-gray-700 hover:bg-gray-600
                             text-white font-medium rounded-lg
                             transition-colors text-sm"
                >
                  Open Repository Detail
                </Link>
              )}

              {/* PDF Button */}
              <button
                onClick={handleDownloadPDF}
                disabled={downloading}
                className="flex items-center gap-2 px-5 py-2.5 
                           bg-purple-600 hover:bg-purple-700
                           disabled:bg-gray-600 disabled:cursor-not-allowed
                           text-white font-medium rounded-lg 
                           transition-colors text-sm"
              >
                {downloading ? (
                  <>
                    <span className="animate-spin">⏳</span>
                    Generating PDF...
                  </>
                ) : (
                  <>📄 Download PDF Report</>
                )}
              </button>

              {/* Slack Button */}
              {integrations?.slack?.configured && (
                <button
                  onClick={handleSendSlack}
                  disabled={slackSending || slackSent}
                  className="flex items-center gap-2 px-5 py-2.5 
                             bg-[#4A154B] hover:bg-[#611f69]
                             disabled:bg-gray-600 disabled:cursor-not-allowed
                             text-white font-medium rounded-lg 
                             transition-colors text-sm"
                >
                  {slackSent
                    ? '✅ Sent to Slack!'
                    : slackSending
                    ? '⏳ Sending...'
                    : `📨 Send to Slack ${integrations.slack.channel}`}
                </button>
              )}

              {/* Jira Button */}
              {integrations?.jira?.configured && (
                <button
                  onClick={handleCreateJira}
                  disabled={jiraCreating || !!jiraResult}
                  className="flex items-center gap-2 px-5 py-2.5 
                             bg-[#0052CC] hover:bg-[#0065FF]
                             disabled:bg-gray-600 disabled:cursor-not-allowed
                             text-white font-medium rounded-lg 
                             transition-colors text-sm"
                >
                  {jiraResult
                    ? `✅ ${jiraResult.total_created} Jira tickets created`
                    : jiraCreating
                    ? '⏳ Creating tickets...'
                    : `🎫 Create Jira Tickets (${integrations.jira.project})`}
                </button>
              )}

              {/* Jira epic link */}
              {jiraResult?.epic_url && (
                <a
                  href={jiraResult.epic_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-sm 
                             text-blue-400 hover:text-blue-300
                             underline underline-offset-2"
                >
                  View Epic in Jira ↗
                </a>
              )}
            </div>

            {/* Unconfigured hint */}
            {integrations && !integrations.slack.configured
                && !integrations.jira.configured && (
              <p className="text-xs text-gray-500 mt-2 text-right">
                Add SLACK_BOT_TOKEN or JIRA_API_TOKEN to .env
                to enable integrations
              </p>
            )}

            {/* Score Cards */}
            <DebtScoreCard
              score={result.debt_score}
              totalCost={result.total_cost_usd}
              hours={result.total_remediation_hours}
              sprints={result.total_remediation_sprints}
              sanityCheck={result.sanity_check}
            />

            {/* Debt Trend Chart */}
            {repoHistory && (
              <DebtTrendChart 
                trend={repoHistory.trend}
                currentCost={result.total_cost_usd}
              />
            )}

            {repoSummary && (
              <RepositoryInsightsPanel summary={repoSummary} />
            )}

            {richRepoHistory && (
              <ActiveDebtChart points={richRepoHistory.active_trend} />
            )}

            {/* Charts + Profile */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <CostBreakdownChart 
                costByCategory={result.cost_by_category} />
              {result.repo_profile && (
                <RepoProfile profile={result.repo_profile} />
              )}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {scanModules && <ModuleRiskList modules={scanModules.modules} />}
              {scanRoadmap && <RoadmapBoard roadmap={scanRoadmap.roadmap} />}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {unresolvedFindings && (
                <UnresolvedFindingsList findings={unresolvedFindings.items} />
              )}
              {scanFindings && (
                <UnresolvedFindingsList
                  findings={scanFindings.findings}
                  title="Current Scan Findings"
                />
              )}
            </div>

            {/* Priority Actions */}
            {result.priority_actions && (
              <PriorityActions
                actions={result.priority_actions}
                roiAnalysis={result.roi_analysis}
              />
            )}

            {/* Data Sources footer */}
            <div className="bg-gray-800/50 rounded-xl p-4 
                            border border-gray-700">
              <p className="text-xs text-gray-500">
                📡 Data sources: {result.data_sources_used?.join(' · ')}
                {' '}· Rate confidence:{' '}
                <span className="text-purple-400">
                  {result.hourly_rates?.confidence?.toUpperCase() || 'N/A'}
                </span>
              </p>
            </div>

            {/* Debug overlay */}
            {process.env.NODE_ENV === 'development' && (
              <details className="mt-8 bg-gray-900 rounded-lg p-4 border border-gray-700">
                <summary className="text-xs text-gray-400 cursor-pointer">
                  🛠 Debug: raw values
                </summary>
                <pre className="text-xs text-gray-300 mt-3 overflow-auto max-h-64">
                  {JSON.stringify({
                    debt_score: result.debt_score,
                    total_cost_usd: result.total_cost_usd,
                    total_remediation_hours: result.total_remediation_hours,
                    cost_by_category_keys: Object.keys(result.cost_by_category || {}),
                    priority_actions_count: result.priority_actions?.length,
                    exec_summary_preview: result.executive_summary?.slice(0, 80),
                  }, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
