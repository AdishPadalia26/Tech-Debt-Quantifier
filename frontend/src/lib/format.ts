/** Shared display formatting for report values. */

const ACRONYMS = new Set(['ci', 'cd', 'api', 'sql', 'llm', 'roi', 'cwe', 'cve', 'ai', 'ml']);

/** `duplicate_logic` -> `Duplicate logic`, `test_debt` -> `Test debt`. */
export function humanize(value?: string | null): string {
  if (!value) return '';
  const words = value.replace(/[_-]+/g, ' ').trim().split(/\s+/);
  return words
    .map((w, i) => {
      const lower = w.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(' ');
}

export function formatUsd(value?: number | null): string {
  return `$${Math.round(value ?? 0).toLocaleString('en-US')}`;
}

export function formatHours(value?: number | null): string {
  const v = value ?? 0;
  return `${v >= 100 ? Math.round(v).toLocaleString('en-US') : v.toFixed(1)}h`;
}

/** `65400` -> `$65K`, `1250000` -> `$1.3M`, `850` -> `$850`. */
export function formatUsdCompact(value?: number | null): string {
  const raw = value ?? 0;
  const v = Math.abs(raw);
  const sign = raw < 0 ? '-' : '';
  if (v >= 1_000_000) {
    const m = v / 1_000_000;
    return `${sign}$${m >= 10 ? Math.round(m) : parseFloat(m.toFixed(1))}M`;
  }
  if (v >= 1_000) {
    const k = v / 1_000;
    return `${sign}$${k >= 10 ? Math.round(k) : parseFloat(k.toFixed(1))}K`;
  }
  return `${sign}$${Math.round(v)}`;
}

const HOURS_PER_ENGINEER_MONTH = 160;

/** `640` -> `≈ 4 engineer-months` (160 h per engineer-month). */
export function formatEffort(hours?: number | null): string {
  const months = (hours ?? 0) / HOURS_PER_ENGINEER_MONTH;
  const rounded = months >= 10 ? Math.round(months) : Math.round(months * 10) / 10;
  if (rounded < 0.1) return '< 0.1 engineer-months';
  return `≈ ${rounded} engineer-${rounded === 1 ? 'month' : 'months'}`;
}

export type Severity = 'critical' | 'high' | 'medium' | 'low';

/** Tinted chip classes; severity color is reserved for risk meaning. */
export function severityChip(severity?: string | null): string {
  switch (severity) {
    case 'critical':
      return 'bg-severity-critical/15 text-severity-critical';
    case 'high':
      return 'bg-severity-high/15 text-severity-high';
    case 'medium':
      return 'bg-severity-medium/15 text-severity-medium';
    default:
      return 'bg-muted text-muted-foreground';
  }
}
