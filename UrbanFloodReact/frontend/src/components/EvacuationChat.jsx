import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Send, Loader, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

export function EvacuationChat({ context, evacuationPlan = [] }) {
    const { lang } = useLanguage();
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            text: "Hi! I'm your AI Evacuation Assistant.\nHere are some questions you can ask me to help plan the evacuation efficiently:\n\n- What is the safest route to the nearest shelter?\n- Which junctions are experiencing the worst bottlenecks?\n- How many evacuees are assigned to each shelter?\n- Are there any shelters exceeding their capacity?\n- Which optimization algorithm performed the best for this simulation?"
        }
    ]);
    const [input, setInput] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const chatEndRef = useRef(null);

    // Auto-scroll to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = (overrideInput = null) => {
        const question = overrideInput !== null ? overrideInput : input.trim();
        if (!question || isStreaming || !context) return;

        setInput('');
        
        setMessages(prev => [...prev, { role: 'user', text: question }]);
        setIsStreaming(true);

        // Add empty assistant message that we'll stream into
        setMessages(prev => [...prev, { role: 'assistant', text: '' }]);

        fetch(`${API_URL}/evacuation-chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, context, evacuation_plan: evacuationPlan }),
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
                            const data = JSON.parse(line.trim().slice(6));
                            if (data.text) {
                                setMessages(prev => {
                                    const updated = [...prev];
                                    const last = updated[updated.length - 1];
                                    if (last && last.role === 'assistant') {
                                        updated[updated.length - 1] = { ...last, text: last.text + data.text };
                                    }
                                    return updated;
                                });
                            }
                        } catch (e) { /* ignore */ }
                    }
                }
            }
        }).catch(err => {
            setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', text: 'Error: ' + err.message };
                return updated;
            });
        }).finally(() => {
            setIsStreaming(false);
        });
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <section className="panel evac-section chat-section" style={{ height: 'calc(100% - 2rem)', display: 'flex', flexDirection: 'column', borderTop: 'none', marginTop: 0 }}>
            <div className="chat-header">
                <h3 className="panel-title" style={{ color: '#6d28d9', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
                    <MessageCircle size={14} /> {t('ask_ai', lang)}
                </h3>
            </div>

            {/* Messages */}
            <div className="chat-messages custom-scrollbar">

                {messages.map((msg, i) => (
                    <div key={i} className={`chat-msg chat-msg--${msg.role}`}>
                        {msg.role === 'user' ? (
                            <div className="chat-msg-bubble chat-msg-user">{msg.text}</div>
                        ) : (
                            <div className="chat-msg-bubble chat-msg-ai">
                                <ReactMarkdown>{msg.text || '...'}</ReactMarkdown>
                                {isStreaming && i === messages.length - 1 && (
                                    <span className="chat-cursor">▋</span>
                                )}
                            </div>
                        )}
                    </div>
                ))}
                <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="chat-input-row">
                <input
                    className="chat-input"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={t('chat_placeholder', lang)}
                    disabled={isStreaming || !context}
                />
                <button
                    className="chat-send-btn"
                    onClick={handleSend}
                    disabled={!input.trim() || isStreaming || !context}
                    title="Send"
                >
                    {isStreaming ? <Loader size={14} className="spin" /> : <Send size={14} />}
                </button>
            </div>
        </section>
    );
}
