import { useState } from 'react';
import { Loader, Anchor, Truck, Megaphone, Cpu } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

export function PanelOfExperts({ summary }) {
    const [activeExpert, setActiveExpert] = useState(null);
    const [responses, setResponses] = useState({ logistics: '', tactical: '', civic: '' });
    const [loading, setLoading] = useState({ logistics: false, tactical: false, civic: false });

    // Stream function
    const fetchExpertise = (persona) => {
        if (!summary || loading[persona]) return;
        
        setActiveExpert(persona);
        setLoading(prev => ({ ...prev, [persona]: true }));
        setResponses(prev => ({ ...prev, [persona]: '' }));

        const ctrl = new AbortController();
        
        fetch(`${API_URL}/expert-advice-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ persona, summary_data: summary }),
            signal: ctrl.signal
        }).then(async res => {
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            while(true) {
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
                        } catch (e) {
                            // ignore json parse errors for incomplete chunks
                        }
                    }
                }
            }
        }).catch(err => {
            setResponses(prev => ({ ...prev, [persona]: 'Error connecting to AI: ' + err.message }));
        }).finally(() => {
            setLoading(prev => ({ ...prev, [persona]: false }));
        });
    };

    return (
        <section className="panel evac-section" style={{ borderTop: '2px solid #3b82f6', marginTop: '1rem' }}>
            <h3 className="panel-title" style={{ color: '#1e3a8a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Cpu size={14} /> AI Panel of Experts
            </h3>
            
            <div className="expert-list" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '10px' }}>
                {/* Logistics */}
                <div style={{ padding: '0.5rem', border: '1px solid #e2e8f0', borderRadius: '0.375rem', backgroundColor: activeExpert === 'logistics' ? '#eff6ff' : '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold', color: '#1e293b' }}>
                        <Truck size={16} color="#2563eb" /> Logistics Chief
                    </div>
                    <button 
                        className="btn-sm btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                        disabled={loading['logistics'] || !summary}
                        onClick={() => fetchExpertise('logistics')}>
                        {loading['logistics'] ? <><Loader size={12} className="spin" /> Thinking...</> : 'Logistics Analysis'}
                    </button>
                </div>

                {/* Tactical */}
                <div style={{ padding: '0.5rem', border: '1px solid #e2e8f0', borderRadius: '0.375rem', backgroundColor: activeExpert === 'tactical' ? '#eff6ff' : '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold', color: '#1e293b' }}>
                        <Anchor size={16} color="#2563eb" /> Tactical Commander
                    </div>
                    <button 
                        className="btn-sm btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                        disabled={loading['tactical'] || !summary}
                        onClick={() => fetchExpertise('tactical')}>
                        {loading['tactical'] ? <><Loader size={12} className="spin" /> Thinking...</> : 'Tactical Analysis'}
                    </button>
                </div>

                {/* Civic */}
                <div style={{ padding: '0.5rem', border: '1px solid #e2e8f0', borderRadius: '0.375rem', backgroundColor: activeExpert === 'civic' ? '#eff6ff' : '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold', color: '#1e293b' }}>
                        <Megaphone size={16} color="#2563eb" /> Civic Authority
                    </div>
                    <button 
                        className="btn-sm btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                        disabled={loading['civic'] || !summary}
                        onClick={() => fetchExpertise('civic')}>
                        {loading['civic'] ? <><Loader size={12} className="spin" /> Thinking...</> : 'Civic Analysis'}
                    </button>
                </div>
            </div>
            
            {activeExpert && (
                <div className="expert-content custom-scrollbar" style={{ backgroundColor: '#ffffff', padding: '12px 16px', borderRadius: '6px', fontSize: '13px', minHeight: '150px', maxHeight: '400px', overflowY: 'auto', border: '2px solid #e2e8f0', color: '#334155', lineHeight: '1.6' }}>
                    {loading[activeExpert] && !responses[activeExpert] && (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#64748b', height: '100px' }}>
                            <Loader size={16} className="spin" />
                            <span>{activeExpert === 'logistics' ? 'Calculating supply chains...' : activeExpert === 'tactical' ? 'Analyzing strategic routes...' : 'Drafting civic communications...'}</span>
                        </div>
                    )}
                    
                    {responses[activeExpert] && (
                        <div className="markdown-body">
                            <ReactMarkdown>{responses[activeExpert]}</ReactMarkdown>
                        </div>
                    )}
                    
                    {loading[activeExpert] && responses[activeExpert] && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '10px', fontSize: '11px', color: '#94a3b8' }}>
                            <Loader size={10} className="spin" /> Generating...
                        </div>
                    )}
                </div>
            )}
        </section>
    );
}
