import { useState, useEffect } from 'react';
import { Loader, Anchor, Truck, Megaphone, ShieldAlert, Cpu } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

export function PanelOfExperts({ summary }) {
    const [activeExpert, setActiveExpert] = useState('logistics');
    const [responses, setResponses] = useState({ logistics: '', tactical: '', civic: '' });
    const [loading, setLoading] = useState({ logistics: false, tactical: false, civic: false });

    // Stream function
    const fetchExpertise = (persona) => {
        if (responses[persona] || loading[persona]) return;
        
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
                            const data = JSON.parse(line.slice(6));
                            if (data.text) {
                                setResponses(prev => ({ ...prev, [persona]: prev[persona] + data.text }));
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

    // Auto fetch when tab switched
    useEffect(() => {
        if (summary) {
            fetchExpertise(activeExpert);
        }
    }, [activeExpert, summary]);

    return (
        <section className="panel evac-section" style={{ borderTop: '2px solid #3b82f6', marginTop: '1rem' }}>
            <h3 className="panel-title" style={{ color: '#1e3a8a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Cpu size={14} /> AI Panel of Experts
            </h3>
            
            <div className="expert-tabs" style={{ display: 'flex', gap: '0.25rem', marginBottom: '10px', backgroundColor: '#f1f5f9', padding: '0.25rem', borderRadius: '0.375rem' }}>
                <button 
                  className={`btn-sm ${activeExpert === 'logistics' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '4px', border: 'none', background: activeExpert === 'logistics' ? '#2563eb' : 'transparent', color: activeExpert === 'logistics' ? 'white' : '#475569' }}
                  onClick={() => setActiveExpert('logistics')}>
                  <Truck size={12}/> Logistics Chief
                </button>
                <button 
                  className={`btn-sm ${activeExpert === 'tactical' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '4px', border: 'none', background: activeExpert === 'tactical' ? '#2563eb' : 'transparent', color: activeExpert === 'tactical' ? 'white' : '#475569' }}
                  onClick={() => setActiveExpert('tactical')}>
                  <Anchor size={12}/> Tactical Commander
                </button>
                <button 
                  className={`btn-sm ${activeExpert === 'civic' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '4px', border: 'none', background: activeExpert === 'civic' ? '#2563eb' : 'transparent', color: activeExpert === 'civic' ? 'white' : '#475569' }}
                  onClick={() => setActiveExpert('civic')}>
                  <Megaphone size={12}/> Civic Authority
                </button>
            </div>
            
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
        </section>
    );
}
