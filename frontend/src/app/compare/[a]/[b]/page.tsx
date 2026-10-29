'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { getScanComparison, getScanSummary } from '@/lib/api';
import { ScanComparisonResponse, ScanSummaryResponse } from '@/types';

interface Props {
  params: { a: string; b: string };
}

function ScanColumn({
  label,
  scan,
}: {
  label: string;
  scan: ScanSummaryResponse | null;
}) {
  return (
    <div className="flex-1 rounded-xl border border-border bg-surface-raised p-5">
      <p className="mb-4 text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      {scan ? (
        <div className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground">Scan ID</p>
            <p className="font-mono text-sm text-foreground truncate">{scan.scan_id}</p>
          </div>
          {scan.created_at && (
            <div>
              <p className="text-xs text-muted-foreground">Date</p>
              <p className="text-sm text-foreground">
                {new Date(scan.created_at).toLocaleString()}
              </p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-card p-3 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Debt Score</p>
              <p className="font-mono text-2xl font-bold text-foreground">
                {scan.debt_score.toFixed(1)}
              </p>
            </div>
            <div className="rounded-lg bg-card p-3 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Total Cost</p>
              <p className="font-mono text-2xl font-bold text-foreground">
                ${Math.round(scan.total_cost_usd).toLocaleString()}
              </p>
            </div>
            <div className="rounded-lg bg-card p-3 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Hours</p>
              <p className="font-mono text-2xl font-bold text-foreground">
                {scan.total_hours.toFixed(1)}
              </p>
            </div>
            <div className="rounded-lg bg-card p-3 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Sprints</p>
              <p className="font-mono text-2xl font-bold text-foreground">
                {scan.total_sprints.toFixed(1)}
              </p>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Cost by Category</p>
            <div className="space-y-2">
              {Object.entries(scan.cost_by_category)
                .filter(([, v]) => v.cost_usd > 0)
                .sort(([, a], [, b]) => b.cost_usd - a.cost_usd)
                .slice(0, 5)
                .map(([key, val]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="capitalize text-foreground">
                      {key.replace(/_/g, ' ')}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      ${Math.round(val.cost_usd).toLocaleString()}
                    </span>
                  </div>
                ))}
            </div>
          </div>
          <Link
            href={`/scans/${scan.scan_id}`}
            className="block text-center text-sm text-primary hover:text-accent-foreground mt-2"
          >
            Open full scan →
          </Link>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">Loading…</p>
      )}
    </div>
  );
}

