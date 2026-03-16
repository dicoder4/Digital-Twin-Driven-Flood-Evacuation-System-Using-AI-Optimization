import { useState, useRef, useEffect } from 'react';
import { Bot, X, Send, ChevronUp, Loader } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

/** Multi-select toggle chips with a Confirm button */
function OptionChips({ options, disabled, onConfirm }) {
    const [selected, setSelected] = useState(new Set());
    const [confirmed, setConfirmed] = useState(false);

    const toggle = (opt) => {
        if (confirmed || disabled) return;
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(opt)) next.delete(opt);
            else next.add(opt);
            return next;
        });
    };

    const handleConfirm = () => {
        if (selected.size === 0 || confirmed || disabled) return;
        setConfirmed(true);
        onConfirm([...selected]);
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {options.map((opt, i) => {
                    const isSelected = selected.has(opt);
                    return (
                        <button
                            key={i}
                            onClick={() => toggle(opt)}
                            disabled={confirmed || disabled}
                            style={{
                                padding: '6px 10px',
                                fontSize: '12px',
                                borderRadius: '16px',
                                background: isSelected ? '#4338ca' : '#e0e7ff',
                                color: isSelected ? '#fff' : '#4338ca',
                                border: `1px solid ${isSelected ? '#4338ca' : '#c7d2fe'}`,
                                cursor: confirmed ? 'default' : 'pointer',
                                transition: 'all 0.2s',
                                opacity: confirmed ? 0.6 : 1,
                            }}
                        >
                            {opt}
                        </button>
                    );
                })}
            </div>
            {!confirmed && selected.size > 0 && (
                <button
                    onClick={handleConfirm}
                    disabled={disabled}
                    style={{
                        padding: '6px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        borderRadius: '16px',
                        background: '#4338ca',
                        color: '#fff',
                        border: 'none',
                        cursor: 'pointer',
                        alignSelf: 'flex-start',
                        transition: 'background 0.2s',
                    }}
                    onMouseOver={e => e.target.style.background = '#3730a3'}
                    onMouseOut={e => e.target.style.background = '#4338ca'}
                >
                    ▶ Confirm
                </button>
            )}
        </div>
    );
}

