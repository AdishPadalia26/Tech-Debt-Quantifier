import { AlertTriangle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { formatUsd } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { DebtReport } from '@/types';

type Props = Pick<
  DebtReport,
  | 'estimation_stats'
  | 'warnings'
  | 'total_cost_range'
  | 'non_principal_cost'
  | 'hourly_rates'
  | 'model_version'
>;

/** Range, estimate-quality badge, warnings and rate-source notes. Renders nothing if keys are absent. */
export function EstimateQuality({
  estimation_stats: stats,
  warnings,
  total_cost_range: range,
  non_principal_cost: nonPrincipal,
  hourly_rates: rates,
  model_version: modelVersion,
}: Props) {
  const excluded = Object.values(nonPrincipal ?? {}).reduce<number>(
    (sum, v) => sum + (typeof v === 'number' ? v : 0),
    0,
  );
  const liveCount = Array.isArray(rates?.live_sources)
    ? rates.live_sources.length
    : typeof rates?.live_sources === 'number'
      ? rates.live_sources
      : null;
  const showRates = rates && (rates.live !== undefined || liveCount !== null);
  const warn = stats && stats.fallback_ratio > 0.1;
  const warningList = (warnings ?? []).filter(Boolean);

  if (!range && !stats && !warningList.length && !excluded && !showRates && !modelVersion) {
    return null;
  }

  const statsTitle = stats
    ? [
        [stats.llm_provider, stats.llm_model].filter(Boolean).join(' / '),
        stats.llm_error ? `Error: ${stats.llm_error}` : '',
      ]
        .filter(Boolean)
        .join(' - ') || undefined
    : undefined;

  return (
    <div className="space-y-2">
      {warningList.length > 0 && (
        <div
          role="alert"
          className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground"
        >
          <p className="mb-1 flex items-center gap-1.5 font-medium text-warning">
            <AlertTriangle className="size-3.5" aria-hidden="true" />
            Warning
          </p>
          <ul className="list-disc space-y-0.5 pl-5">
            {warningList.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
        {range && (
          <span className="font-mono tabular-nums text-foreground">
            Likely range {formatUsd(range.p10)} – {formatUsd(range.p90)}
          </span>
        )}
        {stats && stats.total > 0 && (
          <Badge
            variant="outline"
            title={statsTitle}
            className={cn(warn && 'border-warning/30 bg-warning/15 text-warning')}
          >
            {warn ? 'Low LLM coverage: ' : ''}LLM estimated {stats.llm} / {stats.total}
          </Badge>
        )}
        {showRates && (
          <span>
            {rates.live
              ? `Rates: live${liveCount ? ` (${liveCount} sources)` : ''}`
              : 'Rates: reference table'}
          </span>
        )}
        {modelVersion && <span className="font-mono">model {modelVersion}</span>}
      </div>

      {excluded > 0 && (
        <p className="text-xs text-muted-foreground">
          Test, docs &amp; example code excluded from total ({formatUsd(excluded)} reported
          separately)
        </p>
      )}
    </div>
  );
}
