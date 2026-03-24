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
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h3 className="text-lg font-semibold text-white mb-4">
        🔍 Repository Profile
      </h3>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Tech Stack */}
        <div>
          <p className="text-xs text-gray-400 uppercase mb-2">Tech Stack</p>
          <div className="space-y-1">
            <p className="text-sm text-white">
              🗣️ {tech_stack.primary_language}
            </p>
            {tech_stack.frameworks.map(f => (
              <span key={f} className="inline-block text-xs bg-purple-900/50 
                text-purple-300 px-2 py-0.5 rounded mr-1 mb-1">{f}</span>
            ))}
            {tech_stack.ai_ml_libraries.length > 0 && (
              <p className="text-xs text-yellow-400 mt-1">
                🤖 AI: {tech_stack.ai_ml_libraries.join(', ')}
              </p>
            )}
            {tech_stack.databases.length > 0 && (
              <p className="text-xs text-blue-400">
                🗄️ DB: {tech_stack.databases.join(', ')}
              </p>
            )}
          </div>
          <div className="flex gap-2 mt-3">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              tech_stack.has_tests 
                ? 'bg-green-900/50 text-green-400' 
                : 'bg-red-900/50 text-red-400'}`}>
              {tech_stack.has_tests ? '✅ Tests' : '❌ No Tests'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              tech_stack.has_ci_cd 
                ? 'bg-green-900/50 text-green-400' 
                : 'bg-gray-700 text-gray-400'}`}>
              {tech_stack.has_ci_cd ? '✅ CI/CD' : '⚠️ No CI/CD'}
            </span>
          </div>
        </div>

        {/* Team Info */}
        <div>
          <p className="text-xs text-gray-400 uppercase mb-2">Team</p>
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
                <span className="text-xs text-gray-400">{label}</span>
                <span className={`text-xs font-medium ${
                  warn ? 'text-red-400' : 'text-white'}`}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Multipliers */}
        <div>
          <p className="text-xs text-gray-400 uppercase mb-2">
            Risk Multipliers
          </p>
          <div className="space-y-2">
            {Object.entries(multipliers)
              .filter(([k]) => k !== 'combined_multiplier')
              .map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-xs text-gray-400">
                    {key.replace(/_/g, ' ')}
                  </span>
                  <span className={`text-xs font-medium ${
                    (typeof value === 'number' && value > 1.2) 
                      ? 'text-red-400' 
                      : 'text-green-400'}`}>
                    {typeof value === 'number' ? value.toFixed(1) : '1.0'}x
                  </span>
                </div>
              ))}
            <div className="flex justify-between border-t border-gray-600 pt-2 mt-2">
              <span className="text-xs text-gray-300 font-medium">
                Combined
              </span>
              <span className="text-xs font-bold text-yellow-400">
                {(multipliers.combined_multiplier ?? 1).toFixed(2)}x
              </span>
            </div>
          </div>
          {ai_detection.total_suspected > 0 && (
            <p className="text-xs text-yellow-400 mt-3">
              ⚠️ {ai_detection.total_suspected} AI-generated files suspected
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
