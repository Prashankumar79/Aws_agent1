/**
 * RagChatPage — Chat interface for RAG-based document Q&A.
 *
 * PURPOSE:
 *   Provides a chat UI for asking questions about indexed documents.
 *   Uses SSE streaming for real-time responses.
 *
 * CONNECTIONS:
 *   • api.ts → calls ragChat() with SSE streaming
 *   • workflowStore.ts → reads ragIndexed status
 */

import { useState, useRef, useEffect } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { api, RagResponse } from '../services/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  rag?: RagResponse;  // Structured RAG response for assistant messages
}

export const RagChatPage = () => {
  const { ragIndexed, ragJobId, setRAGIndexed } = useWorkflowStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [conversations, setConversations] = useState<{ id: string; title: string; messages: Message[]; timestamp: number }[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [docMetadata, setDocMetadata] = useState<{ filename: string; chunks_count: number } | null>(null);
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  // 🟢 BEGINNER: Defensive re-check on mount.
  // If we have a ragJobId in the persisted store, ask the backend whether the
  // index actually completed. This fixes the case where ragIndexed=false in
  // localStorage but the document is in fact indexed (e.g. user cleared
  // localStorage, or the indexing finished AFTER they switched tab).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!ragJobId) return;
      try {
        const status = await api.getRAGStatus(ragJobId) as any;
        if (cancelled) return;
        if (status.status === 'indexed') {
          setRAGIndexed(true);
          setDocMetadata({
            filename: status.filename || 'Document',
            chunks_count: status.chunks_count || 0,
          });
        } else if (status.status === 'failed') {
          setStatusMessage(`Indexing failed: ${status.error || 'unknown error'}`);
        } else if (!ragIndexed) {
          setStatusMessage(`Indexing in progress (${status.progress ?? 0}%): ${status.stage}`);
        }
      } catch {
        // Backend down or job long-expired — keep the empty state.
      }
    })();
    return () => { cancelled = true; };
  }, [ragJobId, ragIndexed, setRAGIndexed]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const runQuery = async (userMessage: string) => {
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const result = await api.ragQuery(userMessage);
      setMessages(prev => {
        const newMessages = [...prev];
        if (result.error) {
          newMessages[newMessages.length - 1] = { role: 'assistant', content: result.error };
        } else {
          newMessages[newMessages.length - 1] = {
            role: 'assistant',
            content: result.summary || '',
            rag: result,
          };
        }
        return newMessages;
      });
    } catch (error) {
      setMessages(prev => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          role: 'assistant',
          content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const userMessage = input.trim();
    setInput('');
    await runQuery(userMessage);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestedQuestions = [
    'What are the critical compliance gaps in the current architecture?',
    'Estimate migration effort in engineering hours',
    'Which AWS services are recommended for the database tier?',
    'What naming conventions apply to this client template?',
    'List all security controls mentioned in the document',
  ];

  const handleSuggestedClick = (question: string) => {
    setInput('');
    runQuery(question);
  };

  const handleNewConversation = () => {
    if (messages.length > 0) {
      // Save current conversation
      const title = messages[0]?.content.slice(0, 30) + '...' || 'New Conversation';
      const newConversation = {
        id: Date.now().toString(),
        title,
        messages: [...messages],
        timestamp: Date.now()
      };
      setConversations(prev => [newConversation, ...prev]);
    }
    setMessages([]);
    setSelectedConversationId(null);
  };

  const handleSelectConversation = (id: string) => {
    const conversation = conversations.find(c => c.id === id);
    if (conversation) {
      setMessages(conversation.messages);
      setSelectedConversationId(id);
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setIsLoading(false);  // Reset loading state so input isn't stuck disabled
    setInput('');
  };

  const handleExport = () => {
    const md = messages.map(m => `**${m.role === 'user' ? 'You' : 'Assistant'}:**\n${m.content}\n`).join('\n---\n\n');
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chat-export.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!ragIndexed) {
    return (
      <main style={{ flex: 1, padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginTop: '100px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: '#1a1a1a', marginBottom: '12px' }}>
            {statusMessage ? 'RAG indexing not finished' : 'No Document Indexed'}
          </h2>
          <p style={{ fontSize: '14px', color: '#6b6b6b', marginBottom: '24px' }}>
            {statusMessage || 'Please upload a document on the Upload page and click "Initialize RAG" to index it for chat.'}
          </p>
          <button
            onClick={() => {
              window.history.pushState({}, '', '/');
              window.dispatchEvent(new PopStateEvent('popstate'));
            }}
            style={{
              padding: '12px 24px',
              backgroundColor: '#5B4EE8',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '14px',
              cursor: 'pointer',
            }}
          >
            Go to Upload Page
          </button>
        </div>
      </main>
    );
  }

  return (
    <main style={{ flex: 1, display: 'flex', height: 'calc(100vh - 52px)', backgroundColor: '#FAFAFA' }}>
      {/* ── Left Sidebar ── */}
      <aside style={{ width: '260px', minWidth: '260px', backgroundColor: '#ffffff', borderRight: '1px solid rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        {/* New Conversation Button */}
        <div style={{ padding: '16px', borderBottom: '1px solid rgba(0,0,0,0.08)' }}>
          <button
            onClick={handleNewConversation}
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '8px',
              border: '0.5px solid rgba(0,0,0,0.12)',
              backgroundColor: '#ffffff',
              fontSize: '13px',
              color: '#1a1a1a',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background-color 0.2s ease',
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5F3EE'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#ffffff'}
          >
            <i className="ti ti-plus" style={{ fontSize: '14px' }} />
            New conversation
          </button>
        </div>

        {/* Conversation History */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
          <h3 style={{ fontSize: '11px', fontWeight: 600, color: '#9b9b9b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>
            Recent
          </h3>
          {conversations.length === 0 ? (
            <div style={{ fontSize: '12px', color: '#6b6b6b', textAlign: 'center', marginTop: '20px' }}>
              No conversations yet
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {conversations.map(conv => (
                <button
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv.id)}
                  style={{
                    textAlign: 'left',
                    padding: '10px 12px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: selectedConversationId === conv.id ? '#F5F3EE' : 'transparent',
                    fontSize: '13px',
                    color: '#1a1a1a',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                  onMouseEnter={(e) => {
                    if (selectedConversationId !== conv.id) {
                      e.currentTarget.style.backgroundColor = '#F5F3EE';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedConversationId !== conv.id) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  {conv.title}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Settings */}
        <div style={{ padding: '16px', borderTop: '1px solid rgba(0,0,0,0.08)' }}>
          <button
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: 'transparent',
              fontSize: '13px',
              color: '#6b6b6b',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background-color 0.2s ease',
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5F3EE'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            <i className="ti ti-settings" style={{ fontSize: '14px' }} />
            Settings
          </button>
        </div>
      </aside>

      {/* ── Main Chat Area ── */}
      <section style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Chat Header */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(0,0,0,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#ffffff' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div>
              <h1 style={{ fontSize: '20px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>AI Assistant</h1>
              <p style={{ fontSize: '13px', color: '#6b6b6b', margin: '4px 0 0 0' }}>Answers grounded in your indexed migration document</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <select
              style={{
                padding: '8px 12px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                backgroundColor: '#ffffff',
                fontSize: '13px',
                color: '#1a1a1a',
                cursor: 'pointer',
              }}
            >
              <option>Claude 3.5 Sonnet</option>
              <option>Claude 3 Opus</option>
              <option>GPT-4</option>
            </select>
            <button
              onClick={handleClearChat}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                backgroundColor: '#ffffff',
                fontSize: '13px',
                color: '#6b6b6b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <i className="ti ti-trash" style={{ fontSize: '14px' }} />
              Clear chat
            </button>
            <button
              onClick={handleExport}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                backgroundColor: '#ffffff',
                fontSize: '13px',
                color: '#6b6b6b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <i className="ti ti-download" style={{ fontSize: '14px' }} />
              Export
            </button>
          </div>
        </div>

        {/* Document Context Panel */}
        <div style={{ padding: '16px 24px', backgroundColor: '#F5F3EE', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', maxWidth: '800px', margin: '0 auto' }}>
            <i className="ti ti-file-pdf" style={{ fontSize: '16px', color: '#5B4EE8' }} />
            <span style={{ fontSize: '13px', fontWeight: 500, color: '#1a1a1a' }}>{docMetadata?.filename || 'Document'}</span>
            <span style={{ fontSize: '12px', color: '#10B981', marginLeft: 'auto' }}>Indexed</span>
            {docMetadata?.chunks_count ? (
              <span style={{ fontSize: '12px', color: '#6b6b6b' }}>· {docMetadata.chunks_count} chunks</span>
            ) : null}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px', backgroundColor: '#FAFAFA' }}>
          <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: '#9b9b9b', marginTop: '60px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#5B4EE8', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <span style={{ color: 'white', fontSize: '16px', fontWeight: 600 }}>MP</span>
                </div>
                <p style={{ fontSize: '14px', marginBottom: '24px' }}>Hello! I've indexed your document and I'm ready to answer questions about your architecture, compliance requirements, and infrastructure design. What would you like to explore?</p>
                
                {/* Suggested Questions as Chips */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center' }}>
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestedClick(q)}
                      style={{
                        padding: '10px 16px',
                        borderRadius: '20px',
                        border: '1px solid rgba(0,0,0,0.12)',
                        backgroundColor: '#ffffff',
                        fontSize: '13px',
                        color: '#1a1a1a',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = '#F5F3EE';
                        e.currentTarget.style.borderColor = '#5B4EE8';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = '#ffffff';
                        e.currentTarget.style.borderColor = 'rgba(0,0,0,0.12)';
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} style={{ marginBottom: '20px', display: 'flex', gap: '12px', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                {/* Avatar */}
                {msg.role === 'assistant' ? (
                  <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#5B4EE8', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
                    <span style={{ color: 'white', fontSize: '12px', fontWeight: 600 }}>MP</span>
                  </div>
                ) : (
                  <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#E2E0F0', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
                    <i className="ti ti-user" style={{ fontSize: '14px', color: '#5B4EE8' }} />
                  </div>
                )}

                {/* Bubble */}
                <div style={{ maxWidth: msg.role === 'user' ? '75%' : '92%', flex: msg.role === 'user' ? '0 1 auto' : '1' }}>
                  <div style={{ fontSize: '12px', fontWeight: 500, color: '#9b9b9b', marginBottom: '4px', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                    {msg.role === 'user' ? 'You' : 'Assistant'}
                  </div>

                  {/* User message bubble */}
                  {msg.role === 'user' && (
                    <div style={{
                      fontSize: '14px', color: '#1a1a1a', lineHeight: 1.6, whiteSpace: 'pre-wrap',
                      backgroundColor: '#E2E0F0', padding: '12px 16px', borderRadius: '12px',
                    }}>
                      {msg.content}
                    </div>
                  )}

                  {/* Assistant: loading state */}
                  {msg.role === 'assistant' && !msg.content && !msg.rag && isLoading && idx === messages.length - 1 && (
                    <div style={{
                      backgroundColor: '#ffffff', padding: '14px 16px', borderRadius: '12px',
                      border: '0.5px solid rgba(0,0,0,0.08)', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                    }}>
                      <span className="rag-typing-indicator">
                        <span className="rag-dot" /><span className="rag-dot" /><span className="rag-dot" />
                      </span>
                    </div>
                  )}

                  {/* Assistant: structured RAG response */}
                  {msg.role === 'assistant' && msg.rag && msg.rag.sources && msg.rag.sources.length > 0 && (
                    <RagAnswer rag={msg.rag} expanded={expandedSources} setExpanded={setExpandedSources} msgIdx={idx} />
                  )}

                  {/* Assistant: error or plain text fallback */}
                  {msg.role === 'assistant' && msg.content && (!msg.rag || !msg.rag.sources || msg.rag.sources.length === 0) && (
                    <div style={{
                      fontSize: '14px', color: '#1a1a1a', lineHeight: 1.6, whiteSpace: 'pre-wrap',
                      backgroundColor: '#ffffff', padding: '14px 16px', borderRadius: '12px',
                      border: '0.5px solid rgba(0,0,0,0.08)', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                    }}>
                      {msg.content}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div style={{ padding: '16px 24px', backgroundColor: '#ffffff', borderTop: '1px solid rgba(0,0,0,0.08)' }}>
          <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#F5F3EE', borderRadius: '12px', padding: '4px 4px 4px 16px' }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Ask anything about your migration document..."
              disabled={isLoading}
              style={{
                flex: 1,
                border: 'none',
                backgroundColor: 'transparent',
                fontSize: '14px',
                color: '#1a1a1a',
                outline: 'none',
                padding: '10px 0',
              }}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                backgroundColor: isLoading || !input.trim() ? '#d4d2e8' : '#5B4EE8',
                color: 'white',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: isLoading || !input.trim() ? 'not-allowed' : 'pointer',
                transition: 'background-color 0.2s ease',
              }}
            >
              <i className="ti ti-send" style={{ fontSize: '18px' }} />
            </button>
          </div>
        </div>
      </section>
    </main>
  );
};


/* ══════════════════════════════════════════════════════════════
   RagAnswer — beautiful structured display of retrieved sources
   ══════════════════════════════════════════════════════════════ */
interface RagAnswerProps {
  rag: RagResponse;
  expanded: Set<string>;
  setExpanded: React.Dispatch<React.SetStateAction<Set<string>>>;
  msgIdx: number;
}

const highlightTerms = (text: string, terms: string[]): React.ReactNode => {
  if (!terms || terms.length === 0) return text;
  const pattern = new RegExp(`(${terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const isMatch = terms.some(t => t.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      return (
        <mark key={i} style={{
          backgroundColor: '#FEF3C7',
          color: '#78350F',
          padding: '1px 3px',
          borderRadius: '3px',
          fontWeight: 500,
        }}>
          {part}
        </mark>
      );
    }
    return <span key={i}>{part}</span>;
  });
};

const RagAnswer = ({ rag, expanded, setExpanded, msgIdx }: RagAnswerProps) => {
  const sources = rag.sources || [];
  const terms = rag.query_terms || [];

  const toggleSource = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const scoreColor = (pct: number) => {
    if (pct >= 70) return { bg: '#D1FAE5', text: '#065F46', label: 'High' };
    if (pct >= 40) return { bg: '#FEF3C7', text: '#92400E', label: 'Medium' };
    return { bg: '#E0E7FF', text: '#3730A3', label: 'Low' };
  };

  return (
    <div style={{
      backgroundColor: '#ffffff',
      borderRadius: '12px',
      border: '0.5px solid rgba(0,0,0,0.08)',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      overflow: 'hidden',
    }}>
      {/* Summary block */}
      {rag.summary && (
        <div style={{
          padding: '14px 18px',
          background: rag.haiku_used
            ? 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)'
            : 'linear-gradient(135deg, #F5F3FF 0%, #EEEDFE 100%)',
          borderBottom: `0.5px solid ${rag.haiku_used ? 'rgba(34,197,94,0.2)' : 'rgba(91,78,232,0.15)'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
            {rag.haiku_used ? (
              <>
                <i className="ti ti-sparkles" style={{ fontSize: '14px', color: '#16A34A' }} />
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#16A34A', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  AI Answer
                </span>
                <span style={{
                  padding: '1px 7px', borderRadius: '10px',
                  backgroundColor: '#DCFCE7', color: '#15803D',
                  fontSize: '10px', fontWeight: 600,
                }}>
                  Claude Haiku
                </span>
              </>
            ) : (
              <>
                <i className="ti ti-bulb" style={{ fontSize: '14px', color: '#5B4EE8' }} />
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#5B4EE8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Direct answer
                </span>
              </>
            )}
            <span style={{ fontSize: '11px', color: '#9b9b9b', marginLeft: 'auto' }}>
              from {rag.total} relevant section{rag.total === 1 ? '' : 's'}
            </span>
          </div>
          <div style={{ fontSize: '13.5px', color: '#1a1a1a', lineHeight: 1.6 }}>
            {highlightTerms(rag.summary, terms)}
          </div>
        </div>
      )}

      {/* Source chips bar */}
      <div style={{
        padding: '10px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        backgroundColor: '#FAFAFA',
        borderBottom: '0.5px solid rgba(0,0,0,0.06)',
        flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: '11px', color: '#6b6b6b', fontWeight: 500 }}>
          <i className="ti ti-file-search" style={{ marginRight: '4px' }} />
          Sources
        </span>
        {sources.slice(0, 8).map((src) => {
          const sc = scoreColor(src.score_pct);
          const key = `${msgIdx}-${src.id}`;
          return (
            <button
              key={src.id}
              onClick={() => toggleSource(key)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 9px',
                borderRadius: '12px',
                border: 'none',
                backgroundColor: expanded.has(key) ? '#5B4EE8' : sc.bg,
                color: expanded.has(key) ? '#ffffff' : sc.text,
                fontSize: '11px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title={src.section || `Source ${src.id}`}
            >
              [{src.id}] {src.score_pct}%
            </button>
          );
        })}
      </div>

      {/* Source cards */}
      <div style={{ padding: '8px' }}>
        {sources.map((src) => {
          const key = `${msgIdx}-${src.id}`;
          const isExpanded = expanded.has(key);
          const sc = scoreColor(src.score_pct);
          return (
            <div
              key={src.id}
              style={{
                marginBottom: '6px',
                borderRadius: '8px',
                border: '0.5px solid rgba(0,0,0,0.08)',
                backgroundColor: isExpanded ? '#FAFAFA' : '#ffffff',
                overflow: 'hidden',
                transition: 'all 0.15s ease',
              }}
            >
              {/* Card header */}
              <div
                onClick={() => toggleSource(key)}
                style={{
                  padding: '10px 14px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                }}
              >
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '22px',
                  height: '22px',
                  borderRadius: '50%',
                  backgroundColor: '#5B4EE8',
                  color: 'white',
                  fontSize: '11px',
                  fontWeight: 600,
                  flexShrink: 0,
                }}>
                  {src.id}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '12.5px', fontWeight: 500, color: '#1a1a1a', marginBottom: '2px' }}>
                    {src.section || `Section ${src.chunk_index !== null ? '#' + ((src.chunk_index ?? 0) + 1) : src.id}`}
                  </div>
                  {!isExpanded && (
                    <div style={{ fontSize: '12px', color: '#6b6b6b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {highlightTerms(src.snippet.slice(0, 140), terms)}
                      {src.snippet.length > 140 && '...'}
                    </div>
                  )}
                </div>
                <span style={{
                  padding: '2px 8px',
                  borderRadius: '10px',
                  backgroundColor: sc.bg,
                  color: sc.text,
                  fontSize: '10.5px',
                  fontWeight: 600,
                  flexShrink: 0,
                }}>
                  {sc.label} · {src.score_pct}%
                </span>
                {src.match_count > 0 && (
                  <span style={{
                    padding: '2px 6px',
                    borderRadius: '10px',
                    backgroundColor: '#FEF3C7',
                    color: '#92400E',
                    fontSize: '10.5px',
                    fontWeight: 600,
                  }}>
                    {src.match_count} match{src.match_count === 1 ? '' : 'es'}
                  </span>
                )}
                <i className={`ti ${isExpanded ? 'ti-chevron-up' : 'ti-chevron-down'}`} style={{ fontSize: '14px', color: '#9b9b9b' }} />
              </div>

              {/* Card expanded body */}
              {isExpanded && (
                <div style={{
                  padding: '0 14px 14px',
                  fontSize: '13px',
                  color: '#374151',
                  lineHeight: 1.6,
                }}>
                  <div style={{
                    padding: '10px 12px',
                    backgroundColor: '#ffffff',
                    borderLeft: '3px solid #5B4EE8',
                    borderRadius: '4px',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}>
                    {highlightTerms(src.text, terms)}
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); copyToClipboard(src.text); }}
                      style={{
                        padding: '3px 10px',
                        borderRadius: '6px',
                        border: '0.5px solid rgba(0,0,0,0.15)',
                        backgroundColor: 'white',
                        color: '#374151',
                        fontSize: '11px',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '3px',
                      }}
                    >
                      <i className="ti ti-copy" style={{ fontSize: '11px' }} /> Copy
                    </button>
                    {src.matched_terms.length > 0 && (
                      <span style={{ fontSize: '11px', color: '#6b6b6b' }}>
                        Matched: {src.matched_terms.map(t => (
                          <span key={t} style={{
                            display: 'inline-block',
                            padding: '0 6px',
                            margin: '0 2px',
                            backgroundColor: '#FEF3C7',
                            color: '#92400E',
                            borderRadius: '3px',
                            fontWeight: 500,
                          }}>
                            {t}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{
        padding: '8px 18px',
        backgroundColor: '#FAFAFA',
        borderTop: '0.5px solid rgba(0,0,0,0.06)',
        fontSize: '11px',
        color: '#9b9b9b',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}>
        <i className="ti ti-info-circle" style={{ fontSize: '12px' }} />
        <span>
          {rag.haiku_used
            ? `Answer synthesized by Claude Haiku from ${rag.total} retrieved sections of ${rag.filename || 'document'}.`
            : `Pure retrieval — content shown verbatim from ${rag.filename || 'document'}.`
          }
        </span>
      </div>
    </div>
  );
};
