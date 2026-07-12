'use client';

import { useEffect, useState } from 'react';
import { Card as TremorCard } from '@tremor/react';
import { motion } from 'motion/react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';
import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  Legend as RechartsLegend,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ChevronDown,
  Clock,
  DollarSign,
  GitBranch,
  Sparkles,
  TrendingDown,
  Users,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
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
import { IntegrationActions } from './IntegrationActions';

// ─── Constants ────────────────────────────────────────────────

const CATEGORY_CHART_COLORS = [
  '#4f98a3',
  '#f59e0b',
  '#10b981',
  '#f97316',
  '#60a5fa',
  '#f43f5e',
  '#a78bfa',
  '#22c55e',
];

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

// ─── Local types ──────────────────────────────────────────────

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
  estimation_confidence?: string;
  fix_summary?: string;
  primary_risk?: string;
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

type IntegrationsConfig = {
  slack: { configured: boolean; channel: string };
  jira: { configured: boolean; server: string; project: string };
};

// ─── Helpers ──────────────────────────────────────────────────

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
      if (progress < 1) frame = requestAnimationFrame(tick);
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
  return (value || '')
    .replace(/^\/tmp\/repos\/[^/]+\//, '')
    .replace(/^[A-Za-z]:\/.*?tech-debt-repos\/[^/]+\/?/i, '')
    .replace(
      /^[A-Za-z]:\/.*?tech-debt-quantifier\/backend\/\.cache\/tech-debt-repos\/[^/]+\/?/i,
      ''
    )
    .replace(/:$/, '')
    .replace(/\?$/, '')
    .replace(/\\/g, '/');
}

function formatModulePath(value?: string | null) {
  const normalized = formatFilePath(value);
  if (!normalized || normalized === '.') return 'root';
  return normalized;
}

// ─── Sub-components ───────────────────────────────────────────

