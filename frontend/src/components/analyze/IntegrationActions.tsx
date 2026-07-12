'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  CheckCircle2,
  Download,
  Loader2,
  MessageSquare,
  Ticket,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { repoDetailPath } from '@/lib/routes';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type JiraTicket = { key: string; url: string; summary: string };
type JiraFailed = { file: string; error: string };

type JiraResult = {
  ok?: boolean;
  epic_url?: string;
  epic_key?: string;
  total_created?: number;
  total_failed?: number;
  created?: JiraTicket[];
  failed?: JiraFailed[];
  error?: string;
};

type IntegrationsConfig = {
  slack: { configured: boolean; channel: string };
  jira: { configured: boolean; server: string; project: string };
};

interface IntegrationActionsProps {
  jobId: string;
  scanId?: string;
  currentGithubUrl: string;
  integrations: IntegrationsConfig | null;
  onReset: () => void;
}

export function IntegrationActions({
  jobId,
  scanId,
  currentGithubUrl,
  integrations,
  onReset,
}: IntegrationActionsProps) {
  const [downloading, setDownloading] = useState(false);
  const [slackSending, setSlackSending] = useState(false);
  const [slackSent, setSlackSent] = useState(false);
  const [jiraCreating, setJiraCreating] = useState(false);
  const [jiraResult, setJiraResult] = useState<JiraResult | null>(null);
  const [jiraError, setJiraError] = useState<string | null>(null);

  const handleDownloadPDF = async () => {
    if (!jobId) return;
    setDownloading(true);
    try {
      const response = await fetch(`${API_URL}/report/${jobId}/pdf`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('PDF generation failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tech-debt-report-${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('PDF download failed:', err);
    } finally {
      setDownloading(false);
    }
  };

  const handleSendSlack = async () => {
    if (!jobId) return;
    setSlackSending(true);
    try {
      const r = await fetch(`${API_URL}/report/${jobId}/slack`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!r.ok) throw new Error(await r.text());
      setSlackSent(true);
      setTimeout(() => setSlackSent(false), 4000);
    } catch (err) {
      console.error('Slack failed:', err);
    } finally {
      setSlackSending(false);
    }
  };

  const handleCreateJira = async () => {
    if (!jobId) return;
    setJiraCreating(true);
    setJiraError(null);
    setJiraResult(null);
    try {
      const r = await fetch(`${API_URL}/report/${jobId}/jira`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = (await r.json()) as JiraResult;
      if (!r.ok) {
        setJiraError((data as { detail?: string; error?: string }).detail ?? data.error ?? 'Jira error');
        return;
      }
      setJiraResult(data);
    } catch (err) {
      setJiraError('Network error - could not reach backend.');
      console.error('Jira failed:', err);
    } finally {
      setJiraCreating(false);
    }
  };

  return (
    <TooltipProvider>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onReset}>
            New Analysis
          </Button>
          {scanId ? (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/scans/${scanId}`}>
                Open Scan Detail
                <ArrowRight className="ml-2 size-4" />
              </Link>
            </Button>
          ) : null}
          {currentGithubUrl ? (
            <Button variant="outline" size="sm" asChild>
              <Link href={repoDetailPath(currentGithubUrl)}>
                Open Repository Detail
                <ArrowRight className="ml-2 size-4" />
              </Link>
            </Button>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { void handleDownloadPDF().catch(console.error); }}
                disabled={downloading}
              >
                {downloading ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Download className="size-4" />
                )}
                <span className="ml-2">{downloading ? 'Generating...' : 'PDF Report'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download full PDF analysis</TooltipContent>
          </Tooltip>

          {integrations?.slack?.configured ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { void handleSendSlack().catch(console.error); }}
                  disabled={slackSending || slackSent}
                  className={slackSent ? 'border-emerald-500/30 text-emerald-400' : ''}
                >
                  {slackSent ? (
                    <>
                      <CheckCircle2 className="mr-2 size-4" />
                      Sent
                    </>
                  ) : slackSending ? (
                    <>
                      <Loader2 className="mr-2 size-4 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <MessageSquare className="mr-2 size-4" />
                      Slack
                    </>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Post to {integrations.slack.channel}</TooltipContent>
            </Tooltip>
          ) : null}

          {integrations?.jira?.configured ? (
            <div className="flex flex-col items-end gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { void handleCreateJira().catch(console.error); }}
                    disabled={jiraCreating || !!jiraResult?.total_created}
                    className={
                      jiraResult?.total_created
                        ? 'border-emerald-500/30 text-emerald-400'
                        : ''
                    }
                  >
                    {jiraResult?.total_created ? (
                      <>
                        <CheckCircle2 className="mr-2 size-4" />
                        {jiraResult.total_created} tickets
                      </>
                    ) : jiraCreating ? (
                      <>
                        <Loader2 className="mr-2 size-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Ticket className="mr-2 size-4" />
                        Jira
                      </>
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Create tickets in {integrations.jira.project} project
                </TooltipContent>
              </Tooltip>

              {jiraError ? (
                <p className="max-w-xs text-right text-xs text-destructive">{jiraError}</p>
              ) : null}
              {jiraResult?.total_failed && jiraResult.total_failed > 0 ? (
                <p className="text-xs text-amber-400">
                  {jiraResult.total_failed} ticket
                  {jiraResult.total_failed === 1 ? '' : 's'} failed to create
                </p>
              ) : null}
              {jiraResult?.created && jiraResult.created.length > 0 ? (
                <div className="mt-1 space-y-0.5 text-right text-xs text-muted-foreground">
                  {jiraResult.created.slice(0, 5).map((ticket) => (
                    <div key={ticket.key}>
                      <Link
                        href={ticket.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline underline-offset-2 hover:text-primary/80"
                      >
                        {ticket.key}
                      </Link>{' '}
                      <span className="text-muted-foreground/70">{ticket.summary}</span>
                    </div>
                  ))}
                  {jiraResult.created.length > 5 ? (
                    <span className="text-muted-foreground/70">
                      +{jiraResult.created.length - 5} more
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {jiraResult?.epic_url ? (
            <Link
              href={jiraResult.epic_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline"
            >
              View Epic {jiraResult.epic_key ?? ''}
            </Link>
          ) : null}
        </div>
      </div>
    </TooltipProvider>
  );
}
