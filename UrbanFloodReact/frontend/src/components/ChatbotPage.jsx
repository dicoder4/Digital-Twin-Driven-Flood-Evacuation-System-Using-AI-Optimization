/**
 * ChatbotPage.jsx — Flood AI GenAI Chat
 * Full-page chat UI for the MCP pipeline (/genai/chat SSE endpoint).
 *
 * After simulation completes, renders an inline SimResultPanel showing:
 *  • Key metrics card
 *  • Shelter occupancy bars
 *  • "View Map & Routes" button that navigates to the dashboard map
 *    with the correct hobli + rainfall pre-loaded
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import {
    ArrowLeft, Send, Bot, User, RefreshCw, Loader,
    Zap, CloudRain, Waves, Map, ChevronDown, ChevronUp,
    Activity, Users, Shield, TrendingUp
} from 'lucide-react';
import { API_URL } from '../config';
import './ChatbotPage.css';

// Internal session ID
const SESSION_ID = `flood-ai-${Math.random().toString(36).slice(2, 10)}`;

// Control tokens emitted by the backend pipeline
const SIM_DONE_PREFIX = '\x00SIM_DONE:';
const SIM_META_PREFIX = '\x00SIM_META:';

// ── Simple markdown renderer ──────────────────────────────────────────────────
function renderMarkdown(text) {
    if (!text) return null;
    const lines = text.split('\n');
    const elements = [];
    let tableRows = [], inTable = false;
    let listItems = [], inList = false;
    let key = 0;

    const flushTable = () => {
        if (tableRows.length < 2) {
            elements.push(<p key={key++} className="chat-md-p">{tableRows.join('\n')}</p>);
        } else {
            const headers = tableRows[0].split('|').filter(c => c.trim());
            const body = tableRows.slice(2).map(r => r.split('|').filter(c => c.trim()));
            elements.push(
                <table key={key++} className="chat-md-table">
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
        elements.push(<ul key={key++} className="chat-md-list">{listItems.map((li, i) => <li key={i}>{inlineRender(li)}</li>)}</ul>);
        listItems = []; inList = false;
    };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        if (line.trim().startsWith('|')) {
            if (inList) flushList();
            inTable = true; tableRows.push(line.trim()); continue;
        }
        if (inTable && !line.trim().startsWith('|')) flushTable();

        if (line.startsWith('```')) {
            if (inList) flushList();
            const codeLines = [];
            i++;
            while (i < lines.length && !lines[i].startsWith('```')) { codeLines.push(lines[i]); i++; }
            elements.push(<pre key={key++} className="chat-md-pre"><code>{codeLines.join('\n')}</code></pre>);
            continue;
        }

        if (line.startsWith('## ')) { if (inList) flushList(); elements.push(<h2 key={key++} className="chat-md-h2">{inlineRender(line.slice(3))}</h2>); continue; }
        if (line.startsWith('### ')) { if (inList) flushList(); elements.push(<h3 key={key++} className="chat-md-h3">{inlineRender(line.slice(4))}</h3>); continue; }
        if (line.startsWith('> ')) { if (inList) flushList(); elements.push(<blockquote key={key++} className="chat-md-quote">{inlineRender(line.slice(2))}</blockquote>); continue; }
        if (line.trim() === '---') { if (inList) flushList(); elements.push(<hr key={key++} className="chat-md-hr" />); continue; }

        if (line.match(/^[-*]\s/) || line.match(/^\d+\.\s/)) {
            inList = true;
            listItems.push(line.replace(/^[-*]\s/, '').replace(/^\d+\.\s/, ''));
            continue;
        }
        if (inList) flushList();
        if (line.trim() === '') { elements.push(<div key={key++} className="chat-md-spacer" />); continue; }
        elements.push(<p key={key++} className="chat-md-p">{inlineRender(line)}</p>);
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
        if (p.startsWith('`') && p.endsWith('`') && p.length > 2) return <code key={i} className="chat-md-code">{p.slice(1, -1)}</code>;
        return p;
    });
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function TypingIndicator() {
    return (
        <div className="chat-msg chat-msg--bot">
            <div className="chat-avatar chat-avatar--bot"><Bot size={14} /></div>
            <div className="chat-bubble chat-bubble--bot chat-bubble--typing">
                <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
            </div>
        </div>
    );
}

// ── SimResultPanel ─────────────────────────────────────────────────────────────
function SimResultPanel({ meta, onViewMap }) {
    const [expanded, setExpanded] = useState(true);
    const { hobli, rainfall_mm, summary = {}, shelters = [] } = meta;

    const evacuated = summary.total_evacuated ?? 0;
    const atRisk = summary.total_at_risk_initial ?? 0;
    const stillRisk = summary.total_at_risk_remaining ?? 0;
    const successPct = summary.success_rate_pct ?? 0;
    const execTime = summary.ga_execution_time ?? 'N/A';
    const algorithm = summary.algorithm ?? 'GA';

    const successColor = successPct >= 80
        ? '#16a34a' : successPct >= 50 ? '#d97706' : '#dc2626';

    return (
        <div className="sim-result-panel">
            {/* Header bar */}
            <div className="sim-result-header" onClick={() => setExpanded(e => !e)}>
                <div className="sim-result-header-left">
                    <Activity size={15} className="sim-result-icon" />
                    <div>
                        <div className="sim-result-title">Simulation Results — {hobli}</div>
                        <div className="sim-result-sub">{rainfall_mm} mm · {algorithm} · {execTime}s</div>
                    </div>
                </div>
                <div className="sim-result-header-right">
                    <span className="sim-result-rate" style={{ color: successColor }}>
                        {successPct}% success
                    </span>
                    <button className="sim-result-expand-btn">
                        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                </div>
            </div>

            {expanded && (
                <div className="sim-result-body">
                    {/* Key metrics row */}
                    <div className="sim-metrics-row">
                        <div className="sim-metric-card sim-metric--blue">
                            <Users size={14} />
                            <div className="sim-metric-val">{atRisk.toLocaleString()}</div>
                            <div className="sim-metric-label">At Risk</div>
                        </div>
                        <div className="sim-metric-card sim-metric--green">
                            <Shield size={14} />
                            <div className="sim-metric-val">{evacuated.toLocaleString()}</div>
                            <div className="sim-metric-label">Evacuated</div>
                        </div>
                        <div className="sim-metric-card sim-metric--red">
                            <Activity size={14} />
                            <div className="sim-metric-val">{stillRisk.toLocaleString()}</div>
                            <div className="sim-metric-label">Still at Risk</div>
                        </div>
                        <div className="sim-metric-card sim-metric--purple">
                            <TrendingUp size={14} />
                            <div className="sim-metric-val" style={{ color: successColor }}>{successPct}%</div>
                            <div className="sim-metric-label">Success Rate</div>
                        </div>
                    </div>

                    {/* Shelter occupancy bars */}
                    {shelters.length > 0 && (
                        <div className="sim-shelters">
                            <div className="sim-shelters-title">🏠 Shelter Occupancy</div>
                            <div className="sim-shelters-list">
                                {shelters.slice(0, 6).map((s, i) => {
                                    const pct = Math.min(100, s.occupancy_pct ?? 0);
                                    const barColor = pct > 90 ? '#dc2626' : pct > 70 ? '#d97706' : '#16a34a';
                                    return (
                                        <div key={i} className="sim-shelter-row">
                                            <div className="sim-shelter-name">
                                                {(s.name || s.id || `Shelter ${i + 1}`).slice(0, 22)}
                                            </div>
                                            <div className="sim-shelter-bar-wrap">
                                                <div
                                                    className="sim-shelter-bar-fill"
                                                    style={{ width: `${pct}%`, background: barColor }}
                                                />
                                            </div>
                                            <div className="sim-shelter-pct">{pct}%</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Action buttons */}
                    <div className="sim-result-actions">
                        <button className="sim-view-map-btn" onClick={onViewMap}>
                            <Map size={14} />
                            View Map & Evacuation Routes →
                        </button>
                        <div className="sim-result-hint">
                            The map shows flood zones, shelter locations, and optimised evacuation routes
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Quick-action chips ────────────────────────────────────────────────────────
const QUICK_ACTIONS = [
    { icon: <Waves size={12} />, label: 'Simulate Sarjapura', msg: 'Run flood simulation for Sarjapura' },
    { icon: <Waves size={12} />, label: 'Simulate Marathahalli', msg: 'Run flood simulation for Marathahalli' },
    { icon: <CloudRain size={12} />, label: 'Realtime Rainfall', msg: 'What is the current rainfall in Yelahanka?' },
    { icon: <Zap size={12} />, label: 'What is a hobli?', msg: 'What is a hobli in Karnataka?' },
];

// ── Main Component ────────────────────────────────────────────────────────────
export default function ChatbotPage({ onBack, onSimulationDone }) {
    const [messages, setMessages] = useState([
        {
            id: 0, role: 'bot', streaming: false,
            text: `## 👋 SimHelper — Flood AI Assistant\n\nI can help you:\n- 🌊 **Trigger flood simulations** for any Bengaluru hobli\n- 🌧️ **Fetch real-time or historical rainfall** data\n- 🏃 **Explain evacuation results**, shelter occupancy, and routes\n\n💡 **Quick tip:** Type \`simulate <hobli> historical moderate\` to run immediately — no prompts needed.\n\n_Type a request or pick a quick action below._`,
        },
    ]);
    const [input, setInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [simMeta, setSimMeta] = useState(null); // full summary from SIM_META token
    const [lastSimInfo, setLastSimInfo] = useState(null); // {hobli, rainfall} for legacy fallback
    const bottomRef = useRef(null);
    const abortRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
    useEffect(() => { inputRef.current?.focus(); }, []);

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
        setLastSimInfo(null);

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

                        // ── SIM_DONE control token ─────────────────────────
                        if (visible.includes(SIM_DONE_PREFIX)) {
                            const token = visible.split(SIM_DONE_PREFIX)[1]?.split('\n')[0] ?? '';
                            const [hobli, rainfall] = token.split(':');
                            if (hobli) {
                                setLastSimInfo({ hobli, rainfall: parseFloat(rainfall) || 0 });
                            }
                            visible = visible.replace(new RegExp(`${SIM_DONE_PREFIX}[^\n]*`), '').trim();
                        }

                        // ── SIM_META control token ─────────────────────────
                        if (visible.includes(SIM_META_PREFIX)) {
                            const b64 = visible.split(SIM_META_PREFIX)[1]?.split('\n')[0] ?? '';
                            if (b64) {
                                try {
                                    const decoded = JSON.parse(atob(b64));
                                    setSimMeta(decoded);
                                } catch { /* ignore parse errors */ }
                            }
                            visible = visible.replace(new RegExp(`\\x00SIM_META:[^\n]*`), '').trim();
                        }

                        if (visible) appendToLast(visible);
                    } catch { /* skip malformed */ }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                appendToLast(`\n\n❌ **Connection error:** ${err.message}`);
            }
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
        if (streaming) { abortRef.current?.abort(); }
        await fetch(`${API_URL}/genai/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '', session_id: SESSION_ID }),
        }).catch(() => { });
        setMessages([{ id: Date.now(), role: 'bot', streaming: false, text: '🔄 **Session reset.** How can I help you?' }]);
        setStreaming(false);
        setSimMeta(null);
        setLastSimInfo(null);
    };

    const handleKey = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    };

    // Navigate to map view — passes hobli + rainfall so the dashboard pre-loads the simulation
    const handleViewMap = () => {
        const info = simMeta || lastSimInfo;
        if (onSimulationDone && info) {
            onSimulationDone(info.hobli, info.rainfall_mm ?? info.rainfall);
        } else {
            onBack();
        }
    };

    return (
        <div className="chatbot-page">
            {/* ── Header ── */}
            <header className="chatbot-header">
                <button className="chatbot-back-btn" onClick={onBack} title="Back to Digital Twin">
                    <ArrowLeft size={16} />
                    <span>Back to Dashboard</span>
                </button>
                <div className="chatbot-header-center">
                    <div className="chatbot-header-avatar"><Bot size={18} /></div>
                    <div>
                        <div className="chatbot-header-title">Flood AI — SimHelper</div>
                        <div className="chatbot-header-sub">AI-Powered Flood Assistant · Urban Digital Twin · Bengaluru</div>
                    </div>
                </div>
                <button className="chatbot-reset-btn" onClick={handleReset} title="Reset conversation">
                    <RefreshCw size={14} />
                    <span>Reset</span>
                </button>
            </header>

            {/* ── Messages ── */}
            <main className="chatbot-messages">
                {messages.map((msg) => (
                    <div key={msg.id} className={`chat-msg chat-msg--${msg.role}`}>
                        <div className={`chat-avatar chat-avatar--${msg.role}`}>
                            {msg.role === 'bot' ? <Bot size={14} /> : <User size={14} />}
                        </div>
                        <div className={`chat-bubble chat-bubble--${msg.role}`}>
                            {msg.role === 'bot'
                                ? <div className="chat-md">{renderMarkdown(msg.text)}</div>
                                : <span>{msg.text}</span>
                            }
                            {msg.streaming && msg.text === '' && (
                                <div className="chat-bubble--typing-inline">
                                    <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                                </div>
                            )}
                            {msg.streaming && msg.text !== '' && <span className="chat-cursor">▋</span>}
                        </div>
                    </div>
                ))}
                {streaming && messages[messages.length - 1]?.role === 'user' && <TypingIndicator />}

                {/* ── Inline SimResultPanel — appears after simulation completes ── */}
                {simMeta && !streaming && (
                    <div className="sim-panel-wrapper">
                        <SimResultPanel meta={simMeta} onViewMap={handleViewMap} />
                    </div>
                )}

                {/* ── Fallback: simple "View Map" banner if SIM_META wasn't received ── */}
                {!simMeta && lastSimInfo && !streaming && (
                    <div className="sim-done-banner">
                        <div className="sim-done-info">
                            <Map size={18} />
                            <div>
                                <div className="sim-done-title">Simulation complete — view results on map?</div>
                                <div className="sim-done-sub">{lastSimInfo.hobli} · {lastSimInfo.rainfall} mm</div>
                            </div>
                        </div>
                        <button className="sim-done-btn" onClick={handleViewMap}>
                            View Map &amp; Routes →
                        </button>
                    </div>
                )}

                <div ref={bottomRef} />
            </main>

            {/* ── Quick actions ── */}
            {messages.length <= 2 && !streaming && (
                <div className="chatbot-quick-actions">
                    {QUICK_ACTIONS.map((qa) => (
                        <button key={qa.label} className="chatbot-chip" onClick={() => send(qa.msg)}>
                            {qa.icon} {qa.label}
                        </button>
                    ))}
                </div>
            )}

            {/* ── Input bar ── */}
            <footer className="chatbot-input-bar">
                <div className="chatbot-input-wrap">
                    <textarea
                        ref={inputRef}
                        className="chatbot-input"
                        placeholder="e.g. Simulate Sarjapura, or type 1/2/3 to choose a rainfall scenario…"
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKey}
                        rows={1}
                        disabled={streaming}
                    />
                    <button
                        className={`chatbot-send-btn ${(!input.trim() || streaming) ? 'chatbot-send-btn--disabled' : ''}`}
                        onClick={() => send()}
                        disabled={!input.trim() || streaming}
                        title="Send (Enter)"
                    >
                        {streaming ? <Loader size={16} className="spin" /> : <Send size={16} />}
                    </button>
                </div>
                <div className="chatbot-footer-note">
                    Powered by <strong>Ollama llama3.2</strong> · Open-Meteo weather · Bengaluru IMD records
                </div>
            </footer>
        </div>
    );
}