function EmptyCard({ title, description }: { title: string; description: string }) {
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
  tooltipContent,
}: {
  label: string;
  value: string;
  subtext?: string;
  color?: string;
  index?: number;
  tooltipContent?: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <TremorCard className="border-border bg-card p-5">
        <p className="mb-1 text-xs uppercase tracking-[0.18em] text-muted-foreground flex items-center gap-1">
          {label}
          {tooltipContent && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="cursor-help text-muted-foreground/60 hover:text-muted-foreground">
                  ℹ
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs bg-card border-border shadow-xl p-3">
                {tooltipContent}
              </TooltipContent>
            </Tooltip>
          )}
        </p>
        <p className={cn('font-mono text-3xl font-semibold tabular-nums', color)}>{value}</p>
        {subtext ? <p className="mt-1 text-xs text-muted-foreground">{subtext}</p> : null}
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
              {action.estimation_confidence && (
                <span
                  className={cn(
                    'text-xs px-2 py-0.5 rounded-full font-medium',
                    action.estimation_confidence === 'high'
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : action.estimation_confidence === 'medium'
                        ? 'bg-amber-500/15 text-amber-400'
                        : 'bg-muted text-muted-foreground'
                  )}
                >
                  {action.estimation_confidence === 'high'
                    ? '✓ High confidence'
                    : action.estimation_confidence === 'medium'
                      ? '~ Medium confidence'
                      : '⚠ Formula fallback'}
                </span>
              )}
              <span className="text-xs text-muted-foreground">Sprint {sprint}</span>
            </div>
            <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-foreground">
              ${(action.estimated_cost ?? 0).toLocaleString()}
            </span>
          </div>

          <p className="mb-1 text-sm font-medium text-foreground">
            {action.title || action.file_or_module || 'Unknown item'}
          </p>

          {action.fix_summary && (
            <p className="text-xs text-muted-foreground mt-0.5 mb-1 italic">
              Fix: {action.fix_summary}
            </p>
          )}

          {action.file_or_module || action.file ? (
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
                    <p className="mb-2 text-xs leading-5 text-muted-foreground">{explanation}</p>
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
                {(
                  [
                    ['Category', formatCategoryName(selected.category)],
                    ['Severity', selected.severity || '-'],
                    ['Base effort', `${selected.base_minutes ?? '-'} min`],
                    ['Adjusted effort', `${selected.adjusted_minutes ?? '-'} min`],
                    ['Hourly rate', `$${selected.hourly_rate ?? '-'}/hr`],
                    ['Base cost', `$${(selected.base_cost_usd ?? 0).toLocaleString()}`],
                    ['Final cost', `$${(selected.cost_usd ?? 0).toLocaleString()}`],
                  ] as [string, string][]
                ).map(([label, value]) => (
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
                  <Badge
                    variant="outline"
                    className={cn('text-xs', SEVERITY_BADGE[sev] ?? '')}
                  >
                    {sev}
                  </Badge>
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    ${Math.round(finding.cost_usd ?? 0).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-foreground">
                  {finding.symbol_name || finding.category}
                </p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {formatFilePath(finding.file_path)}
                </p>
                {finding.top_author ? (
                  <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
                    <span className="text-muted-foreground/60">Owner:</span>
                    <span className="font-medium text-foreground/80">{finding.top_author}</span>
                    {finding.ownership_risk && finding.ownership_risk !== 'low' ? (
                      <span
                        className={cn(
                          'ml-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
                          finding.ownership_risk === 'critical'
                            ? 'bg-red-500/15 text-red-400'
                            : finding.ownership_risk === 'high'
                              ? 'bg-orange-500/15 text-orange-400'
                              : 'bg-amber-500/15 text-amber-400'
                        )}
                      >
                        {finding.ownership_risk} risk
                      </span>
                    ) : null}
                  </p>
                ) : null}
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

type SeniorityLevel = 'junior' | 'mid' | 'senior';

const SENIORITY_MULTIPLIER: Record<SeniorityLevel, number> = {
  junior: 2.0,
  mid: 1.0,
  senior: 0.5,
};

const SENIORITY_LABEL: Record<SeniorityLevel, string> = {
  junior: 'Junior (2×)',
  mid: 'Mid (1×)',
  senior: 'Senior (0.5×)',
};

// ─── Contributor Insights ─────────────────────────────────────

const RISK_COLOR: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-amber-400',
  low: 'text-emerald-400',
};

interface ContributorRow {
  author: string;
  findingCount: number;
  totalCost: number;
  topRisk: string;
  files: string[];
}

function ContributorInsights({
  ownershipSummary,
  findings,
}: {
  ownershipSummary: {
    commit_sample_size: number;
    unique_contributors: number;
    active_contributors_90d: number;
    bus_factor: number;
    top_contributor_share: number;
    siloed_hotspots: number;
    handoff_hotspots: number;
  } | null;
  findings: StructuredFinding[];
}) {
  const RISK_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

  const byAuthor = findings.reduce<Record<string, ContributorRow>>((acc, f) => {
    const author = f.top_author ?? 'Unknown';
    if (!acc[author]) {
      acc[author] = { author, findingCount: 0, totalCost: 0, topRisk: 'low', files: [] };
    }
    acc[author].findingCount += 1;
    acc[author].totalCost += f.cost_usd;
    if ((RISK_RANK[f.ownership_risk ?? 'low'] ?? 0) > (RISK_RANK[acc[author].topRisk] ?? 0)) {
      acc[author].topRisk = f.ownership_risk ?? 'low';
    }
    if (!acc[author].files.includes(f.file_path)) {
      acc[author].files.push(f.file_path);
    }
    return acc;
  }, {});

  const rows = Object.values(byAuthor).sort((a, b) => b.totalCost - a.totalCost);

  const silos = findings.filter(
    (f) => f.ownership_risk === 'critical' || (f.owner_count !== null && (f.owner_count ?? 0) <= 1),
  );

  return (
    <div className="space-y-6">
      {ownershipSummary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Bus factor', ownershipSummary.bus_factor],
            ['Active maintainers', ownershipSummary.active_contributors_90d],
            ['Siloed hotspots', ownershipSummary.siloed_hotspots],
            ['Top contributor', `${Math.round(ownershipSummary.top_contributor_share * 100)}%`],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg border border-border bg-muted/20 p-3">
              <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
              <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</p>
            </div>
          ))}
        </div>
      )}

      <Card className="border-border bg-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Per-Developer Debt Attribution</CardTitle>
          <CardDescription>
            Findings grouped by the file&apos;s primary owner derived from git history.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No ownership data — run a scan on a repo with git history.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    <th className="pb-2 pr-4">Contributor</th>
                    <th className="pb-2 pr-4 text-right">Findings</th>
                    <th className="pb-2 pr-4 text-right">Debt cost</th>
                    <th className="pb-2 pr-4">Top risk</th>
                    <th className="pb-2">Files owned</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((row) => (
                    <tr key={row.author} className="py-2">
                      <td className="py-2 pr-4 font-medium text-foreground">{row.author}</td>
                      <td className="py-2 pr-4 text-right font-mono tabular-nums">{row.findingCount}</td>
                      <td className="py-2 pr-4 text-right font-mono tabular-nums">
                        ${Math.round(row.totalCost).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4">
                        <span className={cn('capitalize text-xs font-medium', RISK_COLOR[row.topRisk] ?? 'text-muted-foreground')}>
                          {row.topRisk}
                        </span>
                      </td>
                      <td className="py-2 text-xs text-muted-foreground">
                        {row.files.length} file{row.files.length !== 1 ? 's' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {silos.length > 0 && (
        <Card className="border-border bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Knowledge Silos</CardTitle>
            <CardDescription>
              Files with critical ownership concentration — single contributor or extreme share.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {silos.slice(0, 10).map((f) => (
                <div
                  key={f.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs text-foreground">{formatFilePath(f.file_path)}</p>
                    {f.top_author && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Owner: <span className="font-medium text-foreground/80">{f.top_author}</span>
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 text-xs">
                    {f.owner_count !== null && (
                      <span className="text-muted-foreground">{f.owner_count} contributor{(f.owner_count ?? 0) !== 1 ? 's' : ''}</span>
                    )}
                    <span className="text-red-400 font-medium">critical risk</span>
                  </div>
                </div>
              ))}
              {silos.length > 10 && (
                <p className="text-center text-xs text-muted-foreground pt-1">
                  +{silos.length - 10} more silos
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────

interface ResultsViewProps {
  result: DebtReport;
  repoHistory: RepoHistory | null;
  repoSummary: RepoSummaryRollup | null;
  richRepoHistory: RichRepoTrend | null;
  unresolvedFindings: UnresolvedFindingsResponse | null;
  scanModules: ScanModulesResponse | null;
  scanRoadmap: ScanRoadmapResponse | null;
  scanFindings: ScanFindingsResponse | null;
  currentGithubUrl: string;
  integrations: IntegrationsConfig | null;
  onReset: () => void;
}

export function ResultsView({
  result,
  repoHistory,
  repoSummary,
  richRepoHistory,
  unresolvedFindings,
  scanModules,
  scanRoadmap,
  scanFindings,
  currentGithubUrl,
  integrations,
  onReset,
}: ResultsViewProps) {
  const [seniorityLevel, setSeniorityLevel] = useState<SeniorityLevel>('mid');

  const analysis = (result?.raw_analysis ?? result) as DebtReport | null;

  const debtScore = analysis?.debt_score ?? result?.debt_score ?? repoSummary?.debt_score ?? 0;
  const baseTotalCost =
    analysis?.total_cost_usd ?? result?.total_cost_usd ?? repoSummary?.total_cost_usd ?? 0;
  const baseTotalHours =
    analysis?.total_remediation_hours ??
    result?.total_remediation_hours ??
    repoSummary?.total_hours ??
    0;
  const totalSprints =
    analysis?.total_remediation_sprints ?? result?.total_remediation_sprints ?? 0;

  const hoursByLevel = analysis?.total_hours_by_level ?? result?.total_hours_by_level;
  const totalHours = hoursByLevel
    ? (hoursByLevel[seniorityLevel] ?? baseTotalHours)
    : baseTotalHours * SENIORITY_MULTIPLIER[seniorityLevel];
  const totalCost = baseTotalCost * (totalHours / (baseTotalHours || 1));

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
      color:
        CATEGORY_CHART_COLORS[
          Object.keys(analysis?.cost_by_category ?? {}).indexOf(key) %
            CATEGORY_CHART_COLORS.length
        ],
    }))
    .sort((a, b) => b.value - a.value);

  const nestedPriorityActions = Array.isArray(analysis?.priority_actions)
    ? (analysis?.priority_actions as ActionItem[])
    : [];
  const priorityActions = (
    nestedPriorityActions.length > 0
      ? nestedPriorityActions
      : ((result?.priority_actions ?? []) as ActionItem[])
  ) as ActionItem[];

  const debtItems = (analysis?.debt_items ?? []) as DebtItemRecord[];

  const currentScanFindings = (
    scanFindings?.findings ??
    ((analysis?.findings as StructuredFinding[] | undefined) ?? [])
  ) as StructuredFinding[];

  const nestedRoi =
    analysis?.roi_analysis &&
    typeof analysis.roi_analysis === 'object' &&
    Object.keys(analysis.roi_analysis).length > 0
      ? analysis.roi_analysis
      : null;
  const roi = nestedRoi ?? result?.roi_analysis ?? {};

  const roiChartData = Array.from({ length: 12 }, (_, i) => ({
    month: `Month ${i + 1}`,
    'Cumulative Savings': Math.round(
      (((roi as { annual_maintenance_savings?: number }).annual_maintenance_savings ?? 0) / 12) *
        (i + 1)
    ),
    'Fix Cost': (roi as { total_fix_cost?: number }).total_fix_cost ?? 0,
  }));

  const roadmapSections = Object.entries(
    scanRoadmap?.roadmap ??
      ((analysis as { roadmap?: Record<string, unknown[]> } | undefined)?.roadmap ?? {})
  ) as [string, Array<{ finding_id: string; title: string; file_path: string }>][];

  const latestActive = richRepoHistory?.latest_active;
  const latestTrend = richRepoHistory?.latest;

  return (
    <section className="space-y-6">
      {analysis?.executive_summary ? (
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
            <p className="max-w-4xl leading-7 text-foreground/90">{analysis.executive_summary}</p>
          </CardContent>
        </Card>
      ) : null}

      <IntegrationActions
        jobId={result?.job_id ?? ''}
        scanId={result?.scan_id}
        currentGithubUrl={currentGithubUrl}
        integrations={integrations}
        onReset={onReset}
      />

      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-muted-foreground">Estimate by seniority:</span>
        <div className="flex overflow-hidden rounded-md border border-border">
          {(['junior', 'mid', 'senior'] as SeniorityLevel[]).map((level) => (
            <button
              key={level}
              onClick={() => setSeniorityLevel(level)}
              className={cn(
                'border-r border-border px-3 py-1 text-xs font-medium transition-colors last:border-r-0',
                seniorityLevel === level
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card text-muted-foreground hover:bg-muted',
              )}
            >
              {SENIORITY_LABEL[level]}
            </button>
          ))}
        </div>
      </div>

      <TooltipProvider>
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
            tooltipContent={
              <div className="w-72 text-xs text-muted-foreground">
                <p className="font-semibold text-foreground mb-1">How costs are estimated</p>
                <p>
                  Each debt item is analyzed by the local AI model, which estimates realistic
                  remediation hours based on the actual code context. Those hours are then adjusted
                  using git churn, severity, and repo risk multipliers, then multiplied by an
                  hourly engineering rate.
                </p>
                <p className="mt-1 text-muted-foreground/70">
                  Formula: LLM hours × severity × churn × repo risk × hourly rate
                </p>
              </div>
            }
          />
          <KpiCard
            label="Remediation Time"
            value={`${animatedHours.toLocaleString()} hrs`}
            subtext={`~${totalSprints.toFixed(1)} engineering sprints`}
            index={2}
          />
        </div>
      </TooltipProvider>

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
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={categoryData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={64}
                        outerRadius={102}
                        paddingAngle={3}
                        stroke="rgba(15, 14, 13, 0.95)"
                        strokeWidth={2}
                      >
                        {categoryData.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <text
                        x="50%"
                        y="47%"
                        textAnchor="middle"
                        className="fill-[#797876] text-[11px] uppercase tracking-[0.18em]"
                      >
                        Total
                      </text>
                      <text
                        x="50%"
                        y="56%"
                        textAnchor="middle"
                        className="fill-[#cdccca] font-mono text-[20px] font-semibold"
                      >
                        ${animatedCost.toLocaleString()}
                      </text>
                      <RechartsTooltip
                        formatter={(value: unknown) => {
                          const numericValue = Array.isArray(value)
                            ? Number(value[0] ?? 0)
                            : Number(value ?? 0);
                          return [`$${numericValue.toLocaleString()}`, 'Cost'];
                        }}
                        contentStyle={{
                          backgroundColor: '#1c1b19',
                          border: '1px solid rgba(205, 204, 202, 0.12)',
                          borderRadius: '10px',
                          color: '#cdccca',
                        }}
                        itemStyle={{ color: '#cdccca' }}
                        labelStyle={{ color: '#797876' }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs">
                  {categoryData.map((item) => (
                    <div key={item.name} className="flex items-center gap-2 text-foreground">
                      <span
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: item.color }}
                      />
                      <span>{item.name}</span>
                    </div>
                  ))}
                </div>
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
              {(
                [
                  ['Scans', repoHistory?.total_scans ?? 0],
                  [
                    'Active debt items',
                    latestActive?.active_finding_count ??
                      repoSummary?.triage.active_findings ??
                      0,
                  ],
                  ['Modules', latestTrend?.module_count ?? repoSummary?.module_count ?? 0],
                  ['Quick wins', latestTrend?.quick_wins ?? repoSummary?.quick_wins ?? 0],
                ] as [string, number][]
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-lg border border-border bg-muted/20 p-3"
                >
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
                    {Math.round(
                      (repoSummary?.ownership_summary.top_contributor_share ?? 0) * 100
                    )}
                    %
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
          <TabsTrigger value="contributors" className="flex items-center gap-1.5">
            <Users className="size-3.5" />
            Contributors
          </TabsTrigger>
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
                <ActionCard
                  key={`${action.title ?? 'action'}-${index}`}
                  action={action}
                  index={index}
                />
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
                ${(
                  (roi as { total_fix_cost?: number }).total_fix_cost ?? 0
                ).toLocaleString()}
              </p>
            </Card>
            <Card className="border-border bg-card p-4">
              <p className="mb-1 text-xs text-muted-foreground">Annual Savings</p>
              <p className="font-mono text-xl font-semibold tabular-nums text-emerald-400">
                $
                {(
                  (roi as { annual_maintenance_savings?: number }).annual_maintenance_savings ?? 0
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
              <CardTitle className="text-sm font-medium">12-Month Savings Projection</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsAreaChart data={roiChartData}>
                    <defs>
                      <linearGradient id="savingsFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0.03} />
                      </linearGradient>
                      <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f97316" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#f97316" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(205, 204, 202, 0.08)" vertical={false} />
                    <XAxis
                      dataKey="month"
                      tick={{ fill: '#797876', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#797876', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
                    />
                    <RechartsTooltip
                      formatter={(value: unknown, name: unknown) => {
                        const numericValue = Array.isArray(value)
                          ? Number(value[0] ?? 0)
                          : Number(value ?? 0);
                        return [`$${numericValue.toLocaleString()}`, String(name ?? '')];
                      }}
                      contentStyle={{
                        backgroundColor: '#1c1b19',
                        border: '1px solid rgba(205, 204, 202, 0.12)',
                        borderRadius: '10px',
                        color: '#cdccca',
                      }}
                      itemStyle={{ color: '#cdccca' }}
                      labelStyle={{ color: '#797876' }}
                    />
                    <RechartsLegend wrapperStyle={{ color: '#cdccca', fontSize: '12px' }} />
                    <Area
                      type="monotone"
                      dataKey="Cumulative Savings"
                      stroke="#10b981"
                      fill="url(#savingsFill)"
                      strokeWidth={3}
                    />
                    <Area
                      type="monotone"
                      dataKey="Fix Cost"
                      stroke="#f97316"
                      fill="url(#costFill)"
                      strokeWidth={3}
                    />
                  </RechartsAreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="contributors" className="space-y-6">
          <ContributorInsights
            ownershipSummary={repoSummary?.ownership_summary ?? null}
            findings={currentScanFindings}
          />
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
                          {formatModulePath(module.module)}
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
                <div
                  key={bucket}
                  className="rounded-lg border border-border bg-muted/20 p-3"
                >
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
            <CardDescription>Source transparency for rate and scoring context.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/20 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Rate confidence
              </p>
              <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">
                {analysis?.hourly_rates?.confidence?.toUpperCase() || 'N/A'}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-muted/20 p-4">
              <p className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Data sources
              </p>
              <div className="flex flex-wrap gap-2">
                {(analysis?.data_sources_used ?? []).length === 0 ? (
                  <span className="text-sm text-muted-foreground">
                    No source metadata available.
                  </span>
                ) : (
                  analysis?.data_sources_used?.map((source) => (
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
        <FindingsCard title="Unresolved Findings" findings={unresolvedFindings?.items ?? []} />
        <FindingsCard title="Current Scan Findings" findings={currentScanFindings} />
      </div>
    </section>
  );
}
