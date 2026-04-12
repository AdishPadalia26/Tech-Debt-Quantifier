'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AreaChart, Card as TremorCard, DonutChart, Legend } from '@tremor/react';
import { motion } from 'motion/react';
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  DollarSign,
  Download,
  GitBranch,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  ShieldAlert,
  Sparkles,
  Ticket,
  TrendingDown,
  Workflow,
} from 'lucide-react';

import AnalyzeForm from '@/components/AnalyzeForm';
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
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  JobResult,
  DebtReport,
  RepoHistory,
  RepoSummaryRollup,
  RichRepoTrend,
  ScanFindingsResponse,
  ScanModulesResponse,
  ScanRoadmapResponse,
  StructuredFinding,
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

const CHART_COLORS = ['teal', 'blue', 'amber', 'violet', 'rose', 'emerald'];

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-400 border-red-500/20',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  low: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
};

const SEV_COLOR: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-amber-400',
  low: 'text-emerald-400',
};

type ActionItem = {
  severity?: string;
  sprint_number?: number;
  sprint?: string | number;
  monthly_savings?: number;
  saves_per_month?: number;
  cost_explanation?: string;
  why?: string;
  top_cost_drivers?: string[];
  estimated_cost?: number;
  title?: string;
  file_or_module?: string;
  file?: string;
  estimated_hours?: number;
};

type DebtItemRecord = {
  severity?: string;
  file?: string;
  category?: string;
  cost_usd?: number;
  adjusted_minutes?: number;
  combined_multiplier?: number;
  base_minutes?: number;
  hourly_rate?: number;
  base_cost_usd?: number;
  cost_explanation?: string;
};

function useCountUp(target: number, duration = 1200) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!target) {
      setValue(0);
      return;
    }

    let frame = 0;
    const start = Date.now();

    const tick = () => {
      const elapsed = Date.now() - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);

  return value;
}

