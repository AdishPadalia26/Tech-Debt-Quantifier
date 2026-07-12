export function normalizeRepoUrl(input: string): string {
  if (input.startsWith('http://') || input.startsWith('https://')) {
    return input;
  }
  return `https://${input}`;
}

export function repoSegmentsFromUrl(githubUrl: string): string[] {
  const normalized = normalizeRepoUrl(githubUrl).replace(/^https?:\/\//, '');
  return normalized.split('/').slice(1).filter(Boolean);
}

export function repoDetailPath(githubUrl: string): string {
  const segments = repoSegmentsFromUrl(githubUrl).map(encodeURIComponent);
  return `/repositories/${segments.join('/')}`;
}

export function repoLabel(githubUrl: string): string {
  const segments = repoSegmentsFromUrl(githubUrl);
  return segments.slice(-2).join('/');
}