export default function ComparePage({ params }: Props) {
  const [baseScan, setBaseScan] = useState<ScanSummaryResponse | null>(null);
  const [targetScan, setTargetScan] = useState<ScanSummaryResponse | null>(null);
  const [comparison, setComparison] = useState<ScanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [base, target, comp] = await Promise.all([
          getScanSummary(params.a),
          getScanSummary(params.b),
          getScanComparison(params.a, params.b),
        ]);
        setBaseScan(base);
        setTargetScan(target);
        setComparison(comp);
      } catch (err) {
        console.error(err);
        setError('Failed to load comparison data. Check that both scan IDs are valid.');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [params.a, params.b]);

  if (loading) {
    return (
      <div className="w-full min-w-0">
        <div className="max-w-6xl mx-auto text-muted-foreground">Loading comparison…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-w-0">
        <div className="max-w-6xl mx-auto space-y-4">
          <p className="text-danger">{error}</p>
          <Link href="/" className="text-primary hover:text-accent-foreground">
            Back to Scanner
          </Link>
        </div>
      </div>
    );
  }

  const summary = comparison?.summary;

  return (
    <div className="w-full min-w-0">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-muted-foreground text-sm uppercase tracking-wider mb-1">
              Scan Comparison
            </p>
            <h1 className="text-2xl font-bold text-foreground">
              Baseline vs Target
            </h1>
            <p className="text-muted-foreground text-sm mt-1 font-mono">
              {params.a.slice(0, 12)}… → {params.b.slice(0, 12)}…
            </p>
          </div>
          <Link href="/" className="text-sm text-primary hover:text-accent-foreground">
            Back to Scanner
          </Link>
        </div>

        {/* Delta summary bar */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Cost delta', value: summary.cost_delta_usd, prefix: '$', fmt: (v: number) => Math.round(v) },
              { label: 'Score delta', value: summary.debt_score_delta, prefix: '', fmt: (v: number) => v.toFixed(1) },
              { label: 'Findings delta', value: summary.finding_count_delta, prefix: '', fmt: (v: number) => v },
              { label: 'Hours delta', value: summary.hours_delta, prefix: '', fmt: (v: number) => v.toFixed(1) },
            ].map(({ label, value, prefix, fmt }) => {
              const color =
                value > 0 ? 'text-danger' : value < 0 ? 'text-success' : 'text-muted-foreground';
              const sign = value > 0 ? '+' : '';
              return (
                <div
                  key={label}
                  className="rounded-xl border border-border bg-surface-raised p-4"
                >
                  <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">{label}</p>
                  <p className={`font-mono text-2xl font-bold ${color}`}>
                    {sign}{prefix}{fmt(value).toLocaleString()}
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {/* Side-by-side scan columns */}
        <div className="flex flex-col md:flex-row gap-4">
          <ScanColumn label="Baseline (base)" scan={baseScan} />
          <div className="flex items-center justify-center md:flex-col gap-2 py-4 text-muted-foreground">
            <div className="w-px h-full bg-muted hidden md:block" />
            <span className="text-xs font-mono bg-surface-raised px-2 py-1 rounded border border-border">
              vs
            </span>
            <div className="w-px h-full bg-muted hidden md:block" />
          </div>
          <ScanColumn label="Target (newer)" scan={targetScan} />
        </div>

        {/* Findings breakdown */}
        {comparison && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Added */}
            <div className="rounded-xl border border-border bg-surface-raised p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-foreground">New Findings</h3>
                <span className="rounded-full bg-danger/15 px-2 py-0.5 text-xs font-semibold text-danger">
                  +{comparison.added_findings.length}
                </span>
              </div>
              {comparison.added_findings.length === 0 ? (
                <p className="text-sm text-muted-foreground">No new findings — great!</p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {comparison.added_findings.slice(0, 12).map((f) => (
                    <div
                      key={f.id}
                      className="rounded-lg bg-card p-3 border border-border"
                    >
                      <p className="text-xs text-danger font-medium capitalize">
                        {f.severity} · {f.category.replace(/_/g, ' ')}
                      </p>
                      <p className="text-xs text-foreground mt-1 font-mono truncate">
                        {f.file_path}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        ${Math.round(f.cost_usd).toLocaleString()}
                      </p>
                    </div>
                  ))}
                  {comparison.added_findings.length > 12 && (
                    <p className="text-xs text-muted-foreground text-center pt-1">
                      +{comparison.added_findings.length - 12} more
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Resolved */}
            <div className="rounded-xl border border-border bg-surface-raised p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-foreground">Resolved</h3>
                <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs font-semibold text-success">
                  -{comparison.removed_findings.length}
                </span>
              </div>
              {comparison.removed_findings.length === 0 ? (
                <p className="text-sm text-muted-foreground">No findings resolved yet.</p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {comparison.removed_findings.slice(0, 12).map((f) => (
                    <div
                      key={f.id}
                      className="rounded-lg bg-card p-3 border border-border"
                    >
                      <p className="text-xs text-success font-medium capitalize">
                        {f.severity} · {f.category.replace(/_/g, ' ')}
                      </p>
                      <p className="text-xs text-foreground mt-1 font-mono truncate">
                        {f.file_path}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        saved ${Math.round(f.cost_usd).toLocaleString()}
                      </p>
                    </div>
                  ))}
                  {comparison.removed_findings.length > 12 && (
                    <p className="text-xs text-muted-foreground text-center pt-1">
                      +{comparison.removed_findings.length - 12} more
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Severity changes */}
            <div className="rounded-xl border border-border bg-surface-raised p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-foreground">Severity Changes</h3>
                <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning">
                  {comparison.severity_changed.length}
                </span>
              </div>
              {comparison.severity_changed.length === 0 ? (
                <p className="text-sm text-muted-foreground">No severity changes.</p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {comparison.severity_changed.slice(0, 12).map((sc) => (
                    <div
                      key={sc.id}
                      className="rounded-lg bg-card p-3 border border-border"
                    >
                      <p className="text-xs text-warning font-medium font-mono">
                        {sc.from_severity} → {sc.to_severity}
                      </p>
                      {sc.file_path && (
                        <p className="text-xs text-foreground mt-1 font-mono truncate">
                          {sc.file_path}
                        </p>
                      )}
                    </div>
                  ))}
                  {comparison.severity_changed.length > 12 && (
                    <p className="text-xs text-muted-foreground text-center pt-1">
                      +{comparison.severity_changed.length - 12} more
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
