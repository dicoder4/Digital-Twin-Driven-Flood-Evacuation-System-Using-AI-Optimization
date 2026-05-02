import React, { useState, useEffect, useMemo } from 'react';
import {
  X, BarChart2, Activity, Zap, Shield,
  TrendingDown, TrendingUp, Info, Cpu,
  ChevronRight, BrainCircuit,
  BarChartIcon, Layers, RefreshCw,
  GitCompare, AlertCircle, Clock, Hash, Wrench
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, Bar, BarChart
} from 'recharts';
import { API_URL } from '../config';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * AlgoAnalysisPopup.jsx
 * ────────────────────
 * Advanced analytics for GA, ACO, and PSO comparison.
 * Shows convergence curves, stability scores, and path diversity.
 */

const ALGO_CONFIG = {
  ga: { name: 'Genetic Algorithm', color: '#3b82f6', icon: Zap },
  aco: { name: 'Ant Colony Opt.', color: '#10b981', icon: BarChart2 },
  pso: { name: 'Particle Swarm', color: '#a855f7', icon: Activity },
};

export function AlgoAnalysisPopup({ isOpen, onClose, metrics, locationName }) {
  const [activeTab, setActiveTab] = useState('summary');
  const [chatMessages, setChatMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);

  // MCP vs Non-MCP state
  const [mcpResults, setMcpResults] = useState(null);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [mcpError, setMcpError] = useState(null);
  const [expandedQ, setExpandedQ] = useState(null);

  // NOTE: `algoKeys` is computed below from `metrics` to avoid showing empty cards.

  // 1. Prepare data for Convergence Chart
  const chartData = useMemo(() => {
    if (!metrics) return [];
    const gaHistory = metrics.ga?.fitness_history || [];
    const acoHistory = metrics.aco?.fitness_history || [];
    const psoHistory = metrics.pso?.fitness_history || [];

    const maxLen = Math.max(gaHistory.length, acoHistory.length, psoHistory.length);
    const data = [];

    for (let i = 0; i < maxLen; i++) {
      data.push({
        iteration: i + 1,
        GA: gaHistory[i] != null ? Math.round(gaHistory[i] * 10) / 10 : null,
        ACO: acoHistory[i] != null ? Math.round(acoHistory[i] * 10) / 10 : null,
        PSO: psoHistory[i] != null ? Math.round(psoHistory[i] * 10) / 10 : null,
      });
    }
    return data;
  }, [metrics]);

  // 1. Diagnostics: Log analysis metrics when they arrive
  useEffect(() => {
    if (metrics) {
      console.log("[AlgoAnalysisDeepDive] Received Metrics:", metrics);
    }
  }, [metrics]);

  const algoKeys = useMemo(() => {
    if (!metrics) return [];
    // Only include keys that have actual data
    return Object.keys(metrics).filter(k => metrics[k] && typeof metrics[k] === 'object');
  }, [metrics]);

  const breakdownData = useMemo(() => {
    if (algoKeys.length === 0) return [];
    return algoKeys.map(key => {
      const b = metrics[key]?.breakdown || {};
      return {
        name: key.toUpperCase(),
        Distance: b.distance_score || 0,
        Time: b.time_score || 0,
        CapacityPenalty: b.capacity_penalty || 0,
        TerrainPenalty: b.terrain_penalty || 0,
        UnassignedPenalty: b.unassigned_penalty || 0,
      };
    });
  }, [metrics, algoKeys]);

  if (!isOpen || !metrics) return null;

  // ── Research Planner Logic ──────────────────────────────────────────────────
  const runResearchPlanner = async () => {
    if (chatMessages.length > 0) return;

    setIsTyping(true);

    const outgoing = {
      question: `Perform a deep logical analysis of these algorithm metrics for the ${locationName} region. Specifically explain which algorithm is superior based on Convergence Speed, Stochastic Stability, and Path Diversity. Translate these mathematical results into real-world evacuation survival reasoning.`,
      context: {
        mode: 'compare',
        algorithm_analysis: metrics,
        location: locationName
      }
    };

    console.info('[AlgoAnalysis] Sending research planner body:', outgoing);

    try {
      const response = await fetch(`${API_URL}/algorithm-analysis-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metrics: metrics,
          location: locationName
        })
      });

      console.info('[AlgoAnalysis] Response status:', response.status, 'headers:', response.headers.get('content-type'));

      // If server didn't return a streaming body, fallback to text/json
      if (!response.body) {
        const text = await response.text();
        console.warn('[AlgoAnalysis] No streaming body, fallback text:', text.slice(0, 1000));
        setChatMessages([{ role: 'assistant', content: text }]);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      // initialise chat message shown in UI
      setChatMessages([{ role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        console.debug('[AlgoAnalysis] SSE chunk:', chunk.slice(0, 1000));

        // Common SSE format: lines beginning with 'data: '
        const lines = chunk.split('\n');
        let appended = false;

        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              // If backend streams tokens under `token` use that, otherwise append raw `text` or string
              const token = data.token ?? data.text ?? (typeof data === 'string' ? data : null);
              if (token) {
                setChatMessages(prev => {
                  const last = prev[0] || { role: 'assistant', content: '' };
                  const updated = [{ ...last, content: (last.content || '') + token }];
                  return updated;
                });
                appended = true;
              }
            } catch (e) {
              // Not JSON — append raw text after 'data: '
              const raw = line.slice(6);
              setChatMessages(prev => {
                const last = prev[0] || { role: 'assistant', content: '' };
                const updated = [{ ...last, content: (last.content || '') + raw }];
                return updated;
              });
              appended = true;
            }
          }
        }

        // If no SSE data lines found, append chunk as plain text (fallback)
        if (!appended) {
          setChatMessages(prev => {
            const last = prev[0] || { role: 'assistant', content: '' };
            const updated = [{ ...last, content: (last.content || '') + chunk }];
            return updated;
          });
        }
      }

      console.info('[AlgoAnalysis] Research planner stream complete');
    } catch (err) {
      console.error('Agent Analysis Error:', err);
      setChatMessages([{ role: 'assistant', content: 'Failed to connect to the Research Planner. Please ensure the backend is running.' }]);
    } finally {
      setIsTyping(false);
    }
  };

  const runMcpComparison = async () => {
    if (mcpResults || mcpLoading) return;
    setMcpLoading(true);
    setMcpError(null);
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 300000); // 5 min hard timeout
      const res = await fetch(`${API_URL}/research/mcp-comparison`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_judge: false }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      if (!data.results || data.results.length === 0) {
        throw new Error('Both Gemini and Groq API quotas are exhausted. Please try again tomorrow when quotas reset (midnight PST / ~12:30 PM IST).');
      }
      // Check if all results failed (empty responses)
      const allFailed = data.results.every(r =>
        !r.non_mcp?.response_text && !r.mcp?.response_text
      );
      if (allFailed) {
        throw new Error('API quotas exhausted (Gemini: 20 req/day, Groq: 100K tokens/day). Results will be available after midnight PST (~12:30 PM IST).');
      }
      setMcpResults(data.results || []);
    } catch (err) {
      if (err.name === 'AbortError') {
        setMcpError('Request timed out after 5 minutes. Both API quotas may be exhausted — try again tomorrow.');
      } else {
        setMcpError(err.message);
      }
    } finally {
      setMcpLoading(false);
    }
  };

  return (
    <div className="analysis-overlay">
      <div className="analysis-modal">
        {/* Header */}
        <div className="analysis-header">
          <div className="header-left">
            <div className="icon-wrap">
              <BrainCircuit size={20} className="header-icon" />
            </div>
            <div>
              <h2>Algorithm Deep-Dive Analysis</h2>
              <p className="subtitle">Location: {locationName} • 3-Run Stability Test</p>
            </div>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="analysis-tabs">
          <button
            className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
            onClick={() => setActiveTab('summary')}
          >
            <Layers size={14} /> Performance Dashboard
          </button>
          <button
            className={`tab-btn ${activeTab === 'convergence' ? 'active' : ''}`}
            onClick={() => setActiveTab('convergence')}
          >
            <TrendingDown size={14} /> Convergence Curves
          </button>
          <button
            className={`tab-btn ${activeTab === 'breakdown' ? 'active' : ''}`}
            onClick={() => setActiveTab('breakdown')}
          >
            <BarChartIcon size={14} /> Fitness Breakdown
          </button>
          <button
            className={`tab-btn ${activeTab === 'agent' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('agent');
              runResearchPlanner();
            }}
          >
            <Cpu size={14} /> Research Planner AI
          </button>
          <button
            className={`tab-btn ${activeTab === 'mcp' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('mcp');
              runMcpComparison();
            }}
          >
            <GitCompare size={14} /> MCP vs Non-MCP
          </button>
        </div>

        {/* Content */}
        <div className="analysis-content">
          {activeTab === 'summary' && (
            <div className="summary-grid">
              {algoKeys.map(key => {
                const m = metrics[key] || {};
                const C = ALGO_CONFIG[key] || { name: key.toUpperCase(), color: '#64748b', icon: Info };
                const Icon = C.icon;
                return (
                  <div key={key} className="algo-card" style={{ borderColor: C.color }}>
                    <div className="algo-card-header">
                      <div className="icon-title">
                        <Icon size={16} style={{ color: C.color }} />
                        <span className="name">{C.name}</span>
                      </div>
                      <div className="badge" style={{ background: C.color + '20', color: C.color }}>
                        {key.toUpperCase()}
                      </div>
                    </div>

                    <div className="metric-row">
                      <div className="metric-item">
                        <span className="lbl">Stochastic Stability</span>
                        <div className="val-wrap">
                          <Shield size={12} className="meta-icon" />
                          <span className="val">{(m.stability_score * 100).toFixed(1)}%</span>
                        </div>
                        <div className="progress-bg">
                          <div className="progress-fill" style={{ width: `${m.stability_score * 100}%`, background: C.color }} />
                        </div>
                      </div>
                    </div>

                    <div className="metric-row">
                      <div className="metric-item">
                        <span className="lbl">Path Diversity (Overlap)</span>
                        <div className="val-wrap">
                          <TrendingUp size={12} className="meta-icon" />
                          <span className="val">{(m.path_diversity * 100).toFixed(1)}%</span>
                        </div>
                        <p className="desc">
                          {m.path_diversity > 0.8 ? 'Excellent load balancing.' : 'High road convergence detected.'}
                        </p>
                      </div>
                    </div>

                    <div className="stats-mini-grid">
                      <div className="mini-item">
                        <span className="lbl">Mean Fitness</span>
                        <span className="val">{m.mean_fitness.toLocaleString()}</span>
                      </div>
                      <div className="mini-item">
                        <span className="lbl">Convergence Iter</span>
                        <span className="val">{m.convergence_speed}</span>
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Loading skeleton cards for algorithms still being computed */}
              {['ga', 'aco', 'pso'].filter(k => !algoKeys.includes(k)).map(key => {
                const C = ALGO_CONFIG[key] || { name: key.toUpperCase(), color: '#64748b', icon: Info };
                const Icon = C.icon;
                return (
                  <div key={key} className="algo-card algo-card--loading" style={{ borderColor: C.color + '40', opacity: 0.6 }}>
                    <div className="algo-card-header">
                      <div className="icon-title">
                        <Icon size={16} style={{ color: C.color + '80' }} />
                        <span className="name" style={{ color: '#94a3b8' }}>{C.name}</span>
                      </div>
                      <div className="badge" style={{ background: C.color + '10', color: C.color + '80' }}>
                        {key.toUpperCase()}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem', gap: '0.75rem' }}>
                      <RefreshCw size={20} className="spin" style={{ color: C.color }} />
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>Running 3 stability tests…</span>
                    </div>
                  </div>
                );
              })}

              <div className="analysis-footer-note">
                <Info size={12} />
                <span>
                  <strong>Stochastic Stability</strong> measures how consistent the algorithm is across multiple independent runs.
                  Low stability suggests the algorithm is sensitive to initial random seeding.
                </span>
              </div>
            </div>
          )}

          {activeTab === 'convergence' && (
            <div className="chart-container">
              <div className="chart-header">
                <h3>Fitness Convergence History</h3>
                <p>Tracking the minimize objective across generations (Lower = Better). Y-axis auto-scaled to show differences.</p>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis
                      dataKey="iteration"
                      label={{ value: 'Generation / Iteration', position: 'insideBottom', offset: -5 }}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      label={{ value: 'Fitness Score', angle: -90, position: 'insideLeft' }}
                      domain={['auto', 'auto']}
                      tickFormatter={(val) => val >= 1000000 ? `${(val / 1000000).toFixed(2)}M` : val >= 1000 ? `${(val / 1000).toFixed(0)}K` : val}
                    />
                    <Tooltip
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                      formatter={(value) => [value != null ? Math.round(value).toLocaleString() : 'N/A', undefined]}
                    />
                    <Legend verticalAlign="top" height={36} />
                    <Line
                      type="monotone"
                      dataKey="GA"
                      stroke={ALGO_CONFIG.ga.color}
                      strokeWidth={3}
                      dot={false}
                      activeDot={{ r: 6 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="ACO"
                      stroke={ALGO_CONFIG.aco.color}
                      strokeWidth={3}
                      dot={false}
                      activeDot={{ r: 6 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="PSO"
                      stroke={ALGO_CONFIG.pso.color}
                      strokeWidth={3}
                      dot={false}
                      activeDot={{ r: 6 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-insight">
                <Zap size={14} />
                <span>
                  PSO usually converges faster to its global best, but GA often continues to find small improvements in later generations through mutation.
                </span>
              </div>
            </div>
          )}

          {activeTab === 'breakdown' && (
            <div className="chart-container" style={{ minHeight: '400px' }}>
              <div className="chart-header">
                <h3>Fitness Component Breakdown</h3>
                <p>Comparing internal cost factors across algorithms (Lower = Better)</p>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={breakdownData} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" width={60} tick={{ fontSize: 12, fontWeight: 700 }} />
                    <Tooltip
                      cursor={{ fill: 'transparent' }}
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                    />
                    <Legend />
                    <Bar dataKey="Distance" stackId="a" fill="#3b82f6" radius={[4, 0, 0, 4]} />
                    <Bar dataKey="Time" stackId="a" fill="#0ea5e9" />
                    <Bar dataKey="CapacityPenalty" stackId="a" fill="#ef4444" />
                    <Bar dataKey="TerrainPenalty" stackId="a" fill="#f59e0b" />
                    <Bar dataKey="UnassignedPenalty" stackId="a" fill="#a855f7" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-insight" style={{ background: '#ecfdf5', borderColor: '#a7f3d0', color: '#065f46' }}>
                <Shield size={14} />
                <span>
                  <strong>Capacity Penalty</strong> indicates how much the algorithm "cheated" by overflowing shelters. A high penalty usually means the algorithm failed to find a valid distribution.
                </span>
              </div>
            </div>
          )}

          {activeTab === 'mcp' && (
            <div className="mcp-container">
              {mcpLoading && (
                <div className="mcp-loading">
                  <div className="spinner" />
                  <p>Running MCP vs Non-MCP comparison across {5} questions…</p>
                  <p className="mcp-loading-sub">This may take 60–120s due to LLM calls and inter-question delays.</p>
                </div>
              )}

              {mcpError && (
                <div className="mcp-error">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Comparison failed</strong>
                    <p>{mcpError}</p>
                  </div>
                </div>
              )}

              {!mcpLoading && !mcpError && !mcpResults && (
                <div className="mcp-empty">
                  <GitCompare size={32} style={{ color: '#94a3b8' }} />
                  <p>Click the tab to start the comparison.</p>
                </div>
              )}

              {mcpResults && mcpResults.length > 0 && (() => {
                // Compute averages
                const scored = mcpResults.filter(r =>
                  r.non_mcp?.auto_metrics && r.mcp?.auto_metrics
                );
                const nmAvgNum = scored.length
                  ? (scored.reduce((s, r) => s + (r.non_mcp.auto_metrics.numeric_match_rate || 0), 0) / scored.length).toFixed(2)
                  : '—';
                const mcpAvgNum = scored.length
                  ? (scored.reduce((s, r) => s + (r.mcp.auto_metrics.numeric_match_rate || 0), 0) / scored.length).toFixed(2)
                  : '—';
                const nmAvgLat = scored.length
                  ? (scored.reduce((s, r) => s + (r.non_mcp.latency_s || 0), 0) / scored.length).toFixed(1)
                  : '—';
                const mcpAvgLat = scored.length
                  ? (scored.reduce((s, r) => s + (r.mcp.latency_s || 0), 0) / scored.length).toFixed(1)
                  : '—';

                return (
                  <>
                    {/* Summary strip */}
                    <div className="mcp-summary-strip">
                      <div className="mcp-summary-card nm">
                        <span className="mcp-mode-label">Non-MCP</span>
                        <div className="mcp-summary-stats">
                          <div><Clock size={12} /><span>{nmAvgLat}s avg latency</span></div>
                          <div><Hash size={12} /><span>{nmAvgNum} numeric accuracy</span></div>
                          <div><Wrench size={12} /><span>0 tool calls</span></div>
                        </div>
                      </div>
                      <div className="mcp-vs-badge">VS</div>
                      <div className="mcp-summary-card mcp">
                        <span className="mcp-mode-label">MCP</span>
                        <div className="mcp-summary-stats">
                          <div><Clock size={12} /><span>{mcpAvgLat}s avg latency</span></div>
                          <div><Hash size={12} /><span>{mcpAvgNum} numeric accuracy</span></div>
                          <div><Wrench size={12} /><span>{scored.reduce((s, r) => s + (r.mcp.tool_call_count || 0), 0)} total tool calls</span></div>
                        </div>
                      </div>
                    </div>

                    {/* Per-question results */}
                    <div className="mcp-questions">
                      {mcpResults.map((r, i) => {
                        const nm = r.non_mcp || {};
                        const mc = r.mcp || {};
                        const isOpen = expandedQ === i;
                        const nmWins = (nm.auto_metrics?.numeric_match_rate || 0) >= (mc.auto_metrics?.numeric_match_rate || 0);

                        return (
                          <div key={i} className="mcp-question-card">
                            <div
                              className="mcp-question-header"
                              onClick={() => setExpandedQ(isOpen ? null : i)}
                            >
                              <div className="mcp-q-label">
                                <span className="mcp-q-num">Q{i + 1}</span>
                                <span className="mcp-q-text">{r.question}</span>
                              </div>
                              <div className="mcp-q-badges">
                                <span className={`mcp-winner-badge ${nmWins ? 'nm' : 'mcp'}`}>
                                  {nmWins ? 'Non-MCP' : 'MCP'} wins
                                </span>
                                <ChevronRight size={14} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition: '0.2s' }} />
                              </div>
                            </div>

                            {/* Metrics row always visible */}
                            <div className="mcp-metrics-row">
                              <div className="mcp-metric-cell">
                                <span className="mcp-metric-label">Provider</span>
                                <span className="mcp-metric-nm">{nm.provider || '—'}</span>
                                <span className="mcp-metric-sep">/</span>
                                <span className="mcp-metric-mcp">{mc.provider || '—'}</span>
                              </div>
                              <div className="mcp-metric-cell">
                                <span className="mcp-metric-label">Latency</span>
                                <span className="mcp-metric-nm">{nm.latency_s ?? '—'}s</span>
                                <span className="mcp-metric-sep">/</span>
                                <span className="mcp-metric-mcp">{mc.latency_s ?? '—'}s</span>
                              </div>
                              <div className="mcp-metric-cell">
                                <span className="mcp-metric-label">Words</span>
                                <span className="mcp-metric-nm">{nm.response_words ?? '—'}</span>
                                <span className="mcp-metric-sep">/</span>
                                <span className="mcp-metric-mcp">{mc.response_words ?? '—'}</span>
                              </div>
                              <div className="mcp-metric-cell">
                                <span className="mcp-metric-label">Numeric Acc.</span>
                                <span className="mcp-metric-nm">{nm.auto_metrics?.numeric_match_rate?.toFixed(2) ?? '—'}</span>
                                <span className="mcp-metric-sep">/</span>
                                <span className="mcp-metric-mcp">{mc.auto_metrics?.numeric_match_rate?.toFixed(2) ?? '—'}</span>
                              </div>
                              <div className="mcp-metric-cell">
                                <span className="mcp-metric-label">Tool Calls</span>
                                <span className="mcp-metric-nm">0</span>
                                <span className="mcp-metric-sep">/</span>
                                <span className="mcp-metric-mcp">{mc.tool_call_count ?? '—'}</span>
                              </div>
                            </div>

                            {/* Tool trace + responses (expanded) */}
                            {isOpen && (
                              <div className="mcp-expanded">
                                {mc.tool_calls?.length > 0 && (
                                  <div className="mcp-tool-trace">
                                    <span className="mcp-trace-label">Tools called:</span>
                                    {mc.tool_calls.map((t, j) => (
                                      <span key={j} className="mcp-tool-chip">{t.name}</span>
                                    ))}
                                  </div>
                                )}
                                <div className="mcp-responses">
                                  <div className="mcp-response-col nm">
                                    <div className="mcp-response-header">Non-MCP Response</div>
                                    <div className="mcp-response-body">
                                      {nm.response_text
                                        ? nm.response_text.slice(0, 400) + (nm.response_text.length > 400 ? '…' : '')
                                        : <em style={{ color: '#94a3b8' }}>No response (quota exhausted)</em>}
                                    </div>
                                  </div>
                                  <div className="mcp-response-col mcp">
                                    <div className="mcp-response-header">MCP Response</div>
                                    <div className="mcp-response-body">
                                      {mc.response_text
                                        ? mc.response_text.slice(0, 400) + (mc.response_text.length > 400 ? '…' : '')
                                        : <em style={{ color: '#94a3b8' }}>No response (quota exhausted)</em>}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    <div className="mcp-footer-note">
                      <Info size={12} />
                      <span>
                        <strong>NM = Non-MCP</strong> (static dump, ~7,600 words) vs <strong>MCP</strong> (minimal seed + live tool calls).
                        Numeric accuracy = fraction of cited numbers matching actual simulation data.
                        Latency includes all tool round-trips for MCP.
                      </span>
                    </div>
                  </>
                );
              })()}
            </div>
          )}

          {activeTab === 'agent' && (
            <div className="agent-container">
              <div className="agent-chat-area">
                {chatMessages.length === 0 ? (
                  <div className="agent-loading">
                    <div className="spinner" />
                    <p>Research Planner is crunching numbers...</p>
                  </div>
                ) : (
                  <div className="chat-scroll">
                    {chatMessages.map((msg, i) => (
                      <div key={i} className={`chat-bubble ${msg.role}`}>
                        <div className="bubble-header">
                          <Cpu size={12} /> Research Planner Assistant
                        </div>
                        <div className="bubble-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                          {isTyping && <span className="typing-cursor">●</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .analysis-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          background: rgba(15, 23, 42, 0.4);
          backdrop-filter: blur(8px);
          z-index: 9999;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .analysis-modal {
          width: 900px;
          max-width: 95vw;
          height: 650px;
          background: rgba(255, 255, 255, 0.95);
          border-radius: 24px;
          border: 1px solid rgba(255, 255, 255, 0.2);
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          position: relative;
        }

        .analysis-header {
          padding: 24px 32px;
          background: white;
          border-bottom: 1px solid #f1f5f9;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .header-left {
          display: flex;
          gap: 16px;
          align-items: center;
        }

        .icon-wrap {
          width: 40px;
          height: 40px;
          background: #f8fafc;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #3b82f6;
        }

        .analysis-header h2 {
          margin: 0;
          font-size: 18px;
          font-weight: 800;
          color: #1e293b;
          letter-spacing: -0.01em;
        }

        .subtitle {
          margin: 0;
          font-size: 11px;
          color: #64748b;
          font-weight: 500;
        }

        .close-btn {
          width: 32px;
          height: 32px;
          border-radius: 10px;
          border: none;
          background: #f1f5f9;
          color: #64748b;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s;
        }

        .close-btn:hover {
          background: #fee2e2;
          color: #ef4444;
        }

        .analysis-tabs {
          display: flex;
          padding: 0 32px;
          background: white;
          border-bottom: 1px solid #f1f5f9;
          gap: 24px;
        }

        .tab-btn {
          padding: 14px 4px;
          font-size: 13px;
          font-weight: 600;
          color: #64748b;
          background: none;
          border: none;
          border-bottom: 2px solid transparent;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 8px;
          transition: all 0.2s;
        }

        .tab-btn:hover {
          color: #3b82f6;
        }

        .tab-btn.active {
          color: #3b82f6;
          border-bottom-color: #3b82f6;
        }

        .analysis-content {
          flex: 1;
          padding: 32px;
          overflow-y: auto;
          background: #f8fafc;
        }

        .summary-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
        }

        .algo-card {
          background: white;
          border-radius: 20px;
          padding: 20px;
          border: 1px solid #e2e8f0;
          box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
          transition: transform 0.2s;
        }

        .algo-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
        }

        .icon-title {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .icon-title .name {
          font-size: 14px;
          font-weight: 700;
          color: #1e293b;
        }

        .badge {
          font-size: 10px;
          font-weight: 800;
          padding: 4px 10px;
          border-radius: 8px;
        }

        .metric-row {
          margin-bottom: 16px;
        }

        .lbl {
          display: block;
          font-size: 10px;
          font-weight: 700;
          color: #64748b;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 4px;
          }

        .val-wrap {
          display: flex;
          align-items: baseline;
          gap: 4px;
          margin-bottom: 6px;
        }

        .val {
          font-size: 18px;
          font-weight: 800;
          color: #1e293b;
        }

        .meta-icon {
          opacity: 0.5;
        }

        .progress-bg {
          height: 6px;
          background: #f1f5f9;
          border-radius: 10px;
          overflow: hidden;
        }

        .progress-fill {
          height: 100%;
          border-radius: 10px;
          transition: width 1s ease-out;
        }

        .desc {
          font-size: 11px;
          color: #64748b;
          margin: 4px 0 0;
          line-height: 1.4;
        }

        .stats-mini-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px dashed #e2e8f0;
        }

        .mini-item .val {
          font-size: 14px;
          display: block;
        }

        .analysis-footer-note {
          grid-column: 1 / -1;
          background: #eff6ff;
          border-radius: 12px;
          padding: 12px 16px;
          display: flex;
          gap: 10px;
          align-items: center;
          font-size: 11px;
          color: #1e40af;
          border: 1px solid #bfdbfe;
        }

        /* Chart */
        .chart-wrapper {
          background: white;
          padding: 24px;
          border-radius: 20px;
          border: 1px solid #e2e8f0;
        }

        .chart-header {
          margin-bottom: 16px;
        }

        .chart-header h3 {
          margin: 0;
          font-size: 15px;
          color: #1e293b;
        }

        .chart-header p {
          margin: 4px 0 0;
          font-size: 11px;
          color: #64748b;
        }

        .chart-insight {
          margin-top: 16px;
          background: #fdf4ff;
          padding: 12px 16px;
          border-radius: 12px;
          border: 1px solid #f5d0fe;
          display: flex;
          gap: 10px;
          font-size: 11px;
          color: #701a75;
          align-items: center;
        }

        /* Agent Chat */
        .agent-chat-area {
          height: 480px;
          background: white;
          border-radius: 20px;
          border: 1px solid #e2e8f0;
          display: flex;
          flex-direction: column;
        }

        .chat-scroll {
          flex: 1;
          overflow-y: auto;
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .chat-bubble {
          max-width: 90%;
          padding: 16px;
          border-radius: 16px;
          line-height: 1.6;
          font-size: 14px;
        }

        .chat-bubble.assistant {
          align-self: flex-start;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          color: #334155;
          width: 100%;
        }

        .bubble-content h1, .bubble-content h2, .bubble-content h3 {
          margin: 16px 0 8px;
          border-bottom: 1px solid #e2e8f0;
          padding-bottom: 4px;
          color: #1e293b;
        }
        .bubble-content p { margin: 8px 0; }
        .bubble-content table {
          width: 100%;
          border-collapse: collapse;
          margin: 16px 0;
          font-size: 12px;
        }
        .bubble-content th, .bubble-content td {
          border: 1px solid #e2e8f0;
          padding: 8px;
          text-align: left;
        }
        .bubble-content th { background: #f1f5f9; }
        .bubble-content ul, .bubble-content ol {
          padding-left: 20px;
          margin: 8px 0;
        }

        .bubble-header {
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
          color: #64748b;
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .agent-loading {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
        }

        .spinner {
          width: 32px;
          height: 32px;
          border: 3px solid #f1f5f9;
          border-top-color: #3b82f6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .typing-cursor {
          display: inline-block;
          width: 8px;
          animation: blink 1s infinite;
          margin-left: 2px;
          color: #3b82f6;
        }

        @keyframes blink {
          0%, 100% { opacity: 0; }
          50% { opacity: 1; }
        }

        /* ── MCP vs Non-MCP tab ── */
        .mcp-container {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .mcp-loading, .mcp-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          padding: 60px 20px;
          color: #64748b;
          font-size: 13px;
          text-align: center;
        }

        .mcp-loading-sub {
          font-size: 11px;
          color: #94a3b8;
          margin: 0;
        }

        .mcp-error {
          display: flex;
          gap: 12px;
          align-items: flex-start;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 12px;
          padding: 16px;
          color: #991b1b;
          font-size: 13px;
        }

        .mcp-error p { margin: 4px 0 0; font-size: 11px; color: #b91c1c; }

        .mcp-summary-strip {
          display: flex;
          align-items: center;
          gap: 12px;
          background: white;
          border-radius: 16px;
          padding: 16px 20px;
          border: 1px solid #e2e8f0;
        }

        .mcp-summary-card {
          flex: 1;
          padding: 12px 16px;
          border-radius: 12px;
        }

        .mcp-summary-card.nm {
          background: #eff6ff;
          border: 1px solid #bfdbfe;
        }

        .mcp-summary-card.mcp {
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
        }

        .mcp-mode-label {
          display: block;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          margin-bottom: 8px;
          color: #475569;
        }

        .mcp-summary-stats {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .mcp-summary-stats > div {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #334155;
          font-weight: 500;
        }

        .mcp-vs-badge {
          font-size: 13px;
          font-weight: 900;
          color: #94a3b8;
          padding: 0 8px;
        }

        .mcp-questions {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .mcp-question-card {
          background: white;
          border-radius: 14px;
          border: 1px solid #e2e8f0;
          overflow: hidden;
        }

        .mcp-question-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          cursor: pointer;
          gap: 12px;
        }

        .mcp-question-header:hover {
          background: #f8fafc;
        }

        .mcp-q-label {
          display: flex;
          align-items: center;
          gap: 10px;
          flex: 1;
          min-width: 0;
        }

        .mcp-q-num {
          font-size: 10px;
          font-weight: 800;
          background: #f1f5f9;
          color: #475569;
          padding: 3px 7px;
          border-radius: 6px;
          flex-shrink: 0;
        }

        .mcp-q-text {
          font-size: 12px;
          font-weight: 600;
          color: #1e293b;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .mcp-q-badges {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-shrink: 0;
        }

        .mcp-winner-badge {
          font-size: 10px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
        }

        .mcp-winner-badge.mcp {
          background: #dcfce7;
          color: #166534;
        }

        .mcp-winner-badge.nm {
          background: #dbeafe;
          color: #1e40af;
        }

        .mcp-metrics-row {
          display: flex;
          gap: 0;
          border-top: 1px solid #f1f5f9;
          background: #fafafa;
        }

        .mcp-metric-cell {
          flex: 1;
          padding: 8px 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          border-right: 1px solid #f1f5f9;
          gap: 2px;
        }

        .mcp-metric-cell:last-child { border-right: none; }

        .mcp-metric-label {
          font-size: 9px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #94a3b8;
        }

        .mcp-metric-nm {
          font-size: 11px;
          font-weight: 600;
          color: #3b82f6;
        }

        .mcp-metric-mcp {
          font-size: 11px;
          font-weight: 600;
          color: #10b981;
        }

        .mcp-metric-sep {
          font-size: 10px;
          color: #cbd5e1;
        }

        .mcp-expanded {
          padding: 12px 16px;
          border-top: 1px solid #f1f5f9;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .mcp-tool-trace {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 6px;
        }

        .mcp-trace-label {
          font-size: 10px;
          font-weight: 700;
          color: #64748b;
          text-transform: uppercase;
        }

        .mcp-tool-chip {
          font-size: 10px;
          font-weight: 600;
          background: #f0fdf4;
          color: #166534;
          border: 1px solid #bbf7d0;
          padding: 2px 8px;
          border-radius: 6px;
        }

        .mcp-responses {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }

        .mcp-response-col {
          border-radius: 10px;
          overflow: hidden;
          border: 1px solid #e2e8f0;
        }

        .mcp-response-col.nm { border-color: #bfdbfe; }
        .mcp-response-col.mcp { border-color: #bbf7d0; }

        .mcp-response-header {
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 6px 12px;
          border-bottom: 1px solid #e2e8f0;
        }

        .mcp-response-col.nm .mcp-response-header {
          background: #eff6ff;
          color: #1e40af;
          border-color: #bfdbfe;
        }

        .mcp-response-col.mcp .mcp-response-header {
          background: #f0fdf4;
          color: #166534;
          border-color: #bbf7d0;
        }

        .mcp-response-body {
          padding: 10px 12px;
          font-size: 11px;
          line-height: 1.6;
          color: #334155;
          background: white;
          white-space: pre-wrap;
        }

        .mcp-footer-note {
          background: #eff6ff;
          border-radius: 12px;
          padding: 12px 16px;
          display: flex;
          gap: 10px;
          align-items: flex-start;
          font-size: 11px;
          color: #1e40af;
          border: 1px solid #bfdbfe;
        }
      `}</style>
    </div>
  );
}
