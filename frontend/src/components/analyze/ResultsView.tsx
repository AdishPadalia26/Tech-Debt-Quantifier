'use client';

import { useEffect, useState } from 'react';
import { Card as TremorCard } from '@tremor/react';
import { motion } from 'motion/react';
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
import { CostCategoryDonut } from '@/components/charts/CostCategoryDonut';
import { ParetoChart, paretoStats } from '@/components/charts/ParetoChart';
import { RoiBreakEvenChart } from '@/components/charts/RoiBreakEvenChart';
import { categoryLabel } from '@/lib/categories';
import { humanize } from '@/lib/format';
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
import { EstimateQuality } from './EstimateQuality';
import { HeadlineHero } from './HeadlineHero';
import { IntegrationActions } from './IntegrationActions';
import { ViewModeToggle, useViewMode } from './ViewModeToggle';

// ─── Constants ────────────────────────────────────────────────

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-danger/15 text-danger border-danger/20',
  high: 'bg-severity-high/15 text-severity-high border-severity-high/20',
  medium: 'bg-warning/15 text-warning border-warning/20',
  low: 'bg-success/15 text-success border-success/20',
};

const SEV_COLOR: Record<string, string> = {
  critical: 'text-danger',
  high: 'text-severity-high',
  medium: 'text-warning',
  low: 'text-success',
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
  function?: string;
  principal?: boolean;
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
                      ? 'bg-success/15 text-success'
                      : action.estimation_confidence === 'medium'
                        ? 'bg-warning/15 text-warning'
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
                  monthlySavings > 0 ? 'text-success' : 'text-muted-foreground'
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
                  <TableCell className="text-xs">{categoryLabel(item.category)}</TableCell>
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
                    ['Category', categoryLabel(selected.category)],
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
                            ? 'bg-danger/15 text-danger'
                            : finding.ownership_risk === 'high'
                              ? 'bg-severity-high/15 text-severity-high'
                              : 'bg-warning/15 text-warning'
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
  critical: 'text-danger',
  high: 'text-severity-high',
  medium: 'text-warning',
  low: 'text-success',
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
                    <span className="text-danger font-medium">critical risk</span>
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
  const [viewMode, setViewMode] = useViewMode();
  const [activeTab, setActiveTab] = useState('actions');
  const isEngineer = viewMode === 'engineer';
  const tab =
    !isEngineer && (activeTab === 'files' || activeTab === 'contributors')
      ? 'actions'
      : activeTab;

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
    debtScore <= 3 ? 'text-success' : debtScore <= 6 ? 'text-warning' : 'text-danger';
  const scoreSubtext =
    debtScore <= 3
      ? 'Low - healthy codebase'
      : debtScore <= 6
        ? 'Moderate - needs attention'
        : 'High - act now';

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

  const roiValues = roi as {
    total_fix_cost?: number;
    annual_maintenance_savings?: number;
    payback_months?: number;
    '3_year_roi_pct'?: number;
  };

  const pareto = paretoStats(debtItems);
  const topCount = Math.min(10, pareto.rows.length);
  const topShare = pareto.shareOfTop(topCount);
  const repoName =
    currentGithubUrl
      .replace(/\/+$/, '')
      .replace(/\.git$/, '')
      .split('/')
      .pop() || null;
  const totalCostRange = analysis?.total_cost_range ?? result?.total_cost_range;

  const roadmapSections = Object.entries(
    scanRoadmap?.roadmap ??
      ((analysis as { roadmap?: Record<string, unknown[]> } | undefined)?.roadmap ?? {})
  ) as [string, Array<{ finding_id: string; title: string; file_path: string }>][];

  const latestActive = richRepoHistory?.latest_active;
  const latestTrend = richRepoHistory?.latest;

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <ViewModeToggle mode={viewMode} onChange={setViewMode} />
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
      </div>

      <HeadlineHero
        repoName={repoName}
        totalCost={baseTotalCost}
        range={totalCostRange}
        hours={baseTotalHours}
        topShare={topShare}
        topCount={topCount}
      />

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

      <EstimateQuality
        estimation_stats={analysis?.estimation_stats ?? result?.estimation_stats}
        warnings={analysis?.warnings ?? result?.warnings}
        total_cost_range={analysis?.total_cost_range ?? result?.total_cost_range}
        non_principal_cost={analysis?.non_principal_cost ?? result?.non_principal_cost}
        hourly_rates={analysis?.hourly_rates ?? result?.hourly_rates}
        model_version={analysis?.model_version ?? result?.model_version}
      />

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

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="min-w-0 border-border bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Cost by Category</CardTitle>
          </CardHeader>
          <CardContent>
            <CostCategoryDonut
              costByCategory={analysis?.cost_by_category ?? result?.cost_by_category}
            />
          </CardContent>
        </Card>

        <Card className="min-w-0 border-border bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Where the money is (80/20)</CardTitle>
            <CardDescription>
              A few items usually drive most of the cost. Fix those first.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ParetoChart items={debtItems} />
          </CardContent>
        </Card>
      </div>

      {isEngineer && (
        <>
          <div className="grid gap-4">
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
        </>
      )}

      <Tabs value={tab} onValueChange={setActiveTab} className="mt-6">
        <TabsList className="h-auto flex-wrap bg-muted">
          <TabsTrigger value="actions">Priority Actions</TabsTrigger>
          {isEngineer && <TabsTrigger value="files">Debt Items</TabsTrigger>}
          <TabsTrigger value="roi">ROI Analysis</TabsTrigger>
          {isEngineer && (
            <TabsTrigger value="contributors" className="flex items-center gap-1.5">
              <Users className="size-3.5" />
              Contributors
            </TabsTrigger>
          )}
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

        {isEngineer && (
          <TabsContent value="files">
            <DebtItemsTable items={debtItems} />
          </TabsContent>
        )}

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
              <p className="font-mono text-xl font-semibold tabular-nums text-success">
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

          <Card className="min-w-0 border-border bg-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">When does fixing it pay off?</CardTitle>
              <CardDescription>
                Cumulative net = monthly savings x months - total fix cost.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <RoiBreakEvenChart
                totalFixCost={roiValues.total_fix_cost}
                annualSavings={roiValues.annual_maintenance_savings}
                paybackMonths={roiValues.payback_months}
                roi3yPct={roiValues['3_year_roi_pct']}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {isEngineer && (
          <TabsContent value="contributors" className="space-y-6">
            <ContributorInsights
              ownershipSummary={repoSummary?.ownership_summary ?? null}
              findings={currentScanFindings}
            />
          </TabsContent>
        )}
      </Tabs>

      <div className={cn('grid gap-4', isEngineer && 'xl:grid-cols-3')}>
        {isEngineer && (
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
        )}

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
                      {humanize(bucket)}
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

        {isEngineer && (
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
        )}
      </div>

      {isEngineer && (
      <div className="grid gap-4 xl:grid-cols-2">
        <FindingsCard title="Unresolved Findings" findings={unresolvedFindings?.items ?? []} />
        <FindingsCard title="Current Scan Findings" findings={currentScanFindings} />
      </div>
      )}
    </section>
  );
}