export function AppCopilot({ availableHoblis, regionsTree, populationCount, onNavigate, onSelectRegion, onRunSimulation, onUpdateParams }) {
    const [isOpen, setIsOpen] = useState(false);
    const [isMinimized, setIsMinimized] = useState(false);
    const [messages, setMessages] = useState([
        { role: 'assistant', content: "Hi! I'm your App Copilot. How can I help you navigate or run a simulation today?" }
    ]);
    const [input, setInput] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const endRef = useRef(null);

    // ... lines omitted for space ...

    // Auto-scroll Down
    useEffect(() => {
        if (isOpen && !isMinimized && endRef.current) {
            endRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isOpen, isMinimized, isTyping]);

    const handleSend = async () => {
        if (!input.trim() || isTyping) return;

        const userMsg = input.trim();
        setInput('');
        const newMessages = [...messages, { role: 'user', content: userMsg }];
        setMessages(newMessages);
        setIsTyping(true);

        try {
            // Strip out our custom UI properties (like options) before sending back to the LLM
            const cleanMessages = newMessages.slice(1).map(({ options, ...msg }) => msg);
            
            const res = await fetch(`${API_URL}/app-copilot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    messages: cleanMessages,
                    available_hoblis: availableHoblis || [],
                    regions_tree: regionsTree || {} 
                }),
            });

            const data = await res.json();
            
            if (data.type === 'tool_call') {
                const funcName = data.name;
                const args = data.arguments;
                
                let actionMsg = "";
                
                if (funcName === 'navigate') {
                    onNavigate(args.tab);
                    actionMsg = `*[Navigated to **${args.tab}** tab]*`;
                } else if (funcName === 'select_region') {
                    onSelectRegion && onSelectRegion(args.hobli);
                    actionMsg = `*[Region set to **${args.hobli}** — sidebar updated ✓]*`;
                } else if (funcName === 'run_simulation') {
                    onRunSimulation(
                        args.hobli,
                        args.rainfall_mm,
                        args.algorithm,
                        args.evacuation_mode,
                        args.use_traffic
                    );
                    const algo = (args.algorithm || 'aco').toUpperCase();
                    const traffic = args.use_traffic ? ' · traffic on' : '';
                    const evac = args.evacuation_mode ? ' · evac mode' : '';
                    actionMsg = `*[Running **${algo}** for **${args.hobli}** @ ${args.rainfall_mm || 150}mm${traffic}${evac}]*`;
                } else {
                    actionMsg = `*[Attempted unknown action: ${funcName}]*`;
                }
                
                setMessages(prev => [...prev, { role: 'assistant', content: actionMsg }]);

                // After select_region, auto-follow-up to get parameter options
                if (funcName === 'select_region') {
                    // Slight delay to allow App.jsx state to settle before we read populationCount
                    setTimeout(async () => {
                        let popWarning = "";
                        if (populationCount === 0) {
                            popWarning = " Note: This region has no CSV population data. Please set the population manually in the sidebar.";
                        }
                        
                        const followupMessages = [
                            ...cleanMessages,
                            { role: 'assistant', content: `Region set to ${args.hobli}.${popWarning} Now ask the user how they want to run the simulation.` }
                        ];
                        try {
                            const followRes = await fetch(`${API_URL}/app-copilot`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    messages: followupMessages,
                                    available_hoblis: availableHoblis || [],
                                    regions_tree: regionsTree || {}
                                }),
                            });
                            const followData = await followRes.json();
                            if (followData.options && followData.options.length > 0) {
                                setMessages(prev => [...prev, {
                                    role: 'assistant',
                                    content: followData.content,
                                    options: followData.options
                                }]);
                            } else if (followData.content) {
                                setMessages(prev => [...prev, { role: 'assistant', content: followData.content }]);
                            }
                        } catch (e) {
                            console.warn('Follow-up request failed:', e);
                        }
                    }, 800);
                }
            } else {
                setMessages(prev => [...prev, { 
                    role: 'assistant', 
                    content: data.content,
                    options: data.options || [] 
                }]);
            }
        } catch (err) {
            setMessages(prev => [...prev, { role: 'assistant', content: "Error connecting to Copilot: " + err.message }]);
        } finally {
            setIsTyping(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Render floating trigger button if closed
    if (!isOpen) {
        return (
            <button className="copilot-trigger" onClick={() => setIsOpen(true)}>
                <Bot size={24} />
            </button>
        );
    }

    return (
        <div className={`copilot-window ${isMinimized ? 'copilot-minimized' : ''}`}>
            {/* Header */}
            <div className="copilot-header">
                <div className="copilot-title">
                    <Bot size={18} />
                    <span>App Copilot</span>
                </div>
                <div className="copilot-actions">
                    <button onClick={() => setIsMinimized(!isMinimized)} title={isMinimized ? "Expand" : "Minimize"}>
                        <ChevronUp size={16} style={{ transform: isMinimized ? 'rotate(180deg)' : 'none' }} />
                    </button>
                    <button onClick={() => setIsOpen(false)} title="Close">
                        <X size={16} />
                    </button>
                </div>
            </div>

            {/* Chat Body (hidden if minimized) */}
            {!isMinimized && (
                <>
                    <div className="copilot-body custom-scrollbar">
                        {messages.map((msg, idx) => (
                            <div key={idx} className={`chat-line ${msg.role === 'user' ? 'chat-line-user' : 'chat-line-ai'}`}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                                    <div className={`chat-bubble ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
                                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                                    </div>
                                    {/* Multi-select option chips */}
                                    {msg.options && msg.options.length > 0 && (
                                        <OptionChips
                                            options={msg.options}
                                            disabled={isTyping}
                                            onConfirm={(selected) => {
                                                const combined = selected.join(', ');
                                                
                                                // Try to parse values out to update sidebar instantly
                                                let pAlgorithm = undefined;
                                                let pEvac = undefined;
                                                let pTraffic = undefined;
                                                let pRain = undefined;
                                                
                                                const txt = combined.toLowerCase();
                                                if (txt.includes('ga')) pAlgorithm = 'ga';
                                                if (txt.includes('pso')) pAlgorithm = 'pso';
                                                if (txt.includes('aco')) pAlgorithm = 'aco';
                                                if (txt.includes('compare')) pAlgorithm = 'all';
                                                if (txt.includes('traffic')) pTraffic = true;
                                                if (txt.includes('evacuation') || txt.includes('evac mode')) pEvac = true;
                                                if (txt.includes('150mm')) pRain = 150;

                                                if (onUpdateParams) {
                                                    onUpdateParams({ 
                                                        algorithm: pAlgorithm, 
                                                        evacuationMode: pEvac, 
                                                        useTraffic: pTraffic, 
                                                        rainfall: pRain 
                                                    });
                                                }

                                                setInput(combined);
                                                setTimeout(() => document.querySelector('.chat-send-btn')?.click(), 50);
                                            }}
                                        />
                                    )}
                                </div>
                            </div>
                        ))}
                        {isTyping && (
                            <div className="chat-line chat-line-ai">
                                <div className="chat-bubble chat-bubble-ai" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', padding: '6px 12px' }}>
                                    <Loader size={12} className="spin" /> Thinking...
                                </div>
                            </div>
                        )}
                        <div ref={endRef} />
                    </div>

                    {/* Input Area */}
                    <div className="copilot-footer">
                        <textarea
                            className="chat-input"
                            style={{ minHeight: '40px', maxHeight: '80px' }}
                            placeholder="Ask me to navigate or run a simulation..."
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                        <button 
                            className="chat-send-btn outline-none" 
                            onClick={handleSend}
                            disabled={!input.trim() || isTyping}
                        >
                            <Send size={16} />
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}
