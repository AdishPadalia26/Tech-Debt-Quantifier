import { Folder } from 'lucide-react';

import { RoiBreakEvenChart } from '@/components/charts/RoiBreakEvenChart';
import { formatUsd } from '@/lib/format';
import { PriorityAction, ROIAnalysis } from '@/types';

interface Props {
  actions: PriorityAction[];
  roiAnalysis?: ROIAnalysis;
}

const RANK_LABELS = ['Fix first', 'Fix second', 'Fix third'];

const CONFIDENCE: Record<string, { label: string; className: string }> = {
  high: { label: 'High-confidence estimate', className: 'bg-success/15 text-success' },
  medium: { label: 'Medium-confidence estimate', className: 'bg-warning/15 text-warning' },
  low: { label: 'Formula fallback', className: 'bg-muted text-muted-foreground' },
};

function paybackLabel(cost: number, perMonth: number): string {
  if (perMonth <= 0) return 'n/a';
  return `${Math.ceil(cost / perMonth)} months`;
}

export default function PriorityActions({ actions, roiAnalysis }: Props) {
  if (!actions || actions.length === 0) {
    return (
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="mb-2 text-lg font-semibold text-foreground">Priority actions</h2>
        <p className="text-muted-foreground">No priority actions available for this scan.</p>
      </section>
    );
  }

  return (
    <section className="min-w-0 space-y-4" aria-labelledby="priority-heading">
      <h2 id="priority-heading" className="text-lg font-semibold text-foreground">
        What to fix first
      </h2>

      <ol className="space-y-3">
        {actions.map((action, i) => {
          const confidence = action.estimation_confidence
            ? CONFIDENCE[action.estimation_confidence] ?? CONFIDENCE.low
            : null;
          return (
            <li
              key={action.rank}
              className={`rounded-xl border bg-card p-6 ${
                i === 0 ? 'border-primary/40' : 'border-border'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="tabular font-mono text-xs text-primary">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="text-xs font-medium text-muted-foreground">
                      {RANK_LABELS[i] ?? `Fix #${i + 1}`}
                    </span>
                    {confidence && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${confidence.className}`}
                      >
                        {confidence.label}
                      </span>
                    )}
                  </div>
                  <h3 className="mt-1.5 font-semibold text-foreground [overflow-wrap:anywhere]">{action.title}</h3>
                  <p className="mt-1 flex min-w-0 items-start gap-1.5 font-mono text-xs text-muted-foreground">
                    <Folder className="mt-px size-3.5 shrink-0" aria-hidden />
                    <span className="break-all">{action.file_or_module}</span>
                  </p>
                </div>
                <span className="whitespace-nowrap rounded-full bg-muted px-2 py-1 text-xs text-foreground">
                  {action.sprint}
                </span>
              </div>

              <p className="mt-3 text-sm text-foreground">{action.why}</p>
              {action.fix_summary && (
                <p className="mt-1 text-sm text-muted-foreground">Fix: {action.fix_summary}</p>
              )}

              <dl className="tabular mt-4 grid grid-cols-3 gap-4 border-t border-border pt-4">
                <div>
                  <dt className="text-xs text-muted-foreground">Fix cost</dt>
                  <dd className="font-semibold text-foreground">
                    {formatUsd(action.estimated_cost)}
                  </dd>
                  <dd className="text-xs text-muted-foreground">{action.estimated_hours}h</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Saves</dt>
                  <dd className="font-semibold text-foreground">
                    {formatUsd(action.saves_per_month)}/mo
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Payback</dt>
                  <dd className="font-semibold text-foreground">
                    {paybackLabel(action.estimated_cost, action.saves_per_month)}
                  </dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ol>

      {roiAnalysis && (
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="mb-4 font-semibold text-foreground">Return on fixing it</h3>
          <dl className="tabular grid grid-cols-2 gap-4 md:grid-cols-4">
            {[
              {
                label: 'Annual savings',
                value: formatUsd(roiAnalysis.annual_maintenance_savings),
              },
              { label: 'Payback period', value: `${roiAnalysis.payback_months} months` },
              {
                label: '3-year ROI',
                value: `${roiAnalysis['3_year_roi_pct']}%`,
                negative: Number(roiAnalysis['3_year_roi_pct']) < 0,
              },
              {
                label: 'Suggested quarterly budget',
                value: formatUsd(roiAnalysis.recommended_budget),
              },
            ].map(({ label, value, negative }) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd
                  className={`mt-1 text-lg font-semibold ${
                    negative ? 'text-danger' : 'text-foreground'
                  }`}
                >
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-6 border-t border-border pt-4">
            <h4 className="mb-3 text-sm font-medium text-foreground">
              When does fixing it pay off?
            </h4>
            <RoiBreakEvenChart
              totalFixCost={roiAnalysis.total_fix_cost}
              annualSavings={roiAnalysis.annual_maintenance_savings}
              paybackMonths={roiAnalysis.payback_months}
              roi3yPct={roiAnalysis['3_year_roi_pct']}
            />
          </div>
          {roiAnalysis.recommendation && (
            <p className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
              {roiAnalysis.recommendation}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
