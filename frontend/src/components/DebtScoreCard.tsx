interface Props {
  score?: number;
  totalCost?: number;
  hours?: number;
  sprints?: number;
  sanityCheck?: { is_reasonable: boolean; assessment: string };
}

export default function DebtScoreCard({ 
  score = 0, totalCost = 0, hours = 0, sprints = 0, 
  sanityCheck = { is_reasonable: false, assessment: 'N/A' } 
}: Props) {
  const getScoreColor = (s: number) => {
    if (s <= 3) return 'text-green-400';
    if (s <= 6) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getScoreLabel = (s: number) => {
    if (s <= 3) return 'Low Debt';
    if (s <= 6) return 'Moderate Debt';
    return 'High Debt';
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Debt Score */}
      <div className="md:col-span-1 bg-gray-800 rounded-xl p-6 
                      border border-gray-700 flex flex-col items-center">
        <p className="text-sm text-gray-400 mb-2">Debt Score</p>
        <p className={`text-6xl font-bold ${getScoreColor(score)}`}>
          {score.toFixed(1)}
        </p>
        <p className="text-sm text-gray-500 mt-1">/ 10</p>
        <span className={`mt-2 text-xs font-medium px-2 py-1 rounded-full 
          ${score <= 3 ? 'bg-green-900/50 text-green-400' : 
            score <= 6 ? 'bg-yellow-900/50 text-yellow-400' : 
            'bg-red-900/50 text-red-400'}`}>
          {getScoreLabel(score)}
        </span>
      </div>

      {/* Total Cost */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <p className="text-sm text-gray-400 mb-1">Total Debt Cost</p>
        <p className="text-3xl font-bold text-white">
          ${totalCost.toLocaleString('en-US', {maximumFractionDigits: 0})}
        </p>
        <p className="text-xs text-gray-500 mt-2">{sanityCheck.assessment}</p>
      </div>

      {/* Remediation Hours */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <p className="text-sm text-gray-400 mb-1">Remediation Time</p>
        <p className="text-3xl font-bold text-white">
          {hours.toFixed(0)} <span className="text-lg text-gray-400">hrs</span>
        </p>
        <p className="text-xs text-gray-500 mt-2">
          ~{sprints.toFixed(1)} engineering sprints
        </p>
      </div>

      {/* Sanity Check */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <p className="text-sm text-gray-400 mb-1">vs Industry Avg</p>
        <p className="text-3xl font-bold text-white">
          {sanityCheck.is_reasonable ? '✅' : '⚠️'}
        </p>
        <p className="text-xs text-gray-500 mt-2">
          CISQ benchmark: $1,083/fn
        </p>
      </div>
    </div>
  );
}
