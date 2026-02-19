import React, { useState } from 'react';
import api from '../api';
import { BarChart3, Loader, Trophy } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ScatterChart, Scatter, Cell, Legend } from 'recharts';

const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444'];

export default function AlgorithmComparisonPage({ appState, updateState }) {
  const [walkingSpeed, setWalkingSpeed] = useState(5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [best, setBest] = useState('');

  const runComparison = async () => {
    setLoading(true);
    try {
      const r = await api.post('/evacuation/compare', { walking_speed: walkingSpeed });
      setResults(r.data.results);
      setBest(r.data.best_algorithm);
      updateState({ comparisonResults: r.data.results });
    } catch (e) {
      alert(e.response?.data?.detail || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  const ready = appState.simulationRun && appState.safeCentersPrepared;

  return (
    <div className="h-full overflow-auto p-8 space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <BarChart3 size={24} className="text-blue-600" /> Algorithm Comparison
        </h2>
      </div>

      {!ready ? (
        <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-lg text-yellow-700">
          ⚠️ Complete flood simulation and prepare safe centers first
        </div>
      ) : (
        <>
          <div className="flex items-end gap-4 bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
            <div className="flex-1">
              <label className="flex justify-between text-sm font-medium text-gray-600 mb-1">
                Walking Speed <span className="text-blue-600 font-bold">{walkingSpeed} km/h</span>
              </label>
              <input type="range" min="3" max="15" value={walkingSpeed}
                onChange={e => setWalkingSpeed(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg accent-blue-600" />
            </div>
            <button onClick={runComparison} disabled={loading}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg flex items-center gap-2 disabled:opacity-50 whitespace-nowrap">
              {loading ? <Loader className="animate-spin" size={16} /> : '🚀'}
              {loading ? 'Running all 4...' : 'Run Comparison'}
            </button>
          </div>

          {results && (
            <>
              {/* Best badge */}
              <div className="flex items-center gap-3 bg-green-50 border border-green-200 p-4 rounded-xl">
                <Trophy className="text-yellow-500" size={24} />
                <div>
                  <p className="text-green-800 font-bold">Best Performing Algorithm</p>
                  <p className="text-green-600 text-lg font-bold">{best}</p>
                </div>
              </div>

              {/* Table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-4 py-3 font-semibold text-gray-600">Algorithm</th>
                      <th className="text-right px-4 py-3 font-semibold text-gray-600">Success %</th>
                      <th className="text-right px-4 py-3 font-semibold text-gray-600">Avg Time (min)</th>
                      <th className="text-right px-4 py-3 font-semibold text-gray-600">Exec Time (s)</th>
                      <th className="text-right px-4 py-3 font-semibold text-gray-600">Evacuated</th>
                      <th className="text-right px-4 py-3 font-semibold text-gray-600">Unreachable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, i) => (
                      <tr key={i} className={`border-t ${r.algorithm === best ? 'bg-green-50' : ''}`}>
                        <td className="px-4 py-3 font-medium">
                          {r.algorithm === best && '🏆 '}{r.algorithm}
                          {r.error && <span className="text-red-500 text-xs ml-1">(error)</span>}
                        </td>
                        <td className="text-right px-4 py-3">{r.success_rate}%</td>
                        <td className="text-right px-4 py-3">{r.avg_time}</td>
                        <td className="text-right px-4 py-3">{r.execution_time}</td>
                        <td className="text-right px-4 py-3">{r.evacuated}</td>
                        <td className="text-right px-4 py-3">{r.unreachable}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Success Rate */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                  <h3 className="text-sm font-bold text-gray-700 mb-4">Evacuation Success Rate (%)</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={results}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="algorithm" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="success_rate" name="Success %">
                        {results.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Execution Time */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                  <h3 className="text-sm font-bold text-gray-700 mb-4">Execution Time (seconds)</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={results}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="algorithm" tick={{ fontSize: 11 }} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="execution_time" name="Time (s)">
                        {results.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Scatter: Success vs Exec Time */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm lg:col-span-2">
                  <h3 className="text-sm font-bold text-gray-700 mb-4">Performance: Success Rate vs Execution Time</h3>
                  <ResponsiveContainer width="100%" height={280}>
                    <ScatterChart margin={{ bottom: 20, left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" dataKey="execution_time" name="Exec Time (s)" />
                      <YAxis type="number" dataKey="success_rate" name="Success %" domain={[0, 100]} />
                      <Tooltip cursor={{ strokeDasharray: '3 3' }}
                        formatter={(val, name) => [typeof val === 'number' ? val.toFixed(2) : val, name]} />
                      <Legend />
                      <Scatter name="Algorithms" data={results} fill="#3b82f6">
                        {results.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                  <div className="flex justify-center gap-4 mt-2">
                    {results.map((r, i) => (
                      <span key={i} className="flex items-center gap-1 text-xs text-gray-600">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                        {r.algorithm}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
