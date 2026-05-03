import { useState } from 'react';
import {
  X, GitCompare, AlertCircle, Clock, Hash, Wrench,
  ChevronRight, Info, RefreshCw,
} from 'lucide-react';
import { API_URL } from '../config';

export function McpComparisonPopup({ isOpen, onClose }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedQ, setExpandedQ] = useState(null);

  const runComparison = async () => {
    if (loading) return;
    setLoading(true);
    setError(null);
    setResults(null);
    setExpandedQ(null);
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 300000);
      const res = await fetch(`${API_URL}/research/mcp-comparison`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_judge: false }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server error ${res.status}`);
      }
      const data = await res.json();
      const allEmpty = (data.results || []).every(
        r => !r.non_mcp?.response_text && !r.mcp?.response_text
      );
      if (allEmpty) {
        throw new Error(
          'API quotas exhausted (Gemini: 20 req/day, Groq: 100K tokens/day). Try again after midnight PST (~12:30 PM IST).'
        );
      }
      setResults(data.results || []);
    } catch (err) {
      setError(
        err.name === 'AbortError'
          ? 'Request timed out after 5 minutes. API quotas may be exhausted — try again tomorrow.'
          : err.message
      );
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  // Compute summary stats
  const scored = (results || []).filter(r => r.non_mcp?.auto_metrics && r.mcp?.auto_metrics);
  const avg = (fn) => scored.length
    ? (scored.reduce((s, r) => s + (fn(r) || 0), 0) / scored.length).toFixed(2)
    : '—';
  const nmAvgNum = avg(r => r.non_mcp.auto_metrics.numeric_match_rate);
  const mcpAvgNum = avg(r => r.mcp.auto_metrics.numeric_match_rate);
  const nmAvgLat = scored.length
    ? (scored.reduce((s, r) => s + (r.non_mcp.latency_s || 0), 0) / scored.length).toFixed(1)
    : '—';
  const mcpAvgLat = scored.length
    ? (scored.reduce((s, r) => s + (r.mcp.latency_s || 0), 0) / scored.length).toFixed(1)
    : '—';
  const totalToolCalls = scored.reduce((s, r) => s + (r.mcp.tool_call_count || 0), 0);

  return (
    <div className="mcp-overlay">
      <div className="mcp-modal">
        {/* Header */}
        <div className="mcp-header">
          <div className="mcp-header-left">
            <div className="mcp-icon-wrap">
              <GitCompare size={20} className="mcp-header-icon" />
            </div>
            <div>
              <h2>MCP vs Non-MCP Comparison</h2>
              <p className="mcp-subtitle">Live tool-calling vs static context dump — 5 disaster response questions</p>
            </div>
          </div>
          <button className="mcp-close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="mcp-body">
          {/* Run button — always visible unless results shown */}
          {!results && !loading && (
            <div className="mcp-start">
              <GitCompare size={40} style={{ color: '#a855f7' }} />
              <p>Run the comparison to see how MCP tool-calling compares to a static context dump across 5 disaster-response questions.</p>
              <button className="mcp-run-btn" onClick={runComparison}>
                <GitCompare size={14} /> Run Comparison
              </button>
              <p className="mcp-hint">Takes 60–180s · Uses Gemini 2.5 Flash + Groq fallback</p>
            </div>
          )}

          {loading && (
            <div className="mcp-loading">
              <div className="mcp-spinner" />
              <p>Running 5 questions through both arms…</p>
              <p className="mcp-hint">MCP arm calls live tools; Non-MCP uses a pre-materialized dump.<br />This takes 60–180s depending on API latency.</p>
            </div>
          )}

          {error && !loading && (
            <div className="mcp-error-box">
              <AlertCircle size={18} />
              <div>
                <strong>Comparison failed</strong>
                <p>{error}</p>
              </div>
              <button className="mcp-retry-btn" onClick={runComparison}>
                <RefreshCw size={12} /> Retry
              </button>
            </div>
          )}

          {results && (
            <>
              {/* Summary strip */}
              <div className="mcp-summary-strip">
                <div className="mcp-sum-card nm">
                  <span className="mcp-mode-lbl">Non-MCP</span>
                  <div className="mcp-sum-stats">
                    <div><Clock size={11} /><span>{nmAvgLat}s avg latency</span></div>
                    <div><Hash size={11} /><span>{nmAvgNum} numeric accuracy</span></div>
                    <div><Wrench size={11} /><span>0 tool calls</span></div>
                  </div>
                </div>
                <div className="mcp-vs">VS</div>
                <div className="mcp-sum-card mcp">
                  <span className="mcp-mode-lbl">MCP</span>
                  <div className="mcp-sum-stats">
                    <div><Clock size={11} /><span>{mcpAvgLat}s avg latency</span></div>
                    <div><Hash size={11} /><span>{mcpAvgNum} numeric accuracy</span></div>
                    <div><Wrench size={11} /><span>{totalToolCalls} total tool calls</span></div>
                  </div>
                </div>
                <button className="mcp-rerun-btn" onClick={runComparison}>
                  <RefreshCw size={12} /> Re-run
                </button>
              </div>

              {/* Per-question cards */}
              <div className="mcp-questions">
                {results.map((r, i) => {
                  const nm = r.non_mcp || {};
                  const mc = r.mcp || {};
                  const open = expandedQ === i;

                  // Multi-metric winner logic
                  const nmNum = nm.auto_metrics?.numeric_match_rate || 0;
                  const mcNum = mc.auto_metrics?.numeric_match_rate || 0;
                  const nmShelter = nm.auto_metrics?.shelter_name_match_count || 0;
                  const mcShelter = mc.auto_metrics?.shelter_name_match_count || 0;
                  const nmHas = nm.response_text ? 1 : 0;
                  const mcHas = mc.response_text ? 1 : 0;
                  const nmScore = nmNum * 3 + nmShelter * 2 + nmHas;
                  const mcScore = mcNum * 3 + mcShelter * 2 + mcHas + ((mc.tool_call_count || 0) > 0 ? 0.5 : 0);
                  const bothEmpty = !nm.response_text && !mc.response_text;
                  const isTie = bothEmpty || Math.abs(nmScore - mcScore) < 0.05;
                  const nmWins = !bothEmpty && nmScore > mcScore + 0.05;

                  return (
                    <div key={i} className="mcp-q-card">
                      <div className="mcp-q-header" onClick={() => setExpandedQ(open ? null : i)}>
                        <div className="mcp-q-left">
                          <span className="mcp-q-num">Q{i + 1}</span>
                          <span className="mcp-q-text">{r.question}</span>
                        </div>
                        <div className="mcp-q-right">
                          {bothEmpty
                            ? <span className="mcp-badge inconclusive">No data</span>
                            : isTie
                              ? <span className="mcp-badge tie">Tie</span>
                              : nmWins
                                ? <span className="mcp-badge nm-wins">Non-MCP wins</span>
                                : <span className="mcp-badge mcp-wins">MCP wins</span>
                          }
                          <ChevronRight size={14} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: '0.2s', color: '#94a3b8' }} />
                        </div>
                      </div>

                      {/* Metrics row */}
                      <div className="mcp-metrics-row">
                        {[
                          { label: 'Provider', nm: nm.provider || '—', mc: mc.provider || '—' },
                          { label: 'Latency', nm: nm.latency_s != null ? `${nm.latency_s}s` : '—', mc: mc.latency_s != null ? `${mc.latency_s}s` : '—' },
                          { label: 'Words', nm: nm.response_words ?? '—', mc: mc.response_words ?? '—' },
                          { label: 'Numeric Acc.', nm: nm.auto_metrics?.numeric_match_rate?.toFixed(2) ?? '—', mc: mc.auto_metrics?.numeric_match_rate?.toFixed(2) ?? '—' },
                          { label: 'Tool Calls', nm: '0', mc: mc.tool_call_count ?? '—' },
                        ].map(cell => (
                          <div key={cell.label} className="mcp-metric-cell">
                            <span className="mcp-metric-lbl">{cell.label}</span>
                            <span className="mcp-metric-nm">{cell.nm}</span>
                            <span className="mcp-metric-sep">/</span>
                            <span className="mcp-metric-mcp">{cell.mc}</span>
                          </div>
                        ))}
                      </div>

                      {/* Expanded: tool trace + side-by-side responses */}
                      {open && (
                        <div className="mcp-expanded">
                          {mc.tool_calls?.length > 0 && (
                            <div className="mcp-tool-trace">
                              <span className="mcp-trace-lbl">Tools called:</span>
                              {mc.tool_calls.map((t, j) => (
                                <span key={j} className="mcp-tool-chip">{t.name}</span>
                              ))}
                            </div>
                          )}
                          <div className="mcp-responses">
                            <div className="mcp-resp-col nm">
                              <div className="mcp-resp-header">Non-MCP Response</div>
                              <div className="mcp-resp-body">
                                {nm.response_text
                                  ? nm.response_text.slice(0, 500) + (nm.response_text.length > 500 ? '…' : '')
                                  : <em style={{ color: '#94a3b8' }}>No response (quota exhausted)</em>}
                              </div>
                            </div>
                            <div className="mcp-resp-col mcp">
                              <div className="mcp-resp-header">MCP Response</div>
                              <div className="mcp-resp-body">
                                {mc.response_text
                                  ? mc.response_text.slice(0, 500) + (mc.response_text.length > 500 ? '…' : '')
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
                  <strong>Non-MCP</strong>: static ~7,600-word dump, no tool calls.
                  {' '}<strong>MCP</strong>: minimal seed (~80 words) + live tool calls (14 tools available).
                  {' '}Winner = weighted score: numeric accuracy ×3, shelter name matches ×2, has response ×1, tool calls bonus.
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      <style>{`
        .mcp-overlay {
          position: fixed;
          inset: 0;
          background: rgba(15, 23, 42, 0.45);
          backdrop-filter: blur(8px);
          z-index: 9999;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: mcpFadeIn 0.25s ease;
        }
        @keyframes mcpFadeIn { from { opacity: 0; } to { opacity: 1; } }

        .mcp-modal {
          width: 960px;
          max-width: 96vw;
          max-height: 88vh;
          background: #fff;
          border-radius: 24px;
          box-shadow: 0 25px 60px -12px rgba(0,0,0,0.3);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .mcp-header {
          padding: 20px 28px;
          background: white;
          border-bottom: 1px solid #f1f5f9;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-shrink: 0;
        }

        .mcp-header-left {
          display: flex;
          gap: 14px;
          align-items: center;
        }

        .mcp-icon-wrap {
          width: 40px;
          height: 40px;
          background: linear-gradient(135deg, #f3e8ff, #ede9fe);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .mcp-header-icon { color: #a855f7; }

        .mcp-header h2 {
          margin: 0;
          font-size: 17px;
          font-weight: 800;
          color: #1e293b;
        }

        .mcp-subtitle {
          margin: 2px 0 0;
          font-size: 11px;
          color: #64748b;
        }

        .mcp-close-btn {
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
        .mcp-close-btn:hover { background: #fee2e2; color: #ef4444; }

        .mcp-body {
          flex: 1;
          overflow-y: auto;
          padding: 24px 28px;
          background: #f8fafc;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        /* Start state */
        .mcp-start {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 14px;
          padding: 60px 20px;
          text-align: center;
          color: #64748b;
          font-size: 13px;
        }
        .mcp-start p { margin: 0; max-width: 480px; }

        .mcp-run-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 11px 24px;
          background: linear-gradient(135deg, #a855f7, #7c3aed);
          color: white;
          border: none;
          border-radius: 12px;
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          box-shadow: 0 4px 12px rgba(168,85,247,0.35);
          transition: opacity 0.2s;
        }
        .mcp-run-btn:hover { opacity: 0.88; }

        .mcp-hint {
          font-size: 10.5px;
          color: #94a3b8;
          margin: 0;
          text-align: center;
        }

        /* Loading */
        .mcp-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 14px;
          padding: 60px 20px;
          color: #64748b;
          font-size: 13px;
          text-align: center;
        }
        .mcp-spinner {
          width: 36px;
          height: 36px;
          border: 3px solid #f1f5f9;
          border-top-color: #a855f7;
          border-radius: 50%;
          animation: mcpSpin 1s linear infinite;
        }
        @keyframes mcpSpin { to { transform: rotate(360deg); } }

        /* Error */
        .mcp-error-box {
          display: flex;
          gap: 12px;
          align-items: flex-start;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 14px;
          padding: 16px;
          color: #991b1b;
          font-size: 13px;
        }
        .mcp-error-box p { margin: 4px 0 0; font-size: 11px; color: #b91c1c; }
        .mcp-retry-btn {
          margin-left: auto;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          background: #fee2e2;
          border: 1px solid #fca5a5;
          border-radius: 8px;
          font-size: 11px;
          font-weight: 700;
          color: #b91c1c;
          cursor: pointer;
        }

        /* Summary strip */
        .mcp-summary-strip {
          display: flex;
          align-items: center;
          gap: 12px;
          background: white;
          border-radius: 16px;
          padding: 14px 18px;
          border: 1px solid #e2e8f0;
          flex-shrink: 0;
        }
        .mcp-sum-card {
          flex: 1;
          padding: 10px 14px;
          border-radius: 12px;
        }
        .mcp-sum-card.nm { background: #eff6ff; border: 1px solid #bfdbfe; }
        .mcp-sum-card.mcp { background: #f5f3ff; border: 1px solid #ddd6fe; }
        .mcp-mode-lbl {
          display: block;
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          margin-bottom: 7px;
          color: #475569;
        }
        .mcp-sum-stats { display: flex; flex-direction: column; gap: 4px; }
        .mcp-sum-stats > div {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11.5px;
          color: #334155;
          font-weight: 500;
        }
        .mcp-vs {
          font-size: 13px;
          font-weight: 900;
          color: #cbd5e1;
          padding: 0 4px;
        }
        .mcp-rerun-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 7px 14px;
          background: #f5f3ff;
          border: 1px solid #ddd6fe;
          border-radius: 10px;
          font-size: 11px;
          font-weight: 700;
          color: #7c3aed;
          cursor: pointer;
          white-space: nowrap;
          transition: background 0.15s;
        }
        .mcp-rerun-btn:hover { background: #ede9fe; }

        /* Question cards */
        .mcp-questions { display: flex; flex-direction: column; gap: 10px; }

        .mcp-q-card {
          background: white;
          border-radius: 14px;
          border: 1px solid #e2e8f0;
          overflow: hidden;
        }

        .mcp-q-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 11px 15px;
          cursor: pointer;
          gap: 12px;
        }
        .mcp-q-header:hover { background: #f8fafc; }

        .mcp-q-left {
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
        .mcp-q-right {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-shrink: 0;
        }

        .mcp-badge {
          font-size: 10px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
        }
        .mcp-badge.mcp-wins { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
        .mcp-badge.nm-wins  { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
        .mcp-badge.tie      { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
        .mcp-badge.inconclusive { background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; }

        .mcp-metrics-row {
          display: flex;
          border-top: 1px solid #f1f5f9;
          background: #fafafa;
        }
        .mcp-metric-cell {
          flex: 1;
          padding: 7px 10px;
          display: flex;
          flex-direction: column;
          align-items: center;
          border-right: 1px solid #f1f5f9;
          gap: 1px;
        }
        .mcp-metric-cell:last-child { border-right: none; }
        .mcp-metric-lbl {
          font-size: 8.5px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #94a3b8;
        }
        .mcp-metric-nm  { font-size: 11px; font-weight: 600; color: #3b82f6; }
        .mcp-metric-mcp { font-size: 11px; font-weight: 600; color: #a855f7; }
        .mcp-metric-sep { font-size: 9px; color: #e2e8f0; }

        /* Expanded */
        .mcp-expanded {
          padding: 12px 15px;
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
        .mcp-trace-lbl {
          font-size: 9.5px;
          font-weight: 700;
          color: #64748b;
          text-transform: uppercase;
        }
        .mcp-tool-chip {
          font-size: 10px;
          font-weight: 600;
          background: #f5f3ff;
          color: #6d28d9;
          border: 1px solid #ddd6fe;
          padding: 2px 8px;
          border-radius: 6px;
        }
        .mcp-responses {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }
        .mcp-resp-col {
          border-radius: 10px;
          overflow: hidden;
          border: 1px solid #e2e8f0;
        }
        .mcp-resp-col.nm  { border-color: #bfdbfe; }
        .mcp-resp-col.mcp { border-color: #ddd6fe; }
        .mcp-resp-header {
          font-size: 9.5px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 6px 11px;
          border-bottom: 1px solid #e2e8f0;
        }
        .mcp-resp-col.nm  .mcp-resp-header { background: #eff6ff; color: #1e40af; border-color: #bfdbfe; }
        .mcp-resp-col.mcp .mcp-resp-header { background: #f5f3ff; color: #6d28d9; border-color: #ddd6fe; }
        .mcp-resp-body {
          padding: 10px 11px;
          font-size: 11px;
          line-height: 1.6;
          color: #334155;
          background: white;
          white-space: pre-wrap;
          max-height: 220px;
          overflow-y: auto;
        }

        /* Footer */
        .mcp-footer-note {
          background: #f5f3ff;
          border-radius: 12px;
          padding: 11px 14px;
          display: flex;
          gap: 8px;
          align-items: flex-start;
          font-size: 10.5px;
          color: #5b21b6;
          border: 1px solid #ddd6fe;
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
}
