import React, { useState, useEffect, useMemo } from 'react';
import {
  X, BarChart2, Activity, Zap, Shield,
  TrendingDown, TrendingUp, Info, Cpu,
  ChevronRight, BrainCircuit, MessageSquare,
  BarChartIcon, Layers, Timer, Repeat, RefreshCw
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, AreaChart, Area, Bar, BarChart
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
      `}</style>
    </div>
  );
}
