import { humanize } from '@/lib/format';
import { RepoProfile as RepoProfileType } from '@/types';

interface Props {
  profile: RepoProfileType;
}

export default function RepoProfile({ profile }: Props) {
  const tech_stack = profile.tech_stack || {
    primary_language: 'Unknown', frameworks: [], ai_ml_libraries: [],
    databases: [], has_tests: false, has_ci_cd: false,
  };
  const team = profile.team || {
    estimated_team_size: 0, bus_factor: 0, repo_age_days: 0,
    active_contributors: 0,
  };
  const multipliers = profile.multipliers || {
    combined_multiplier: 1, bus_factor_multiplier: 1,
    repo_age_multiplier: 1, ai_code_multiplier: 1,
  };
  const ai_detection = profile.ai_detection || { total_suspected: 0, suspected_files: [] };

  return (
    <div className="bg-card rounded-xl p-6 border border-border">
      <h3 className="text-lg font-semibold text-foreground mb-4">
        Repository profile
      </h3>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Tech Stack */}
        <div>
          <p className="text-sm text-muted-foreground mb-2">Tech stack</p>
          <div className="space-y-1">
            <p className="text-sm text-foreground">
              {tech_stack.primary_language}
            </p>
            {tech_stack.frameworks.map(f => (
              <span key={f} className="inline-block text-xs bg-accent 
                text-primary px-2 py-0.5 rounded mr-1 mb-1">{f}</span>
            ))}
            {tech_stack.ai_ml_libraries.length > 0 && (
              <p className="text-xs text-warning mt-1">
                AI/ML: {tech_stack.ai_ml_libraries.join(', ')}
              </p>
            )}
            {tech_stack.databases.length > 0 && (
              <p className="text-xs text-info">
                Databases: {tech_stack.databases.join(', ')}
              </p>
            )}
          </div>
          <div className="flex gap-2 mt-3">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              tech_stack.has_tests 
                ? 'bg-success/10 text-success' 
                : 'bg-danger/10 text-danger'}`}>
              {tech_stack.has_tests ? 'Tests' : 'No tests'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              tech_stack.has_ci_cd 
                ? 'bg-success/10 text-success' 
                : 'bg-muted text-muted-foreground'}`}>
              {tech_stack.has_ci_cd ? 'CI/CD' : 'No CI/CD'}
            </span>
          </div>
        </div>

        {/* Team Info */}
        <div>
          <p className="text-sm text-muted-foreground mb-2">Team</p>
          <div className="space-y-2">
            {[
              { label: 'Team Size', 
                value: `~${team.estimated_team_size} engineers` },
              { label: 'Bus Factor', 
                value: team.bus_factor,
                warn: team.bus_factor <= 2 },
              { label: 'Repo Age', 
                value: `${Math.floor(team.repo_age_days / 365)} years` },
              { label: 'Active Contributors', 
                value: team.active_contributors },
            ].map(({ label, value, warn }) => (
              <div key={label} className="flex justify-between">
                <span className="text-xs text-muted-foreground">{label}</span>
                <span className={`text-xs font-medium ${
                  warn ? 'text-danger' : 'text-foreground'}`}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Multipliers */}
        <div>
          <p className="text-sm text-muted-foreground mb-2">
            Risk multipliers
          </p>
          <div className="space-y-2">
            {Object.entries(multipliers)
              .filter(([k]) => k !== 'combined_multiplier')
              .map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-xs text-muted-foreground">
                    {humanize(key)}
                  </span>
                  <span className={`text-xs font-medium ${
                    (typeof value === 'number' && value > 1.2) 
                      ? 'text-danger' 
                      : 'text-success'}`}>
                    {typeof value === 'number' ? value.toFixed(1) : '1.0'}x
                  </span>
                </div>
              ))}
            <div className="flex justify-between border-t border-border-strong pt-2 mt-2">
              <span className="text-xs text-foreground font-medium">
                Combined
              </span>
              <span className="text-xs font-bold text-warning">
                {(multipliers.combined_multiplier ?? 1).toFixed(2)}x
              </span>
            </div>
          </div>
          {ai_detection.total_suspected > 0 && (
            <p className="text-xs text-warning mt-3">
              {ai_detection.total_suspected} files look AI-generated
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
