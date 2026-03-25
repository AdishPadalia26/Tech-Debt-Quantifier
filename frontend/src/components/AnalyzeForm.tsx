'use client';
import { useState } from 'react';
import { startAnalysis } from '@/lib/api';

interface Props {
  onJobStarted: (jobId: string, githubUrl: string) => void;
}

export default function AnalyzeForm({ onJobStarted }: Props) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    
    // Basic GitHub URL validation
    if (!url.includes('github.com')) {
      setError('Please enter a valid GitHub repository URL');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      const response = await startAnalysis(url.trim());
      onJobStarted(response.job_id, url.trim());
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to start analysis');
    } finally {
      setLoading(false);
    }
  };

  const exampleRepos = [
    'https://github.com/pallets/flask',
    'https://github.com/django/django',
    'https://github.com/fastapi/fastapi',
  ];

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            GitHub Repository URL
          </label>
          <div className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-600 
                         rounded-lg text-white placeholder-gray-400 
                         focus:outline-none focus:border-purple-500 
                         focus:ring-1 focus:ring-purple-500"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 
                         disabled:bg-gray-600 disabled:cursor-not-allowed
                         text-white font-medium rounded-lg transition-colors"
            >
              {loading ? 'Starting...' : 'Analyze →'}
            </button>
          </div>
          {error && (
            <p className="mt-2 text-sm text-red-400">{error}</p>
          )}
        </div>
      </form>

      <div className="mt-4">
        <p className="text-xs text-gray-500 mb-2">Try an example:</p>
        <div className="flex flex-wrap gap-2">
          {exampleRepos.map((repo) => (
            <button
              key={repo}
              onClick={() => setUrl(repo)}
              className="text-xs px-3 py-1 bg-gray-800 hover:bg-gray-700 
                         text-gray-300 rounded-full border border-gray-600
                         transition-colors"
            >
              {repo.split('/').slice(-2).join('/')}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
