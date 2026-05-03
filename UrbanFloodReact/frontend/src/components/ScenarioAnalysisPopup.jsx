import React, { useState, useEffect, useMemo } from 'react';
import {
  X, BarChart2, Activity, Zap, Shield,
  TrendingDown, TrendingUp, Info, Cpu,
  BrainCircuit, Layers, RefreshCw, AlertTriangle, Trophy
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { API_URL } from '../config';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALGO_CONFIG = {
  ga: { name: 'GA', fullName: 'Genetic Algorithm', color: '#3b82f6', icon: Zap },
  aco: { name: 'ACO', fullName: 'Ant Colony Opt.', color: '#10b981', icon: BarChart2 },
  pso: { name: 'PSO', fullName: 'Particle Swarm', color: '#a855f7', icon: Activity },
};

const SCENARIOS = [
  { key: 'low', label: 'Low (50mm)', color: '#34d399' },
  { key: 'medium', label: 'Medium (150mm)', color: '#fbbf24' },
  { key: 'high', label: 'High (250mm)', color: '#f87171' }
];

export function ScenarioAnalysisPopup({ isOpen, onClose, metrics, locationName }) {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [chatMessages, setChatMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (metrics) {
      console.log("[ScenarioAnalysisPopup] Received Metrics:", metrics);
    }
  }, [metrics]);

  const fitnessChartData = useMemo(() => {
    if (!metrics) return [];
    
    return SCENARIOS.map(s => {
      const dataPoint = { name: s.label };
      if (metrics[s.key]) {
        ['ga', 'aco', 'pso'].forEach(algo => {
          if (metrics[s.key][algo]) {
             // Fitness is high, so we show it in millions for readability
             dataPoint[`${algo.toUpperCase()}_Fitness`] = metrics[s.key][algo].fitness / 1_000_000;
          }
        });
      }
      return dataPoint;
    });
  }, [metrics]);

  const timeChartData = useMemo(() => {
    if (!metrics) return [];
    
    return SCENARIOS.map(s => {
      const dataPoint = { name: s.label };
      if (metrics[s.key]) {
        ['ga', 'aco', 'pso'].forEach(algo => {
          if (metrics[s.key][algo]) {
             dataPoint[`${algo.toUpperCase()}_Time`] = metrics[s.key][algo].execution_time;
          }
        });
      }
      return dataPoint;
    });
  }, [metrics]);

  const pressureChartData = useMemo(() => {
    if (!metrics) return [];
    
    return SCENARIOS.map(s => {
      const dataPoint = { name: s.label };
      if (metrics[s.key]) {
        ['ga', 'aco', 'pso'].forEach(algo => {
          if (metrics[s.key][algo]) {
             dataPoint[`${algo.toUpperCase()}_Pressure`] = metrics[s.key][algo].total_bottleneck_load || metrics[s.key][algo].pressure_points_count || 0;
          }
        });
      }
      return dataPoint;
    });
  }, [metrics]);

  if (!isOpen || !metrics) return null;

  const runScenarioPlanner = async () => {
    if (chatMessages.length > 0) return;

    setIsTyping(true);

    try {
      const response = await fetch(`${API_URL}/scenario-analysis-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metrics: metrics,
          location: locationName
        })
      });

      if (!response.body) {
        const text = await response.text();
        setChatMessages([{ role: 'assistant', content: text }]);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      setChatMessages([{ role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        
        const lines = chunk.split('\n');
        let appended = false;

        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
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

        if (!appended) {
          setChatMessages(prev => {
            const last = prev[0] || { role: 'assistant', content: '' };
            const updated = [{ ...last, content: (last.content || '') + chunk }];
            return updated;
          });
        }
      }

    } catch (err) {
      console.error('Agent Analysis Error:', err);
      setChatMessages([{ role: 'assistant', content: 'Failed to connect to the Scenario Analyst. Please ensure the backend is running.' }]);
    } finally {
      setIsTyping(false);
    }
  };

  const isComplete = SCENARIOS.every(s => metrics[s.key] && Object.keys(metrics[s.key]).length > 0);

  return (
    <div className="analysis-overlay">
      <div className="analysis-modal">
        {/* Header */}
        <div className="analysis-header">
          <div className="header-left">
            <div className="icon-wrap" style={{ background: '#ecfeff', color: '#06b6d4' }}>
              <BrainCircuit size={20} className="header-icon" />
            </div>
            <div>
              <h2>Scenario Algorithm Analysis</h2>
              <p className="subtitle">Location: {locationName} • Multi-Intensity Flood Stress Test</p>
            </div>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="analysis-tabs">
          <button
            className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <Layers size={14} /> Performance Dashboard
          </button>
          <button
            className={`tab-btn ${activeTab === 'charts' ? 'active' : ''}`}
            onClick={() => setActiveTab('charts')}
          >
            <BarChart2 size={14} /> Resilience Charts
          </button>
          <button
            className={`tab-btn ${activeTab === 'agent' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('agent');
              runScenarioPlanner();
            }}
            disabled={!isComplete}
            style={{ opacity: !isComplete ? 0.5 : 1, cursor: !isComplete ? 'not-allowed' : 'pointer' }}
          >
            <Cpu size={14} /> AI Scenario Analyst
          </button>
        </div>

        {/* Content */}
        <div className="analysis-content">
          {activeTab === 'dashboard' && (
            <div className="dashboard-view">
              {!isComplete && (
                <div className="running-notice">
                  <RefreshCw size={16} className="spin" /> 
                  Generating scenarios and running algorithms. This may take a moment...
                </div>
              )}

              {isComplete && metrics._best_overall_algorithm && (
                <div className="overall-winner-banner" style={{
                  background: 'linear-gradient(135deg, #f0fdfa, #ccfbf1)',
                  border: '1px solid #5eead4',
                  borderRadius: '12px',
                  padding: '16px 24px',
                  marginBottom: '24px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px'
                }}>
                  <div style={{ background: '#14b8a6', color: 'white', padding: '12px', borderRadius: '12px' }}>
                    <Trophy size={24} />
                  </div>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '16px', color: '#0f766e', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      Recommended Algorithm: <strong>{ALGO_CONFIG[metrics._best_overall_algorithm]?.name || metrics._best_overall_algorithm.toUpperCase()}</strong>
                    </h3>
                    <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#0f766e', opacity: 0.8 }}>
                      Based on comprehensive rank evaluation of Fitness, Execution Time, Route Success, and Bottleneck Load across all flood intensities.
                    </p>
                  </div>
                </div>
              )}
              
              <div className="scenario-grid">
                {SCENARIOS.map(scenario => {
                  const sData = metrics[scenario.key] || {};
                  const hasData = Object.keys(sData).length > 0;
                  
                  return (
                    <div key={scenario.key} className="scenario-column">
                      <div className="scenario-title" style={{ borderBottom: `2px solid ${scenario.color}` }}>
                        {scenario.label}
                      </div>
                      
                      {!hasData ? (
                        <div className="scenario-loading">
                          <RefreshCw size={24} className="spin" style={{ color: '#94a3b8' }}/>
                        </div>
                      ) : (
                        <div className="algo-cards-list">
                          {['ga', 'aco', 'pso'].map(algoKey => {
                            const result = sData[algoKey];
                            const C = ALGO_CONFIG[algoKey];
                            if (!result) return null;
                            
                            return (
                              <div key={algoKey} className="small-algo-card" style={{ borderLeft: `4px solid ${C.color}` }}>
                                <div className="sac-header">
                                  <span className="sac-name"><C.icon size={12} color={C.color}/> {C.name}</span>
                                  <span className="sac-time">{result.execution_time.toFixed(1)}s</span>
                                </div>
                                <div className="sac-body">
                                  <div className="sac-metric">
                                    <span className="sac-lbl">Success Rate</span>
                                    <span className="sac-val" style={{ color: result.success_rate_pct < 80 ? '#ef4444' : '#10b981' }}>
                                      {result.success_rate_pct}%
                                    </span>
                                  </div>
                                  <div className="sac-metric">
                                    <span className="sac-lbl" title="Total evacuees stuck at bottleneck junctions">Bottleneck Load</span>
                                    <span className="sac-val">{result.total_bottleneck_load?.toLocaleString() || result.pressure_points_count}</span>
                                  </div>
                                  <div className="sac-metric">
                                    <span className="sac-lbl">Evacuated</span>
                                    <span className="sac-val">{result.total_evacuated.toLocaleString()}</span>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === 'charts' && (
            <div className="charts-view">
              <div className="chart-container" style={{ marginBottom: '24px' }}>
                <div className="chart-header">
                  <h3>Route Quality (Fitness Score)</h3>
                  <p>Total evacuation cost (Weighted Distance + Time + Penalties). Lower is Better.</p>
                </div>
                <div className="chart-wrapper">
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={fitnessChartData} margin={{ top: 20, right: 30, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="name" />
                      <YAxis label={{ value: 'Cost (Millions)', angle: -90, position: 'insideLeft' }} />
                      <Tooltip 
                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                        formatter={(value) => [`${value.toFixed(2)}M`, 'Fitness']}
                      />
                      <Legend />
                      <Bar dataKey="GA_Fitness" name="GA" fill={ALGO_CONFIG.ga.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="ACO_Fitness" name="ACO" fill={ALGO_CONFIG.aco.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="PSO_Fitness" name="PSO" fill={ALGO_CONFIG.pso.color} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="chart-container" style={{ marginBottom: '24px' }}>
                <div className="chart-header">
                  <h3>Computational Efficiency</h3>
                  <p>Algorithm execution time across scenarios (Lower = Faster).</p>
                </div>
                <div className="chart-wrapper">
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={timeChartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="name" />
                      <YAxis label={{ value: 'Seconds', angle: -90, position: 'insideLeft' }} />
                      <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
                      <Legend />
                      <Bar dataKey="GA_Time" name="GA" fill={ALGO_CONFIG.ga.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="ACO_Time" name="ACO" fill={ALGO_CONFIG.aco.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="PSO_Time" name="PSO" fill={ALGO_CONFIG.pso.color} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              
              <div className="chart-container">
                <div className="chart-header">
                  <h3>Bottleneck Load (Evacuees)</h3>
                  <p>Total number of people routed through congested intersections (Lower = Better).</p>
                </div>
                <div className="chart-wrapper">
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={pressureChartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="name" />
                      <YAxis label={{ value: 'Stuck Evacuees', angle: -90, position: 'insideLeft' }} />
                      <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
                      <Legend />
                      <Bar dataKey="GA_Pressure" name="GA" fill={ALGO_CONFIG.ga.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="ACO_Pressure" name="ACO" fill={ALGO_CONFIG.aco.color} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="PSO_Pressure" name="PSO" fill={ALGO_CONFIG.pso.color} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'agent' && (
            <div className="agent-container">
              <div className="agent-chat-area">
                {chatMessages.length === 0 ? (
                  <div className="agent-loading">
                    <div className="spinner" />
                    <p>AI Analyst is reviewing scenario resilience...</p>
                  </div>
                ) : (
                  <div className="chat-scroll">
                    {chatMessages.map((msg, i) => (
                      <div key={i} className={`chat-bubble ${msg.role}`}>
                        <div className="bubble-header">
                          <Cpu size={12} /> AI Scenario Analyst
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
        /* Inheriting base styles from AlgoAnalysisPopup */
        .analysis-overlay {
          position: fixed;
          top: 0; left: 0; width: 100vw; height: 100vh;
          background: rgba(15, 23, 42, 0.4);
          backdrop-filter: blur(8px);
          z-index: 9999;
          display: flex; align-items: center; justify-content: center;
          animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        
        .analysis-modal {
          width: 950px; max-width: 95vw; height: 750px;
          background: rgba(255, 255, 255, 0.95);
          border-radius: 24px; border: 1px solid rgba(255, 255, 255, 0.2);
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
          display: flex; flex-direction: column; overflow: hidden;
        }

        .analysis-header { padding: 24px 32px; background: white; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; }
        .header-left { display: flex; gap: 16px; align-items: center; }
        .icon-wrap { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }
        .analysis-header h2 { margin: 0; font-size: 18px; font-weight: 800; color: #1e293b; }
        .subtitle { margin: 0; font-size: 11px; color: #64748b; font-weight: 500; }
        .close-btn { width: 32px; height: 32px; border-radius: 10px; border: none; background: #f1f5f9; color: #64748b; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; }
        .close-btn:hover { background: #fee2e2; color: #ef4444; }

        .analysis-tabs { display: flex; padding: 0 32px; background: white; border-bottom: 1px solid #f1f5f9; gap: 24px; }
        .tab-btn { padding: 14px 4px; font-size: 13px; font-weight: 600; color: #64748b; background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; }
        .tab-btn:hover:not(:disabled) { color: #3b82f6; }
        .tab-btn.active { color: #3b82f6; border-bottom-color: #3b82f6; }

        .analysis-content { flex: 1; padding: 32px; overflow-y: auto; background: #f8fafc; }

        .running-notice { background: #eff6ff; color: #1d4ed8; padding: 12px; border-radius: 12px; font-size: 13px; display: flex; align-items: center; gap: 12px; margin-bottom: 24px; font-weight: 500; }
        .spin { animation: spin 1.5s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        .scenario-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
        .scenario-column { display: flex; flex-direction: column; gap: 16px; }
        .scenario-title { font-size: 15px; font-weight: 800; color: #1e293b; padding-bottom: 8px; text-align: center; }
        
        .scenario-loading { height: 200px; display: flex; align-items: center; justify-content: center; background: white; border-radius: 16px; border: 1px dashed #cbd5e1; }
        
        .algo-cards-list { display: flex; flex-direction: column; gap: 12px; }
        
        .small-algo-card { background: white; border-radius: 12px; padding: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); border-top: 1px solid #f1f5f9; border-right: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9; }
        .sac-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .sac-name { font-weight: 700; font-size: 13px; color: #1e293b; display: flex; align-items: center; gap: 6px; }
        .sac-time { font-size: 11px; color: #64748b; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
        
        .sac-body { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .sac-metric { display: flex; flex-direction: column; }
        .sac-lbl { font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 2px; }
        .sac-val { font-size: 15px; font-weight: 800; color: #1e293b; }

        .chart-wrapper { background: white; padding: 24px; border-radius: 20px; border: 1px solid #e2e8f0; }
        .chart-header { margin-bottom: 16px; }
        .chart-header h3 { margin: 0; font-size: 15px; color: #1e293b; }
        .chart-header p { margin: 4px 0 0; font-size: 11px; color: #64748b; }

        /* Agent Chat styles */
        .agent-chat-area { height: 550px; background: white; border-radius: 20px; border: 1px solid #e2e8f0; display: flex; flex-direction: column; }
        .chat-scroll { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
        .chat-bubble { max-width: 90%; padding: 16px; border-radius: 16px; line-height: 1.6; font-size: 14px; }
        .chat-bubble.assistant { align-self: flex-start; background: #f8fafc; border: 1px solid #e2e8f0; color: #334155; width: 100%; }
        .bubble-content h1, .bubble-content h2, .bubble-content h3 { margin: 16px 0 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; color: #1e293b; }
        .bubble-content p { margin: 8px 0; }
        .bubble-content table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 12px; }
        .bubble-content th, .bubble-content td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; }
        .bubble-content th { background: #f1f5f9; }
        .agent-loading { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #64748b; }
        .spinner { width: 24px; height: 24px; border: 2px solid #e2e8f0; border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 16px; }
      `}</style>
    </div>
  );
}
