import { useState, useEffect } from 'react';
import { Loader, Truck, Anchor, Megaphone, Cpu, CheckCircle, ChevronDown } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

const TABS = [
    { key: 'logistics', label: 'Logistics Chief', icon: Truck, color: '#2563eb', bgActive: '#eff6ff', loadingMsg: 'Calculating supply chains...' },
    { key: 'tactical', label: 'Tactical Commander', icon: Anchor, color: '#d97706', bgActive: '#fffbeb', loadingMsg: 'Analyzing strategic routes...' },
    { key: 'civic', label: 'Civic Authority', icon: Megaphone, color: '#16a34a', bgActive: '#f0fdf4', loadingMsg: 'Drafting civic communications...' },
];

export function PanelOfExperts({ summary, evacuationPlan }) {
    const [isOpen, setIsOpen] = useState(false);
    const [activeTab, setActiveTab] = useState('logistics');
    const [responses, setResponses] = useState({ logistics: '', tactical: '', civic: '' });
    const [loading, setLoading] = useState({ logistics: false, tactical: false, civic: false });
    const [fetched, setFetched] = useState({ logistics: false, tactical: false, civic: false });

    // Auto-fetch on tab switch if not yet loaded (only when panel is open)
    useEffect(() => {
        if (isOpen && summary && activeTab && !fetched[activeTab] && !loading[activeTab]) {
            fetchExpertise(activeTab);
        }
    }, [activeTab, summary, isOpen]);

    const fetchExpertise = (persona) => {
        if (!summary || loading[persona]) return;

        setLoading(prev => ({ ...prev, [persona]: true }));
        setResponses(prev => ({ ...prev, [persona]: '' }));

        fetch(`${API_URL}/expert-advice-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                persona,
                summary_data: summary,
                evacuation_plan: evacuationPlan || [],
            }),
        }).then(async res => {
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const params = line.trim().slice(6);
                            if (params) {
                                const data = JSON.parse(params);
                                if (data.text) {
                                    setResponses(prev => ({ ...prev, [persona]: prev[persona] + data.text }));
                                }
                            }
                        } catch (e) { /* ignore */ }
                    }
                }
            }
        }).catch(err => {
            setResponses(prev => ({ ...prev, [persona]: 'Error connecting to AI: ' + err.message }));
        }).finally(() => {
            setLoading(prev => ({ ...prev, [persona]: false }));
            setFetched(prev => ({ ...prev, [persona]: true }));
        });
    };

    const activeConfig = TABS.find(t => t.key === activeTab);

    return (
        <div className="expert-panel-wrapper">
            {/* ── Toggle Header ─────────────────────────────── */}
            <button
                className="expert-panel-toggle"
                onClick={() => setIsOpen(prev => !prev)}
            >
                <span className="expert-panel-toggle-title">
                    <Cpu size={13} /> AI Panel of Experts
                </span>
                <ChevronDown
                    size={13}
                    className={`genai-chevron ${isOpen ? 'genai-chevron--open' : ''}`}
                />
            </button>

            {isOpen && (
                <div className="expert-panel-body">
                    {/* ── Tab Buttons ──────────────────────────────── */}
                    <div className="expert-tabs">
                        {TABS.map(tab => {
                            const Icon = tab.icon;
                            const isActive = activeTab === tab.key;
                            const isDone = fetched[tab.key] && !loading[tab.key] && responses[tab.key];
                            const isLoading = loading[tab.key];

                            return (
                                <button
                                    key={tab.key}
                                    className={`expert-tab ${isActive ? 'expert-tab--active' : ''}`}
                                    style={{
                                        borderBottomColor: isActive ? tab.color : 'transparent',
                                        color: isActive ? tab.color : '#64748b',
                                        backgroundColor: isActive ? tab.bgActive : 'transparent',
                                    }}
                                    onClick={() => setActiveTab(tab.key)}
                                >
                                    <Icon size={13} />
                                    <span className="expert-tab-label">{tab.label.split(' ')[0]}</span>
                                    {isLoading && <Loader size={10} className="spin" />}
                                    {isDone && <CheckCircle size={10} style={{ color: '#16a34a' }} />}
                                </button>
                            );
                        })}
                    </div>

                    {/* ── Response Area ─────────────────────────────── */}
                    <div
                        className="expert-content custom-scrollbar"
                        style={{
                            backgroundColor: '#ffffff',
                            padding: '12px 16px',
                            borderRadius: '0 0 6px 6px',
                            fontSize: '13px',
                            minHeight: '150px',
                            maxHeight: '400px',
                            overflowY: 'auto',
                            border: '1px solid #e2e8f0',
                            borderTop: `2px solid ${activeConfig?.color || '#3b82f6'}`,
                            color: '#334155',
                            lineHeight: '1.6',
                        }}
                    >
                        {loading[activeTab] && !responses[activeTab] && (
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#64748b', height: '100px' }}>
                                <Loader size={16} className="spin" />
                                <span>{activeConfig?.loadingMsg || 'Analyzing...'}</span>
                            </div>
                        )}

                        {responses[activeTab] && (
                            <div className="markdown-body">
                                <ReactMarkdown>{responses[activeTab]}</ReactMarkdown>
                            </div>
                        )}

                        {loading[activeTab] && responses[activeTab] && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '10px', fontSize: '11px', color: '#94a3b8' }}>
                                <Loader size={10} className="spin" /> Generating...
                            </div>
                        )}

                        {!loading[activeTab] && !responses[activeTab] && fetched[activeTab] && (
                            <div style={{ color: '#94a3b8', textAlign: 'center', marginTop: '40px' }}>
                                No response received. Check API connectivity.
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
