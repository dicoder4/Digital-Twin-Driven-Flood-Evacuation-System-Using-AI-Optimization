/**
 * ChatbotPanel.jsx — Embedded side-panel version of SimHelper
 *
 * Renders as a 380px right panel alongside the map (Layout B).
 * Differences from ChatbotPage.jsx:
 *  - No full-page layout, no back button — it's a panel
 *  - onAutoLoadRegion(hobli): tells App.jsx to load the region on the map
 *  - onAutoRunSim(hobli, rainfall, algo): tells App.jsx to start the simulation
 *  - simIsRunning / simProgress: shows a live sim progress bar in the panel
 *  - simResult / evacuationPlan: passed in after sim completes for route insights
 *  - onClose: close button (X) top-right
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import {
    Send, Bot, User, RefreshCw, Loader, X,
    Zap, CloudRain, Waves, Map, ChevronDown, ChevronUp,
    Activity, Users, Shield, TrendingUp, CheckCircle
} from 'lucide-react';
import { API_URL } from '../config';
import './ChatbotPanel.css';

const SESSION_ID = `simhelper-${Math.random().toString(36).slice(2, 10)}`;
const SIM_DONE_PREFIX = '\x00SIM_DONE:';
const SIM_META_PREFIX = '\x00SIM_META:';

// ── Markdown renderer (identical to ChatbotPage) ──────────────────────────────
function renderMarkdown(text) {
    if (!text) return null;
    const lines = text.split('\n');
    const elements = [];
    let tableRows = [], inTable = false;
    let listItems = [], inList = false;
    let key = 0;

    const flushTable = () => {
        if (tableRows.length < 2) {
            elements.push(<p key={key++} className="cp-md-p">{tableRows.join('\n')}</p>);
        } else {
            const headers = tableRows[0].split('|').filter(c => c.trim());
            const body = tableRows.slice(2).map(r => r.split('|').filter(c => c.trim()));
            elements.push(
                <table key={key++} className="cp-md-table">
                    <thead><tr>{headers.map((h, i) => <th key={i}>{inlineRender(h.trim())}</th>)}</tr></thead>
                    <tbody>{body.map((row, ri) => (
                        <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{inlineRender(cell.trim())}</td>)}</tr>
                    ))}</tbody>
                </table>
            );
        }
        tableRows = []; inTable = false;
    };

    const flushList = () => {
        elements.push(<ul key={key++} className="cp-md-list">{listItems.map((li, i) => <li key={i}>{inlineRender(li)}</li>)}</ul>);
        listItems = []; inList = false;
    };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.trim().startsWith('|')) { if (inList) flushList(); inTable = true; tableRows.push(line.trim()); continue; }
        if (inTable && !line.trim().startsWith('|')) flushTable();
        if (line.startsWith('```')) {
            if (inList) flushList();
            const codeLines = []; i++;
            while (i < lines.length && !lines[i].startsWith('```')) { codeLines.push(lines[i]); i++; }
            elements.push(<pre key={key++} className="cp-md-pre"><code>{codeLines.join('\n')}</code></pre>);
            continue;
        }
        if (line.startsWith('## ')) { if (inList) flushList(); elements.push(<h2 key={key++} className="cp-md-h2">{inlineRender(line.slice(3))}</h2>); continue; }
        if (line.startsWith('### ')) { if (inList) flushList(); elements.push(<h3 key={key++} className="cp-md-h3">{inlineRender(line.slice(4))}</h3>); continue; }
        if (line.startsWith('> ')) { if (inList) flushList(); elements.push(<blockquote key={key++} className="cp-md-quote">{inlineRender(line.slice(2))}</blockquote>); continue; }
        if (line.trim() === '---') { if (inList) flushList(); elements.push(<hr key={key++} className="cp-md-hr" />); continue; }
        if (line.match(/^[-*]\s/) || line.match(/^\d+\.\s/)) {
            inList = true;
            listItems.push(line.replace(/^[-*]\s/, '').replace(/^\d+\.\s/, ''));
            continue;
        }
        if (inList) flushList();
        if (line.trim() === '') { elements.push(<div key={key++} className="cp-md-spacer" />); continue; }
        elements.push(<p key={key++} className="cp-md-p">{inlineRender(line)}</p>);
    }
    if (inTable) flushTable();
    if (inList) flushList();
    return elements;
}

function inlineRender(text) {
    if (!text) return null;
    const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g);
    return parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith('_') && p.endsWith('_') && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
        if (p.startsWith('`') && p.endsWith('`') && p.length > 2) return <code key={i} className="cp-md-code">{p.slice(1, -1)}</code>;
        return p;
    });
}

// ── Sim progress banner (shown while map is running the sim) ──────────────────
function SimProgressBanner({ progress }) {
    return (
        <div className="cp-sim-banner">
            <Loader size={13} className="spin cp-sim-banner-icon" />
            <div className="cp-sim-banner-text">
                <span className="cp-sim-banner-label">Running on map…</span>
                {progress && <span className="cp-sim-banner-step">{progress}</span>}
            </div>
        </div>
    );
}

// ── SimResultPanel (inline results after sim) ─────────────────────────────────
function SimResultPanel({ meta }) {
    const [expanded, setExpanded] = useState(true);
    const { hobli, rainfall_mm, summary = {}, shelters = [] } = meta;
    const evacuated = summary.total_evacuated ?? 0;
    const atRisk = summary.total_at_risk_initial ?? 0;
    const stillRisk = summary.total_at_risk_remaining ?? 0;
    const successPct = summary.success_rate_pct ?? 0;
    const execTime = summary.ga_execution_time ?? 'N/A';
    const algorithm = summary.algorithm ?? 'GA';
    const successColor = successPct >= 80 ? '#16a34a' : successPct >= 50 ? '#d97706' : '#dc2626';

    return (
        <div className="cp-result-panel">
            <div className="cp-result-header" onClick={() => setExpanded(e => !e)}>
                <div className="cp-result-header-left">
                    <Activity size={13} style={{ color: '#2563eb', flexShrink: 0 }} />
                    <div>
                        <div className="cp-result-title">Results — {hobli}</div>
                        <div className="cp-result-sub">{rainfall_mm} mm · {algorithm} · {execTime}s</div>
                    </div>
                </div>
                <div className="cp-result-header-right">
                    <span className="cp-result-rate" style={{ color: successColor }}>{successPct}%</span>
                    <button className="cp-result-expand-btn">
                        {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                    </button>
                </div>
            </div>
            {expanded && (
                <div className="cp-result-body">
                    <div className="cp-metrics-row">
                        {[
                            { icon: <Users size={12} />, val: atRisk.toLocaleString(), label: 'At Risk', cls: 'blue' },
                            { icon: <Shield size={12} />, val: evacuated.toLocaleString(), label: 'Evacuated', cls: 'green' },
                            { icon: <Activity size={12} />, val: stillRisk.toLocaleString(), label: 'Still at Risk', cls: 'red' },
                            { icon: <TrendingUp size={12} />, val: `${successPct}%`, label: 'Success', cls: 'purple', style: { color: successColor } },
                        ].map((m, i) => (
                            <div key={i} className={`cp-metric-card cp-metric--${m.cls}`}>
                                {m.icon}
                                <div className="cp-metric-val" style={m.style}>{m.val}</div>
                                <div className="cp-metric-label">{m.label}</div>
                            </div>
                        ))}
                    </div>
                    {shelters.length > 0 && (
                        <div className="cp-shelters">
                            <div className="cp-shelters-title">🏠 Shelter Occupancy</div>
                            {shelters.slice(0, 5).map((s, i) => {
                                const pct = Math.min(100, s.occupancy_pct ?? 0);
                                const barColor = pct > 90 ? '#dc2626' : pct > 70 ? '#d97706' : '#16a34a';
                                return (
                                    <div key={i} className="cp-shelter-row">
                                        <div className="cp-shelter-name">{(s.name || s.id || `Shelter ${i + 1}`).slice(0, 18)}</div>
                                        <div className="cp-shelter-bar-wrap">
                                            <div className="cp-shelter-bar-fill" style={{ width: `${pct}%`, background: barColor }} />
                                        </div>
                                        <div className="cp-shelter-pct">{pct}%</div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                    <div className="cp-result-map-hint">
                        <CheckCircle size={12} style={{ color: '#16a34a', flexShrink: 0 }} />
                        <span>Routes &amp; flood zones are live on the map →</span>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Quick actions ─────────────────────────────────────────────────────────────
const QUICK_ACTIONS = [
    { icon: <Waves size={11} />, label: 'Sarjapura severe', msg: 'simulate sarjapura historical severe' },
    { icon: <Waves size={11} />, label: 'Marathahalli moderate', msg: 'simulate marathahalli historical moderate' },
    { icon: <CloudRain size={11} />, label: 'Yelahanka realtime', msg: 'simulate yelahanka realtime' },
    { icon: <Zap size={11} />, label: 'What is a hobli?', msg: 'What is a hobli in Karnataka?' },
];

// ── Main component ────────────────────────────────────────────────────────────
export default function ChatbotPanel({
    onClose,
    simIsRunning = false,
    simProgress = '',
    simResult = null,
    evacuationPlan = [],
}) {
    const [messages, setMessages] = useState([{
        id: 0, role: 'bot', streaming: false,
        text: `## 🤖 SimHelper — Flood AI\n\nI run simulations directly on the **map** — just tell me the hobli and scenario.\n\n💡 **Quick tip:** Type \`simulate <hobli> historical moderate\` to run immediately.\n\n_Pick an action below or type a request._`,
    }]);
    const [input, setInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [simMeta, setSimMeta] = useState(null);
    const bottomRef = useRef(null);
    const abortRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
    useEffect(() => { inputRef.current?.focus(); }, []);

    // If App.jsx passes in a new simResult (sim completed on dashboard), show it
    useEffect(() => {
        if (simResult && !simIsRunning) {
            // Merge into simMeta for display if we don't already have a meta from the pipeline
            if (!simMeta) {
                setSimMeta({
                    hobli: simResult.hobli ?? 'Unknown',
                    rainfall_mm: simResult.rainfall ?? 0,
                    summary: simResult.summary ?? {},
                    shelters: simResult.shelters ?? [],
                });
            }
        }
    }, [simResult, simIsRunning]);

    const appendToLast = useCallback((chunk) => {
        setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last?.role === 'bot' && last.streaming) {
                copy[copy.length - 1] = { ...last, text: last.text + chunk };
            }
            return copy;
        });
    }, []);

    const send = useCallback(async (msgText) => {
        const text = (msgText || input).trim();
        if (!text || streaming) return;
        setInput('');
        setStreaming(true);
        setSimMeta(null);

        setMessages(prev => [...prev, { id: Date.now(), role: 'user', text, streaming: false }]);
        const botId = Date.now() + 1;
        setMessages(prev => [...prev, { id: botId, role: 'bot', text: '', streaming: true }]);

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const res = await fetch(`${API_URL}/genai/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, session_id: SESSION_ID }),
                signal: controller.signal,
            });
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() ?? '';

                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const data = line.slice(5).trim();
                    if (data === '[DONE]') break;
                    try {
                        const parsed = JSON.parse(data);
                        if (!parsed.text) continue;
                        let visible = parsed.text;

                        // ── SIM_DONE token ──
                        if (visible.includes(SIM_DONE_PREFIX)) {
                            visible = visible.split(SIM_DONE_PREFIX)[0].trim();
                        }

                        // ── SIM_META token ──
                        if (visible.includes(SIM_META_PREFIX)) {
                            const b64 = visible.split(SIM_META_PREFIX)[1]?.split('\n')[0] ?? '';
                            if (b64) {
                                try { setSimMeta(JSON.parse(atob(b64))); } catch { /* ignore */ }
                            }
                            visible = visible.split(SIM_META_PREFIX)[0].trim();
                        }

                        if (visible) appendToLast(visible);
                    } catch { /* skip malformed */ }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') appendToLast(`\n\n❌ **Error:** ${err.message}`);
        } finally {
            setMessages(prev => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last?.id === botId) copy[copy.length - 1] = { ...last, streaming: false };
                return copy;
            });
            setStreaming(false);
            abortRef.current = null;
            inputRef.current?.focus();
        }
    }, [input, streaming, appendToLast]);

    const handleReset = async () => {
        if (streaming) abortRef.current?.abort();
        await fetch(`${API_URL}/genai/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '', session_id: SESSION_ID }),
        }).catch(() => { });
        setMessages([{ id: Date.now(), role: 'bot', streaming: false, text: '🔄 **Session reset.** How can I help?' }]);
        setStreaming(false);
        setSimMeta(null);
    };

    const handleKey = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    };

    return (
        <div className="cp-panel">
            {/* ── Header ── */}
            <div className="cp-header">
                <div className="cp-header-left">
                    <div className="cp-header-avatar"><Bot size={15} /></div>
                    <div>
                        <div className="cp-header-title">SimHelper</div>
                        <div className="cp-header-sub">AI Flood Assistant · Bengaluru</div>
                    </div>
                </div>
                <div className="cp-header-actions">
                    <button className="cp-icon-btn" onClick={handleReset} title="Reset conversation">
                        <RefreshCw size={13} />
                    </button>
                    <button className="cp-icon-btn cp-close-btn" onClick={onClose} title="Close panel">
                        <X size={14} />
                    </button>
                </div>
            </div>

            {/* ── Sim progress banner ── */}
            {simIsRunning && <SimProgressBanner progress={simProgress} />}

            {/* ── Messages ── */}
            <div className="cp-messages">
                {messages.map((msg) => (
                    <div key={msg.id} className={`cp-msg cp-msg--${msg.role}`}>
                        <div className={`cp-avatar cp-avatar--${msg.role}`}>
                            {msg.role === 'bot' ? <Bot size={12} /> : <User size={12} />}
                        </div>
                        <div className={`cp-bubble cp-bubble--${msg.role}`}>
                            {msg.role === 'bot'
                                ? <div className="cp-md">{renderMarkdown(msg.text)}</div>
                                : <span>{msg.text}</span>
                            }
                            {msg.streaming && msg.text === '' && (
                                <span className="cp-typing">
                                    <span className="cp-dot" /><span className="cp-dot" /><span className="cp-dot" />
                                </span>
                            )}
                            {msg.streaming && msg.text !== '' && <span className="cp-cursor">▋</span>}
                        </div>
                    </div>
                ))}

                {/* Inline sim result panel */}
                {simMeta && !streaming && <SimResultPanel meta={simMeta} />}

                <div ref={bottomRef} />
            </div>

            {/* ── Quick actions ── */}
            {messages.length <= 2 && !streaming && (
                <div className="cp-quick-actions">
                    {QUICK_ACTIONS.map(qa => (
                        <button key={qa.label} className="cp-chip" onClick={() => send(qa.msg)}>
                            {qa.icon}{qa.label}
                        </button>
                    ))}
                </div>
            )}

            {/* ── Input ── */}
            <div className="cp-input-bar">
                <textarea
                    ref={inputRef}
                    className="cp-input"
                    placeholder="e.g. simulate sarjapura historical severe…"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKey}
                    rows={1}
                    disabled={streaming}
                />
                <button
                    className={`cp-send-btn ${(!input.trim() || streaming) ? 'cp-send-btn--disabled' : ''}`}
                    onClick={() => send()}
                    disabled={!input.trim() || streaming}
                >
                    {streaming ? <Loader size={14} className="spin" /> : <Send size={14} />}
                </button>
            </div>
            <div className="cp-footer-note">
                SimHelper · Ollama + Open-Meteo + IMD records
            </div>
        </div>
    );
}
