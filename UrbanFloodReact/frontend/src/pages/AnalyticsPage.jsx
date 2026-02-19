import React from 'react';
import { Activity } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, BarChart, Bar, Legend
} from 'recharts';

const PIE_COLORS = ['#22c55e', '#f97316', '#3b82f6', '#ef4444'];

export default function AnalyticsPage({ appState }) {
  const result = appState.evacuationResult;
  const stats = appState.simStats;

  if (!result || !stats) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <Activity size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 font-medium">Complete evacuation planning to see analytics</p>
        </div>
      </div>
    );
  }

  const eStats = result.stats;
  const times = [];
  // Build cumulative timeline from routes
  if (result.routes_geojson?.features) {
    const routeTimes = result.routes_geojson.features
      .map(f => f.properties.time_min)
      .filter(t => t > 0)
      .sort((a, b) => a - b);

    routeTimes.forEach((t, i) => {
      times.push({
        time: t,
        evacuated: i + 1,
        pct: Math.round(((i + 1) / routeTimes.length) * 100),
      });
    });
  }

  // Pie data
  const pieData = [
    { name: 'Safe', value: stats.safe_people },
    { name: 'In Flood Zone', value: stats.flooded_people },
    { name: 'Evacuated', value: eStats.evacuated },
    { name: 'Unreachable', value: eStats.unreachable },
  ];

  // Infrastructure bar data (approximation since we have stats)
  const infraData = [
    { name: 'Safe Centers', count: appState.safeCenters?.length || 0, status: 'Available' },
    { name: 'Evacuated', count: eStats.evacuated, status: 'Good' },
    { name: 'Unreachable', count: eStats.unreachable, status: 'Critical' },
  ];

  return (
    <div className="h-full overflow-auto p-8 space-y-8">
      <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
        <Activity size={24} className="text-blue-600" /> Analytics Dashboard
      </h2>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Success Rate" value={`${eStats.success_rate}%`} sub={`${eStats.evacuated}/${eStats.total_flooded}`} color="blue" />
        <MetricCard label="Avg Evacuation" value={`${eStats.avg_time} min`} color="green" />
        <MetricCard label="Max Evacuation" value={`${eStats.max_time} min`} color="orange" />
        <MetricCard label="Algorithm" value={result.algorithm} sub={`${eStats.execution_time}s exec`} color="purple" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Timeline */}
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-bold text-gray-700 mb-4">📈 Evacuation Timeline</h3>
          {times.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={times}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" label={{ value: 'Time (min)', position: 'bottom', offset: -5 }} tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" label={{ value: 'People', angle: -90, position: 'insideLeft' }} />
                <YAxis yAxisId="right" orientation="right" label={{ value: '%', angle: 90, position: 'insideRight' }} domain={[0, 100]} />
                <Tooltip />
                <Line yAxisId="left" type="monotone" dataKey="evacuated" stroke="#3b82f6" strokeWidth={2} dot={false} name="People Evacuated" />
                <Line yAxisId="right" type="monotone" dataKey="pct" stroke="#ef4444" strokeWidth={2} dot={false} name="Completion %" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-400 text-sm">No timeline data available</p>
          )}
        </div>

        {/* Pie */}
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-bold text-gray-700 mb-4">🎯 Population Distribution</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" outerRadius={90} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Infrastructure Bar */}
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-bold text-gray-700 mb-4">🏗️ Infrastructure & Response Status</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={infraData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="count" name="Count">
                {infraData.map((entry, i) => (
                  <Cell key={i} fill={entry.status === 'Critical' ? '#ef4444' : entry.status === 'Good' ? '#22c55e' : '#3b82f6'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Situation Report */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <h3 className="text-lg font-bold text-gray-800 mb-4">📋 Situation Report</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-gray-700">
          <div>
            <p className="font-semibold text-gray-500 mb-2">👥 Population Impact</p>
            <p>Total: <strong>{stats.total_people}</strong></p>
            <p>At Risk: <strong>{stats.flooded_people}</strong> ({stats.risk_pct}%)</p>
            <p>Evacuated: <strong>{eStats.evacuated}</strong></p>
            <p>Unreachable: <strong>{eStats.unreachable}</strong></p>
          </div>
          <div>
            <p className="font-semibold text-gray-500 mb-2">⏱️ Performance</p>
            <p>Algorithm: <strong>{result.algorithm}</strong></p>
            <p>Avg Time: <strong>{eStats.avg_time} min</strong></p>
            <p>Max Time: <strong>{eStats.max_time} min</strong></p>
            <p>Exec Time: <strong>{eStats.execution_time}s</strong></p>
          </div>
          <div>
            <p className="font-semibold text-gray-500 mb-2">🚦 Risk Assessment</p>
            <div className={`p-3 rounded-lg border text-sm font-medium ${
              stats.risk_level?.includes('HIGH') ? 'bg-red-50 border-red-300 text-red-700'
              : stats.risk_level?.includes('MEDIUM') ? 'bg-yellow-50 border-yellow-300 text-yellow-700'
              : 'bg-green-50 border-green-300 text-green-700'
            }`}>
              {stats.risk_level}
            </div>
            {stats.recommendations?.slice(0, 3).map((r, i) => (
              <p key={i} className="text-xs text-gray-500 mt-1">{r}</p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, sub, color }) {
  const colors = {
    blue: 'border-l-blue-500 bg-blue-50',
    green: 'border-l-green-500 bg-green-50',
    orange: 'border-l-orange-500 bg-orange-50',
    purple: 'border-l-purple-500 bg-purple-50',
  };

  return (
    <div className={`p-4 rounded-xl border-l-4 ${colors[color] || colors.blue}`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold text-gray-800 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}
