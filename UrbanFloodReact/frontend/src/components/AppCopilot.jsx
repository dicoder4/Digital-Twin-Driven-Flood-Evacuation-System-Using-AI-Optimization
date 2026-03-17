import { useState, useRef, useEffect } from 'react';
import { Bot, X, Send, ChevronUp, Loader, Maximize2, Minimize2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

const MIN_WIDTH = 300;
const MIN_HEIGHT = 320;
const DEFAULT_SIZE = { width: 320, height: 506 };
const EXPANDED_SIZE = { width: 560, height: 760 };
const WINDOW_MARGIN = 24;

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
    const [isExpanded, setIsExpanded] = useState(false);
    const [isResizing, setIsResizing] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const [windowState, setWindowState] = useState({
        width: DEFAULT_SIZE.width,
        height: DEFAULT_SIZE.height,
        left: null, // null means use CSS fixed positioning (bottom/right)
        top: null
    });

    const endRef = useRef(null);
    const interactionRef = useRef(null); // stores startX, startY, startW, startH, startL, startT, direction
    const preExpandStateRef = useRef(null);

    const clampSizeToViewport = (nextSize) => {
        const maxWidth = Math.max(MIN_WIDTH, window.innerWidth - (WINDOW_MARGIN * 2));
        const maxHeight = Math.max(MIN_HEIGHT, window.innerHeight - (WINDOW_MARGIN * 2));
        return {
            width: Math.min(maxWidth, Math.max(MIN_WIDTH, nextSize.width)),
            height: Math.min(maxHeight, Math.max(MIN_HEIGHT, nextSize.height)),
        };
    };

    const stopInteraction = () => {
        globalThis.removeEventListener('mousemove', onMouseMove);
        globalThis.removeEventListener('mouseup', stopInteraction);
        interactionRef.current = null;
        setIsResizing(false);
        setIsDragging(false);
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
    };

    const onMouseMove = (event) => {
        if (!interactionRef.current) return;
        const { type, direction, startX, startY, startW, startH, startL, startT } = interactionRef.current;
        const dx = event.clientX - startX;
        const dy = event.clientY - startY;

        if (type === 'drag') {
            setWindowState(prev => ({
                ...prev,
                left: startL + dx,
                top: startT + dy
            }));
            return;
        }

        // type === 'resize'
        let nextW = startW;
        let nextH = startH;
        let nextL = startL;
        let nextT = startT;

        if (direction.includes('e')) nextW = startW + dx;
        if (direction.includes('w')) {
            nextW = startW - dx;
            nextL = startL + dx;
        }
        if (direction.includes('s')) nextH = startH + dy;
        if (direction.includes('n')) {
            nextH = startH - dy;
            nextT = startT + dy;
        }

        // Enforce Min Size
        if (nextW < MIN_WIDTH) {
            if (direction.includes('w')) nextL = startL + (startW - MIN_WIDTH);
            nextW = MIN_WIDTH;
        }
        if (nextH < MIN_HEIGHT) {
            if (direction.includes('n')) nextT = startT + (startH - MIN_HEIGHT);
            nextH = MIN_HEIGHT;
        }

        setWindowState({ width: nextW, height: nextH, left: nextL, top: nextT });
    };

    const startResize = (event, direction) => {
        event.preventDefault();
        event.stopPropagation();
        if (isMinimized) return;

        const rect = event.currentTarget.closest('.copilot-window').getBoundingClientRect();
        setIsResizing(true);
        interactionRef.current = {
            type: 'resize',
            direction,
            startX: event.clientX,
            startY: event.clientY,
            startWidth: windowState.width,
            startHeight: windowState.height,
            startW: rect.width,
            startH: rect.height,
            startL: rect.left,
            startT: rect.top
        };

        document.body.style.userSelect = 'none';
        
        let cursor = 'nwse-resize';
        if (direction === 'n' || direction === 's') cursor = 'ns-resize';
        if (direction === 'e' || direction === 'w') cursor = 'ew-resize';
        if (direction === 'ne' || direction === 'sw') cursor = 'nesw-resize';
        
        document.body.style.cursor = cursor;
        globalThis.addEventListener('mousemove', onMouseMove);
        globalThis.addEventListener('mouseup', stopInteraction);
    };

    const startDrag = (event) => {
        if (isMinimized || isResizing || event.target.closest('.copilot-actions')) return;
        event.preventDefault();
        
        const rect = event.currentTarget.closest('.copilot-window').getBoundingClientRect();
        setIsDragging(true);
        interactionRef.current = {
            type: 'drag',
            startX: event.clientX,
            startY: event.clientY,
            startL: rect.left,
            startT: rect.top
        };

        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'move';
        globalThis.addEventListener('mousemove', onMouseMove);
        globalThis.addEventListener('mouseup', stopInteraction);
    };

    const toggleExpand = () => {
        if (isExpanded) {
            if (preExpandStateRef.current) {
                setWindowState(preExpandStateRef.current);
            } else {
                setWindowState(prev => ({ ...prev, width: DEFAULT_SIZE.width, height: DEFAULT_SIZE.height }));
            }
            setIsExpanded(false);
            return;
        }

        // Get current rect to preserve L/T if active
        const rect = document.querySelector('.copilot-window')?.getBoundingClientRect();
        preExpandStateRef.current = { ...windowState };
        
        setWindowState({
            width: EXPANDED_SIZE.width,
            height: EXPANDED_SIZE.height,
            left: rect ? rect.left - (EXPANDED_SIZE.width - rect.width) / 2 : null,
            top: rect ? rect.top - (EXPANDED_SIZE.height - rect.height) / 2 : null
        });
        setIsExpanded(true);
    };

    // ... lines omitted for space ...

    // Auto-scroll Down
    useEffect(() => {
        if (isOpen && !isMinimized && endRef.current) {
            endRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isOpen, isMinimized, isTyping]);

    useEffect(() => {
        return () => {
            stopInteraction();
        };
    }, []);

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

    const chatBodyHeight = Math.max(170, windowState.height - 156);

    const windowStyle = {
        width: `${windowState.width}px`,
        height: isMinimized ? '44px' : `${windowState.height}px`,
    };
    if (windowState.left !== null) {
        windowStyle.left = `${windowState.left}px`;
        windowStyle.top = `${windowState.top}px`;
        windowStyle.right = 'auto';
        windowStyle.bottom = 'auto';
        windowStyle.transform = 'none';
    }

    return (
        <div
            className={`copilot-window ${isMinimized ? 'copilot-minimized' : ''} ${isExpanded ? 'copilot-expanded' : ''} ${isResizing || isDragging ? 'copilot-resizing' : ''}`}
            style={windowStyle}
        >
            {/* Draggable Borders/Handles (Free Resize like Word) */}
            {!isMinimized && (
                <>
                    <div className="resizer resizer-n" onMouseDown={e => startResize(e, 'n')} />
                    <div className="resizer resizer-e" onMouseDown={e => startResize(e, 'e')} />
                    <div className="resizer resizer-s" onMouseDown={e => startResize(e, 's')} />
                    <div className="resizer resizer-w" onMouseDown={e => startResize(e, 'w')} />
                    <div className="resizer resizer-nw" onMouseDown={e => startResize(e, 'nw')} />
                    <div className="resizer resizer-ne" onMouseDown={e => startResize(e, 'ne')} />
                    <div className="resizer resizer-se" onMouseDown={e => startResize(e, 'se')} />
                    <div className="resizer resizer-sw" onMouseDown={e => startResize(e, 'sw')} />
                </>
            )}

            {/* Header */}
            <div className="copilot-header" onMouseDown={startDrag}>
                <div className="copilot-title">
                    <Bot size={18} />
                    <span>App Copilot</span>
                </div>
                <div className="copilot-actions">
                    <button onClick={toggleExpand} title={isExpanded ? 'Restore size' : 'Expand'}>
                        {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                    </button>
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
                    <div className="copilot-body custom-scrollbar" style={{ height: `${chatBodyHeight}px` }}>
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

                    {/* No legacy handle needed, multiple resizers added above */}
                </>
            )}
        </div>
    );
}