function formatCategoryName(value?: string | null) {
  return (value || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatFilePath(value?: string | null) {
  return (value || '').replace(/^\/tmp\/repos\/[^/]+\//, '');
}

function EmptyCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function KpiCard({
  label,
  value,
  subtext,
  color = 'text-foreground',
  index = 0,
}: {
  label: string;
  value: string;
  subtext?: string;
  color?: string;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <TremorCard className="border-border bg-card p-5">
        <p className="mb-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </p>
        <p className={cn('font-mono text-3xl font-semibold tabular-nums', color)}>
          {value}
        </p>
        {subtext ? (
          <p className="mt-1 text-xs text-muted-foreground">{subtext}</p>
        ) : null}
      </TremorCard>
    </motion.div>
  );
}

function ActionCard({ action, index }: { action: ActionItem; index: number }) {
  const [open, setOpen] = useState(false);
  const severity = (action.severity || (index === 0 ? 'high' : 'medium')).toLowerCase();
  const badgeClass = SEVERITY_BADGE[severity] ?? SEVERITY_BADGE.medium;
  const sprint = action.sprint_number ?? action.sprint ?? index + 1;
  const monthlySavings = action.monthly_savings ?? action.saves_per_month ?? 0;
  const explanation = action.cost_explanation ?? action.why;
  const hasExplanation = explanation || action.top_cost_drivers?.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
    >
      <Card className="border-border bg-card transition-colors hover:bg-card/80">
        <CardContent className="p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={cn('text-xs', badgeClass)}>
                {severity}
              </Badge>
              <span className="text-xs text-muted-foreground">Sprint {sprint}</span>
            </div>
            <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-foreground">
              ${(action.estimated_cost ?? 0).toLocaleString()}
            </span>
          </div>

          <p className="mb-1 text-sm font-medium text-foreground">
            {action.title || action.file_or_module || 'Unknown item'}
          </p>

          {(action.file_or_module || action.file) ? (
            <p className="mb-3 w-fit rounded bg-muted/50 px-2 py-0.5 font-mono text-xs text-muted-foreground">
              {action.file_or_module || formatFilePath(action.file)}
            </p>
          ) : null}

          <Separator className="mb-3" />

          <div className="mb-3 grid grid-cols-3 gap-2 text-xs">
            <div>
              <p className="mb-0.5 flex items-center gap-1 text-muted-foreground">
                <DollarSign className="size-3" /> Fix Cost
              </p>
              <p className="font-mono font-semibold tabular-nums">
                ${(action.estimated_cost ?? 0).toLocaleString()}
              </p>
            </div>
            <div>
              <p className="mb-0.5 flex items-center gap-1 text-muted-foreground">
                <Clock className="size-3" /> Hours
              </p>
              <p className="font-mono font-semibold tabular-nums">
                {action.estimated_hours ?? 0}h
              </p>
            </div>
            <div>
              <p className="mb-0.5 flex items-center gap-1 text-muted-foreground">
                <TrendingDown className="size-3" /> Savings/mo
              </p>
              <p
                className={cn(
                  'font-mono font-semibold tabular-nums',
                  monthlySavings > 0 ? 'text-emerald-400' : 'text-muted-foreground'
                )}
              >
                {monthlySavings > 0 ? `$${monthlySavings.toLocaleString()}/mo` : 'N/A'}
              </p>
            </div>
          </div>

          {hasExplanation ? (
            <Collapsible open={open} onOpenChange={setOpen}>
              <CollapsibleTrigger className="flex w-full items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
                <ChevronDown
                  className={cn('size-3 transition-transform', open ? 'rotate-180' : '')}
                />
                Why this costs more
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-2 rounded-md border border-border bg-muted/30 p-3">
                  {explanation ? (
                    <p className="mb-2 text-xs leading-5 text-muted-foreground">
                      {explanation}
                    </p>
                  ) : null}
                </div>
              </CollapsibleContent>
            </Collapsible>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function DebtItemsTable({ items }: { items: DebtItemRecord[] }) {
  const [selected, setSelected] = useState<DebtItemRecord | null>(null);

  if (items.length === 0) {
    return (
      <Card className="border-border bg-card">
        <CardContent className="p-6 text-sm text-muted-foreground">
          No debt items available for this scan yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="overflow-hidden rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="w-[40%]">File</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Hours</TableHead>
              <TableHead className="text-right">Multiplier</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.slice(0, 50).map((item, i) => {
              const sev = (item.severity || 'low').toLowerCase();
              return (
                <TableRow
                  key={`${item.file ?? 'file'}-${i}`}
                  className="cursor-pointer border-border transition-colors hover:bg-muted/40"
                  onClick={() => setSelected(item)}
                >
                  <TableCell className="max-w-xs truncate font-mono text-xs text-muted-foreground">
                    {formatFilePath(item.file)}
                  </TableCell>
                  <TableCell className="text-xs">{formatCategoryName(item.category)}</TableCell>
                  <TableCell>
                    <span className={cn('text-xs font-medium', SEV_COLOR[sev] ?? '')}>
                      {sev}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    ${(item.cost_usd ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                    {(((item.adjusted_minutes ?? 0) as number) / 60).toFixed(1)}h
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums text-primary">
                    {item.combined_multiplier
                      ? `${item.combined_multiplier.toFixed(2)}x`
                      : '-'}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Drawer open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DrawerContent className="max-h-[85dvh] overflow-y-auto border-border bg-card">
          <DrawerHeader>
            <DrawerTitle className="text-sm font-medium">Cost Breakdown</DrawerTitle>
          </DrawerHeader>
          {selected ? (
            <div className="space-y-4 px-4 pb-8 text-sm">
              <div className="break-all rounded bg-muted/40 p-2 font-mono text-xs text-muted-foreground">
                {formatFilePath(selected.file)}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Category', formatCategoryName(selected.category)],
                  ['Severity', selected.severity || '-'],
                  ['Base effort', `${selected.base_minutes ?? '-'} min`],
                  ['Adjusted effort', `${selected.adjusted_minutes ?? '-'} min`],
                  ['Hourly rate', `$${selected.hourly_rate ?? '-'}/hr`],
                  ['Base cost', `$${(selected.base_cost_usd ?? 0).toLocaleString()}`],
                  ['Final cost', `$${(selected.cost_usd ?? 0).toLocaleString()}`],
                ].map(([label, value]) => (
                  <div key={label}>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="font-mono text-sm font-medium">{value}</p>
                  </div>
                ))}
              </div>
              {selected.cost_explanation ? (
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <p className="text-xs leading-5 text-muted-foreground">
                    {selected.cost_explanation}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}
        </DrawerContent>
      </Drawer>
    </>
  );
}

function FindingsCard({
  title,
  findings,
}: {
  title: string;
  findings: StructuredFinding[];
}) {
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          Highest-signal items surfaced from persistence and scan rollups.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {findings.length === 0 ? (
          <p className="text-sm text-muted-foreground">No findings available.</p>
        ) : (
          findings.slice(0, 6).map((finding) => {
            const sev = (finding.severity || 'low').toLowerCase();
            return (
              <div
                key={finding.id}
                className="rounded-lg border border-border bg-muted/20 p-3"
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <Badge variant="outline" className={cn('text-xs', SEVERITY_BADGE[sev] ?? '')}>
                    {sev}
                  </Badge>
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    ${Math.round(finding.cost_usd ?? 0).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-foreground">{finding.symbol_name || finding.category}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {formatFilePath(finding.file_path)}
                </p>
                {finding.business_impact ? (
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    {finding.business_impact}
                  </p>
                ) : null}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

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
    setJiraResult(null);
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
    setSlackSent(false);
    setJiraResult(null);
  };

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/integrations/status`)
      .then((r) => r.json())
      .then(setIntegrations)
      .catch(console.error);
  }, []);

  const handleSendSlack = async () => {
    if (!jobId) return;
    setSlackSending(true);
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/report/${jobId}/slack`, {
        method: 'POST',
      });
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
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/report/${jobId}/jira`, {
        method: 'POST',
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setJiraResult(data);
    } catch (err) {
      console.error('Jira failed:', err);
    } finally {
      setJiraCreating(false);
    }
  };

  const analysis = (result?.raw_analysis ?? result) as DebtReport | null;
  const debtScore = analysis?.debt_score ?? result?.debt_score ?? 0;
  const totalCost = analysis?.total_cost_usd ?? result?.total_cost_usd ?? 0;
  const totalHours =
    analysis?.total_remediation_hours ?? result?.total_remediation_hours ?? 0;
  const totalSprints =
    analysis?.total_remediation_sprints ?? result?.total_remediation_sprints ?? 0;
  const animatedCost = useCountUp(Math.round(totalCost));
  const animatedHours = useCountUp(Math.round(totalHours));
  const scoreColor =
    debtScore <= 3 ? 'text-emerald-400' : debtScore <= 6 ? 'text-amber-400' : 'text-red-400';
  const scoreSubtext =
    debtScore <= 3
      ? 'Low - healthy codebase'
      : debtScore <= 6
        ? 'Moderate - needs attention'
        : 'High - act now';
  const categoryData = Object.entries(analysis?.cost_by_category ?? {})
    .filter(([, value]) => typeof value === 'object' && (value?.cost_usd ?? 0) > 0)
    .map(([key, value]) => ({
      name: formatCategoryName(key),
      value: Math.round(value.cost_usd),
    }))
    .sort((a, b) => b.value - a.value);
  const priorityActions = (analysis?.priority_actions ?? []) as ActionItem[];
  const debtItems = (analysis?.debt_items ?? []) as DebtItemRecord[];
  const roi = analysis?.roi_analysis ?? {};
  const roiChartData = Array.from({ length: 12 }, (_, i) => ({
    month: `Month ${i + 1}`,
    'Cumulative Savings': Math.round(
      (((roi as { annual_maintenance_savings?: number }).annual_maintenance_savings ?? 0) /
        12) *
        (i + 1)
    ),
    'Fix Cost': (roi as { total_fix_cost?: number }).total_fix_cost ?? 0,
  }));
  const roadmapSections = Object.entries(scanRoadmap?.roadmap ?? {});
  const latestActive = richRepoHistory?.latest_active;
  const latestTrend = richRepoHistory?.latest;

  return (
    <div className="mx-auto w-full max-w-7xl">
      <section className="mb-8 grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-5">
          <div className="space-y-4">
            <Badge variant="outline" className="border-border bg-muted/20 text-muted-foreground">
              Vercel-grade debt visibility for engineering teams
            </Badge>
            <div className="space-y-3">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                Quantify technical debt with executive clarity and engineering detail.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                Scan a GitHub repository, turn hotspots into cost and effort signals,
                and move directly into remediation, reporting, Slack, and Jira.
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
                description: 'Priority actions, roadmap buckets, and exportable next steps.',
              },
              {
                icon: LayoutDashboard,
                title: 'Portfolio view',
                description: 'Trend and module views across multiple scans and repositories.',
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

      {appState === 'analyzing' ? (
        <section className="space-y-4">
          <ProgressBar jobId={jobId} onComplete={handleComplete} />
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

      {appState === 'complete' && analysis ? (
        <section className="space-y-6">
          {analysis.executive_summary ? (
            <Card className="border-border bg-card">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="size-4 text-primary" />
                  Executive Summary
                </CardTitle>
                <CardDescription>
                  LLM-assisted narrative summary grounded in analyzer output.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="max-w-4xl leading-7 text-foreground/90">
                  {analysis.executive_summary}
                </p>
              </CardContent>
            </Card>
          ) : null}

          <TooltipProvider>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="ghost" size="sm" onClick={handleReset}>
                  New Analysis
                </Button>
                {result?.scan_id ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/scans/${result.scan_id}`}>
                      Open Scan Detail
                      <ArrowRight className="ml-2 size-4" />
                    </Link>
                  </Button>
                ) : null}
                {currentGithubUrl ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link href={repoDetailPath(currentGithubUrl)}>
                      Open Repository Detail
                      <ArrowRight className="ml-2 size-4" />
                    </Link>
                  </Button>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDownloadPDF}
                      disabled={downloading}
                    >
                      {downloading ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Download className="size-4" />
                      )}
                      <span className="ml-2">{downloading ? 'Generating...' : 'PDF Report'}</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Download full PDF analysis</TooltipContent>
                </Tooltip>

                {integrations?.slack?.configured ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSendSlack}
                        disabled={slackSending || slackSent}
                        className={slackSent ? 'border-emerald-500/30 text-emerald-400' : ''}
                      >
                        {slackSent ? (
                          <>
                            <CheckCircle2 className="mr-2 size-4" />
                            Sent
                          </>
                        ) : slackSending ? (
                          <>
                            <Loader2 className="mr-2 size-4 animate-spin" />
                            Sending...
                          </>
                        ) : (
                          <>
                            <MessageSquare className="mr-2 size-4" />
                            Slack
                          </>
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Post to {integrations.slack.channel}</TooltipContent>
                  </Tooltip>
                ) : null}

                {integrations?.jira?.configured ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCreateJira}
                        disabled={jiraCreating || !!jiraResult}
                        className={jiraResult ? 'border-emerald-500/30 text-emerald-400' : ''}
                      >
                        {jiraResult ? (
                          <>
                            <CheckCircle2 className="mr-2 size-4" />
                            {jiraResult.total_created} tickets
                          </>
                        ) : jiraCreating ? (
                          <>
                            <Loader2 className="mr-2 size-4 animate-spin" />
                            Creating...
                          </>
                        ) : (
                          <>
                            <Ticket className="mr-2 size-4" />
                            Jira
                          </>
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      Create tickets in {integrations?.jira?.project} project
                    </TooltipContent>
                  </Tooltip>
                ) : null}

                {jiraResult?.epic_url ? (
                  <Link
                    href={jiraResult.epic_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline"
                  >
                    View Epic
                  </Link>
                ) : null}
              </div>
            </div>
          </TooltipProvider>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <KpiCard
              label="Debt Score"
              value={`${debtScore.toFixed(1)} / 10`}
              subtext={scoreSubtext}
              color={scoreColor}
              index={0}
            />
            <KpiCard
              label="Total Debt Cost"
              value={`$${animatedCost.toLocaleString()}`}
              subtext="Estimated remediation cost"
              index={1}
            />
            <KpiCard
              label="Remediation Time"
              value={`${animatedHours.toLocaleString()} hrs`}
              subtext={`~${totalSprints.toFixed(1)} engineering sprints`}
              index={2}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <Card className="border-border bg-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Cost by Category</CardTitle>
              </CardHeader>
              <CardContent>
                {categoryData.length === 0 ? (
                  <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                    No category data available
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-4">
                    <DonutChart
                      data={categoryData}
                      category="value"
                      index="name"
                      colors={CHART_COLORS}
                      valueFormatter={(value) => `$${value.toLocaleString()}`}
                      className="h-48"
                      showTooltip
                    />
                    <Legend
                      categories={categoryData.map((item) => item.name)}
                      colors={categoryData.map((_, index) => CHART_COLORS[index % CHART_COLORS.length])}
                      className="text-xs"
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle>Repository Signals</CardTitle>
                <CardDescription>
                  Current scan context blended with persisted repository rollups.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  {[
                    ['Scans', repoHistory?.total_scans ?? 0],
                    ['Active debt items', latestActive?.active_finding_count ?? repoSummary?.triage.active_findings ?? 0],
                    ['Modules', latestTrend?.module_count ?? repoSummary?.module_count ?? 0],
                    ['Quick wins', latestTrend?.quick_wins ?? repoSummary?.quick_wins ?? 0],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg border border-border bg-muted/20 p-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                        {label}
                      </p>
                      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-foreground">
                        {Number(value).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="rounded-lg border border-border bg-muted/20 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <GitBranch className="size-4 text-primary" />
                    <p className="text-sm font-medium text-foreground">Ownership snapshot</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">Bus factor</p>
                      <p className="font-mono text-lg tabular-nums">
                        {repoSummary?.ownership_summary.bus_factor ?? 0}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Active maintainers</p>
                      <p className="font-mono text-lg tabular-nums">
                        {repoSummary?.ownership_summary.active_contributors_90d ?? 0}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Top contributor share</p>
                      <p className="font-mono text-lg tabular-nums">
                        {Math.round((repoSummary?.ownership_summary.top_contributor_share ?? 0) * 100)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Siloed hotspots</p>
                      <p className="font-mono text-lg tabular-nums">
                        {repoSummary?.ownership_summary.siloed_hotspots ?? 0}
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
            <span className="font-mono text-primary">f</span>
            <span>
              Cost = base remediation time x severity multiplier x churn multiplier x hourly rate
            </span>
            <span className="ml-auto hidden text-muted-foreground/60 lg:inline">
              Not a line count - effort + risk estimate
            </span>
          </div>

          <Tabs defaultValue="actions" className="mt-6">
            <TabsList className="bg-muted">
              <TabsTrigger value="actions">Priority Actions</TabsTrigger>
              <TabsTrigger value="files">Debt Items</TabsTrigger>
              <TabsTrigger value="roi">ROI Analysis</TabsTrigger>
            </TabsList>

            <TabsContent value="actions" className="space-y-3">
              {priorityActions.length === 0 ? (
                <EmptyCard
                  title="Priority Actions"
                  description="No priority actions are available for this scan yet."
                />
              ) : (
                <div className="space-y-3">
                  {priorityActions.map((action, index) => (
                    <ActionCard key={`${action.title ?? 'action'}-${index}`} action={action} index={index} />
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="files">
              <DebtItemsTable items={debtItems} />
            </TabsContent>

            <TabsContent value="roi" className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Card className="border-border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Total Fix Cost</p>
                  <p className="font-mono text-xl font-semibold tabular-nums">
                    ${((roi as { total_fix_cost?: number }).total_fix_cost ?? 0).toLocaleString()}
                  </p>
                </Card>
                <Card className="border-border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Annual Savings</p>
                  <p className="font-mono text-xl font-semibold tabular-nums text-emerald-400">
                    $
                    {(
                      (roi as { annual_maintenance_savings?: number }).annual_maintenance_savings ??
                      0
                    ).toLocaleString()}
                    /yr
                  </p>
                </Card>
                <Card className="border-border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Payback Period</p>
                  <p className="font-mono text-xl font-semibold tabular-nums">
                    {(roi as { payback_months?: number }).payback_months
                      ? `${(roi as { payback_months?: number }).payback_months} mo`
                      : 'N/A'}
                  </p>
                </Card>
              </div>

              <Card className="border-border bg-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">
                    12-Month Savings Projection
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <AreaChart
                    data={roiChartData}
                    index="month"
                    categories={['Cumulative Savings', 'Fix Cost']}
                    colors={['teal', 'rose']}
                    valueFormatter={(value) => `$${value.toLocaleString()}`}
                    className="h-48"
                    showLegend
                    showGridLines={false}
                  />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle>Top Modules</CardTitle>
                <CardDescription>
                  Module-level concentration of cost, severity, and ownership risk.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {((scanModules?.modules ?? repoSummary?.top_modules) || []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No module summaries available.</p>
                ) : (
                  <div className="space-y-3">
                    {(scanModules?.modules ?? repoSummary?.top_modules ?? [])
                      .slice(0, 6)
                      .map((module) => (
                        <div
                          key={module.module}
                          className="rounded-lg border border-border bg-muted/20 p-3"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <p className="truncate text-sm font-medium text-foreground">
                              {module.module}
                            </p>
                            <span className="font-mono text-xs tabular-nums text-muted-foreground">
                              ${Math.round(module.total_cost_usd).toLocaleString()}
                            </span>
                          </div>
                          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{module.finding_count} findings</span>
                            <span>-</span>
                            <span>{module.total_effort_hours.toFixed(1)}h</span>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle>Roadmap Buckets</CardTitle>
                <CardDescription>
                  Structured roadmap output grouped by remediation horizon.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {roadmapSections.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No roadmap data available.</p>
                ) : (
                  roadmapSections.slice(0, 4).map(([bucket, items]) => (
                    <div key={bucket} className="rounded-lg border border-border bg-muted/20 p-3">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-foreground">
                          {formatCategoryName(bucket)}
                        </p>
                        <Badge variant="outline">{items.length}</Badge>
                      </div>
                      <div className="space-y-2">
                        {items.slice(0, 3).map((item) => (
                          <div key={item.finding_id} className="rounded-md bg-background/40 p-2">
                            <p className="text-sm text-foreground">{item.title}</p>
                            <p className="mt-1 font-mono text-xs text-muted-foreground">
                              {formatFilePath(item.file_path)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle>Data Confidence</CardTitle>
                <CardDescription>
                  Source transparency for rate and scoring context.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-border bg-muted/20 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    Rate confidence
                  </p>
                  <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">
                    {analysis.hourly_rates?.confidence?.toUpperCase() || 'N/A'}
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 p-4">
                  <p className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    Data sources
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(analysis.data_sources_used ?? []).length === 0 ? (
                      <span className="text-sm text-muted-foreground">No source metadata available.</span>
                    ) : (
                      analysis.data_sources_used?.map((source) => (
                        <Badge key={source} variant="outline">
                          {source}
                        </Badge>
                      ))
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <FindingsCard
              title="Unresolved Findings"
              findings={unresolvedFindings?.items ?? []}
            />
            <FindingsCard
              title="Current Scan Findings"
              findings={scanFindings?.findings ?? []}
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}
