'use client';

import { useCallback, useEffect, useState } from 'react';

import { cn } from '@/lib/utils';

export type ViewMode = 'executive' | 'engineer';

const STORAGE_KEY = 'tdq:view-mode';

const OPTIONS: { value: ViewMode; label: string }[] = [
  { value: 'executive', label: 'Executive' },
  { value: 'engineer', label: 'Engineer' },
];

function isViewMode(value: unknown): value is ViewMode {
  return value === 'executive' || value === 'engineer';
}

/**
 * View mode persisted in `?view=` and localStorage (URL wins).
 * Defaults to `executive`; storage access is guarded for private windows.
 */
export function useViewMode(): [ViewMode, (mode: ViewMode) => void] {
  const [mode, setModeState] = useState<ViewMode>('executive');

  useEffect(() => {
    let next: ViewMode | null = null;
    try {
      const fromUrl = new URLSearchParams(window.location.search).get('view');
      if (isViewMode(fromUrl)) next = fromUrl;
    } catch {
      /* ignore */
    }
    if (!next) {
      try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (isViewMode(stored)) next = stored;
      } catch {
        /* storage unavailable */
      }
    }
    if (next) setModeState(next);
  }, []);

  const setMode = useCallback((value: ViewMode) => {
    setModeState(value);
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch {
      /* storage unavailable */
    }
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('view', value);
      window.history.replaceState(window.history.state, '', url);
    } catch {
      /* ignore */
    }
  }, []);

  return [mode, setMode];
}

/** Segmented Executive / Engineer control. */
export function ViewModeToggle({
  mode,
  onChange,
}: {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span id="view-mode-label" className="text-xs font-medium text-muted-foreground">
        View:
      </span>
      <div
        role="group"
        aria-labelledby="view-mode-label"
        className="flex overflow-hidden rounded-md border border-border"
      >
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={mode === opt.value}
            onClick={() => onChange(opt.value)}
            className={cn(
              'border-r border-border px-3 py-1.5 text-xs font-medium transition-colors last:border-r-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
              mode === opt.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-card text-muted-foreground hover:bg-muted',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
