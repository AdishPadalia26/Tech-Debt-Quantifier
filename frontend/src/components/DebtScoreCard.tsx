interface Props {
  score?: number;
  totalCost?: number;
  hours?: number;
  sprints?: number;
  /** Only rendered when the backend actually supplied a benchmark comparison. */
  sanityCheck?: { is_reasonable: boolean; assessment: string };
}

function scoreBand(s: number) {
  if (s <= 3) return { label: 'Low debt', text: 'text-success', chip: 'bg-success/15 text-success' };
  if (s <= 6) return { label: 'Moderate debt', text: 'text-warning', chip: 'bg-warning/15 text-warning' };
  return { label: 'High debt', text: 'text-danger', chip: 'bg-danger/15 text-danger' };
}

export default function DebtScoreCard({
  score = 0,
  totalCost = 0,
  hours = 0,
  sprints = 0,
  sanityCheck,
}: Props) {
  const band = scoreBand(score);

  return (
    <section
      aria-label="Debt overview"
      className="grid grid-cols-1 overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-2 lg:grid-cols-3"
    >
      {/* Total cost leads: it's the number this product exists to produce. */}
      <div className="border-b border-border p-6 sm:col-span-2 lg:col-span-1 lg:border-b-0 lg:border-r">
        <p className="text-sm text-muted-foreground">Estimated debt cost</p>
        <p className="tabular mt-1 text-4xl font-semibold tracking-tight text-foreground">
          ${totalCost.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
        {sanityCheck && (
          <p className="mt-2 text-xs text-muted-foreground">{sanityCheck.assessment}</p>
        )}
      </div>

      <div className="border-b border-border p-6 sm:border-b-0 sm:border-r">
        <p className="text-sm text-muted-foreground">Debt score</p>
        <p className="mt-1 flex items-baseline gap-1">
          <span className={`tabular text-4xl font-semibold tracking-tight ${band.text}`}>
            {score.toFixed(1)}
          </span>
          <span className="text-sm text-muted-foreground">/ 10</span>
        </p>
        <span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${band.chip}`}>
          {band.label}
        </span>
      </div>

      <div className="p-6">
        <p className="text-sm text-muted-foreground">Remediation effort</p>
        <p className="mt-1 flex items-baseline gap-1">
          <span className="tabular text-4xl font-semibold tracking-tight text-foreground">
            {Math.round(hours).toLocaleString()}
          </span>
          <span className="text-sm text-muted-foreground">hours</span>
        </p>
        <p className="tabular mt-2 text-xs text-muted-foreground">
          About {sprints.toFixed(1)} engineering sprints
        </p>
      </div>
    </section>
  );
}
