import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Send, Loader, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_URL } from '../config';

export function EvacuationChat({ context }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [isOpen, setIsOpen] = useState(false);
    const chatEndRef = useRef(null);

    // Auto-scroll to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = () => {
        const question = input.trim();
        if (!question || isStreaming || !context) return;

        setInput('');
        setMessages(prev => [...prev, { role: 'user', text: question }]);
        setIsStreaming(true);

        // Add empty assistant message that we'll stream into
        const assistantIdx = messages.length + 1;
        setMessages(prev => [...prev, { role: 'assistant', text: '' }]);

        fetch(`${API_URL}/evacuation-chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, context }),
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

    if (!isOpen) {
        return (
            <button
                className="chat-toggle-btn"
                onClick={() => setIsOpen(true)}
                title="Ask about this evacuation"
            >
                <MessageCircle size={14} />
                <span>Ask AI about this evacuation</span>
            </button>
        );
    }

    return (
        <section className="panel evac-section chat-section" style={{ borderTop: '2px solid #8b5cf6', marginTop: '0.75rem' }}>
            <div className="chat-header">
                <h3 className="panel-title" style={{ color: '#6d28d9', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
                    <MessageCircle size={14} /> Ask AI
                </h3>
                <button className="chat-close-btn" onClick={() => setIsOpen(false)} title="Close chat">
                    <X size={14} />
                </button>
            </div>

            {/* Messages */}
            <div className="chat-messages custom-scrollbar">
                {messages.length === 0 && (
                    <div className="chat-hint">
                        Ask anything about the evacuation data, e.g.:<br />
                        <em>"Why is this shelter overloaded?"</em><br />
                        <em>"Which route has the most evacuees?"</em>
                    </div>
                )}
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
                    placeholder="Ask something..."
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
