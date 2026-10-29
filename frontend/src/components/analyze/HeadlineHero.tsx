import { formatEffort, formatUsdCompact } from '@/lib/format';
import type { CostRange } from '@/types';

interface Props {
  /** Repository display name, e.g. `fastapi`. */
  repoName?: string | null;
  totalCost?: number;
  range?: CostRange;
  hours?: number;
  /** Share (0-100) of cost removed by fixing the top `topCount` items. */
  topShare?: number;
  topCount?: number;
}

/** One-sentence pitch headline. Parts degrade away when data is missing. */
export function HeadlineHero({
  repoName,
  totalCost = 0,
  range,
  hours,
  topShare,
  topCount = 10,
}: Props) {
  const hasRange = range && range.p90 > 0 && range.p90 > range.p10;
  const hasShare = typeof topShare === 'number' && topShare > 0;

  return (
    <section
      aria-label="Headline"
      className="rounded-xl border border-border bg-card p-5 sm:p-6"
    >
      <p className="max-w-4xl text-lg leading-relaxed text-foreground/90 sm:text-xl">
        <strong className="font-semibold text-foreground">
          {repoName || 'This repository'} carries ≈ {formatUsdCompact(totalCost)} of tech debt
        </strong>
        {hasRange && (
          <>
            {' '}
            (likely {formatUsdCompact(range.p10)} – {formatUsdCompact(range.p90)})
          </>
        )}
        {hours ? <>, {formatEffort(hours)} of work</> : null}.
        {hasShare && (
          <>
            {' '}
            Fixing the top {topCount} items removes {Math.round(topShare)}% of it.
          </>
        )}
      </p>
    </section>
  );
}
