/** Single source of truth for debt category labels and chart colors. */
import { humanize } from '@/lib/format';

export interface CategoryMeta {
  label: string;
  color: string;
}

/** Keys mirror backend `DEFAULT_CATEGORIES` plus categories emitted by agents. */
export const CATEGORY_META: Record<string, CategoryMeta> = {
  code_quality: { label: 'Code quality', color: 'var(--chart-1)' },
  architecture: { label: 'Architecture', color: 'var(--chart-2)' },
  test_debt: { label: 'Test coverage', color: 'var(--chart-3)' },
  dependency: { label: 'Dependencies', color: 'var(--chart-4)' },
  documentation: { label: 'Documentation', color: 'var(--chart-5)' },
  performance: { label: 'Performance', color: 'var(--chart-6)' },
  reliability: { label: 'Reliability', color: 'var(--chart-7)' },
  security: { label: 'Safety & security', color: 'var(--chart-8)' },
};

const FALLBACK_COLORS = ['var(--chart-7)', 'var(--chart-6)', 'var(--chart-5)', 'var(--chart-4)'];

/** Display label for a category key; unknown keys are humanized. */
export function categoryLabel(key?: string | null): string {
  if (!key) return 'Unknown';
  return CATEGORY_META[key]?.label ?? (humanize(key) || 'Unknown');
}

/** Stable color per category (unknown keys hash to a fixed fallback). */
export function categoryColor(key?: string | null): string {
  const known = key ? CATEGORY_META[key] : undefined;
  if (known) return known.color;
  const s = key ?? '';
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return FALLBACK_COLORS[h % FALLBACK_COLORS.length];
}
