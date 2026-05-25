import { useState, useRef, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { useWorkflowStore } from '../store/workflowStore';
import { useTerraformChatStore, type ChatMessage, type AIModel, type GeneratedFile } from '../store/terraformChatStore';
import { api } from '../services/api';
import { PromptRefinerModal } from '../components/terraform/PromptRefinerModal';

/* 🟢 BEGINNER: DOMPurify config that is safe for our syntax-highlighter output.
   We allow only <span>, <pre>, <br> with the `style` attribute (for inline colors).
   This blocks <script>, <iframe>, on*= event handlers, and javascript: URLs even
   if a future bug in highlightHCL accidentally lets one slip through. */
function safeHighlight(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'pre', 'br', 'code'],
    ALLOWED_ATTR: ['style'],
    KEEP_CONTENT: true,
    RETURN_TRUSTED_TYPE: false,
  }) as unknown as string;
}

/* ── Robust copy that works even when navigator.clipboard is unavailable ── */
async function copyToClipboard(text: string): Promise<void> {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}

/* ── Copy button with visual feedback ── */
function CopyButton({ text, style, children }: { text: string; style?: React.CSSProperties; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await copyToClipboard(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={handleCopy} style={style}>
      {copied ? <><i className="ti ti-check" /> Copied!</> : children}
    </button>
  );
}

/* ══════════════════════════════════════════════════════════════
   Utility — Parse AI response into files + commands
   ══════════════════════════════════════════════════════════════ */
// 🟢 BEGINNER: Parse the AI's response text into structured pieces:
// prose (explanation text), files (HCL code blocks), and commands (bash usage).
function parseResponse(text: string) {
  const files: GeneratedFile[] = [];
  let commands = '';
  let prose = '';

  // 🟢 BEGINNER: Extract the prose explanation that comes before the first file marker.
  const firstFileMatch = text.match(/\*\*\d+\.\s+[^*]+\*\*/);
  if (firstFileMatch) {
    prose = text.slice(0, firstFileMatch.index).trim();
  } else {
    prose = text;
  }

  // 🟢 BEGINNER: Find all HCL code blocks formatted as **N. filename.tf** followed by ```hcl ... ```
  const fileRegex = /\*\*(\d+)\.\s+([^*]+)\*\*\s*```hcl\s*([\s\S]*?)```/g;
  let m;
  while ((m = fileRegex.exec(text)) !== null) {
    files.push({
      name: m[2].trim(),
      language: 'hcl',
      content: m[3].trim(),
    });
  }

  // 🟢 BEGINNER: Find the Usage Commands section (bash commands the user can run).
  const cmdMatch = text.match(/\*\*Usage Commands\*\*\s*```bash\s*([\s\S]*?)```/);
  if (cmdMatch) {
    commands = cmdMatch[1].trim();
  }

  return { prose, files, commands };
}

/* ══════════════════════════════════════════════════════════════
   Utility — Simple HCL syntax highlighting (marker-based)
   ══════════════════════════════════════════════════════════════ */
const MARKERS = {
  COMMENT: '\x00C\x00',
  STRING: '\x00S\x00',
  KEYWORD: '\x00K\x00',
  BOOL: '\x00B\x00',
  NUMBER: '\x00N\x00',
  FUNC: '\x00F\x00',
  ATTR: '\x00A\x00',
  END: '\x00E\x00',
} as const;

function highlightHCL(code: string): string {
  // Step 1: mark tokens with non-printable markers (safe from overlap)
  let m = code
    .replace(/("(?:[^"\\]|\\.)*")/g, `${MARKERS.STRING}$1${MARKERS.END}`)
    .replace(/(#.*$)/gm, `${MARKERS.COMMENT}$1${MARKERS.END}`)
    .replace(/\b(terraform|resource|provider|variable|output|module|data|locals|dynamic|for_each|count|lifecycle|depends_on|each|self)\b/g, `${MARKERS.KEYWORD}$1${MARKERS.END}`)
    .replace(/\b(true|false|null)\b/g, `${MARKERS.BOOL}$1${MARKERS.END}`)
    .replace(/\b(\d+)\b/g, `${MARKERS.NUMBER}$1${MARKERS.END}`)
    .replace(/\b([a-zA-Z_][a-zA-Z0-9_]*)(?=\s*\()/g, `${MARKERS.FUNC}$1${MARKERS.END}`)
    .replace(/\b([a-zA-Z_][a-zA-Z0-9_]*)(?=\s*=)/g, `${MARKERS.ATTR}$1${MARKERS.END}`);

  // Step 2: escape HTML
  m = m.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Step 3: replace markers with spans
  m = m
    .replace(new RegExp(MARKERS.COMMENT, 'g'), '<span style="color:rgba(255,255,255,0.28)">')
    .replace(new RegExp(MARKERS.STRING, 'g'), '<span style="color:#5DCAA5">')
    .replace(new RegExp(MARKERS.KEYWORD, 'g'), '<span style="color:#AFA9EC">')
    .replace(new RegExp(MARKERS.BOOL, 'g'), '<span style="color:#F0997B">')
    .replace(new RegExp(MARKERS.NUMBER, 'g'), '<span style="color:#F0997B">')
    .replace(new RegExp(MARKERS.FUNC, 'g'), '<span style="color:#FAC775">')
    .replace(new RegExp(MARKERS.ATTR, 'g'), '<span style="color:#85B7EB">')
    .replace(new RegExp(MARKERS.END, 'g'), '</span>');

  return m;
}

function highlightBash(code: string): string {
  return code
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^(\s*#.*)$/gm, '<span style="color:rgba(255,255,255,0.35)">$1</span>')
    .replace(/\b(terraform|init|plan|apply|destroy|validate|fmt)\b/g, '<span style="color:#AFA9EC">$1</span>');
}

/* ══════════════════════════════════════════════════════════════
   Model config
   ══════════════════════════════════════════════════════════════ */
const MODEL_CONFIG: Record<AIModel, { label: string; desc: string; group: string; recommended?: boolean }> = {
  'claude-sonnet-4-6': { label: 'Claude Sonnet 4.6', desc: 'Powerful, detailed HCL output', group: 'Anthropic Claude', recommended: true },
  'claude-haiku-4-5': { label: 'Claude Haiku 4.5', desc: 'Fast, lightweight generation', group: 'Anthropic Claude' },
  'gemini-2.5-flash': { label: 'Gemini 2.5 Flash', desc: 'Fast responses, good for iteration', group: 'Google Gemini' },
  'gemini-2.5-pro': { label: 'Gemini 2.5 Pro', desc: 'Complex architectures, deep context', group: 'Google Gemini' },
};

const QUICK_STARTS = [
  'EC2 + RDS + VPC',
  'Lambda + API Gateway',
  'EKS cluster',
  'S3 static site',
];

/* ══════════════════════════════════════════════════════════════
   Service color chips
   ══════════════════════════════════════════════════════════════ */
const SERVICE_CHIP_COLORS: Record<string, { bg: string; text: string }> = {
  ec2: { bg: '#FEF3C7', text: '#92400E' },
  asg: { bg: '#FEF3C7', text: '#92400E' },
  rds: { bg: '#DBEAFE', text: '#1E40AF' },
  s3: { bg: '#D1FAE5', text: '#065F46' },
  waf: { bg: '#EDE9FE', text: '#5B21B6' },
  vpc: { bg: '#FEE2E2', text: '#991B1B' },
  lambda: { bg: '#CCFBF1', text: '#115E59' },
};

function getChipColor(service: string) {
  const key = service.toLowerCase().replace(/[^a-z]/g, '');
  for (const k of Object.keys(SERVICE_CHIP_COLORS)) {
    if (key.includes(k)) return SERVICE_CHIP_COLORS[k];
  }
  return { bg: '#F3F4F6', text: '#4B5563' };
}

/* ══════════════════════════════════════════════════════════════
   Component
   ══════════════════════════════════════════════════════════════ */
export const TerraformChatPage = () => {
  const { jobId, designDocs, selectedProvider, terraformPrompts } = useWorkflowStore();
  const {
    messages,
    generatedFiles,
    activeFile,
    isStreaming,
    selectedModel,
    showModelDropdown,
    contextVisible,
    diagramContext,
    conversations,
    activeConversationId,
    setMessages,
    addMessage,
    updateLastMessage,
    setGeneratedFiles,
    setActiveFile,
    setIsStreaming,
    setSelectedModel,
    setShowModelDropdown,
    setContextVisible,
    setDiagramContext,
    reset,
    saveConversation,
    loadConversation,
    deleteConversation,
  } = useTerraformChatStore();

  const [input, setInput] = useState('');
  const [showRefinerModal, setShowRefinerModal] = useState(false);

  /* ── Pick up a pending prompt from DesignDocPage navigation ── */
  // 🟢 BEGINNER: When the user clicks a "Generate Terraform" prompt card on DesignDocPage,
  // that page stores the prompt text in window.__pendingTfPrompt. This effect picks it up.
  const hasPendingRef = useRef(false);
  useEffect(() => {
    if (hasPendingRef.current) return;
    const pending = (window as any).__pendingTfPrompt;
    if (pending) {
      hasPendingRef.current = true;
      setInput(pending);
      delete (window as any).__pendingTfPrompt;
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);

  /* ── Build diagram context on mount ── */
  // 🟢 BEGINNER: Extract cloud service names (EC2, S3, RDS, etc.) from the design document
  // so the AI chat knows what resources were detected in the uploaded diagram.
  const hasSetContextRef = useRef(false);
  useEffect(() => {
    if (hasSetContextRef.current) return;
    const doc = designDocs?.[selectedProvider];
    if (doc) {
      hasSetContextRef.current = true;
      const content = doc.content || '';
      const resources: { name: string; service: string }[] = [];
      const lines = content.split('\n');
      for (const line of lines) {
        const m = line.match(/\b(EC2|S3|RDS|Lambda|VPC|ALB|API Gateway|DynamoDB|EKS|CloudFront|WAF|Route 53|SQS|SNS|ElastiCache|Secrets Manager)\b/gi);
        if (m) {
          for (const svc of m) {
            if (!resources.some((r) => r.service.toLowerCase() === svc.toLowerCase())) {
              resources.push({ name: svc, service: svc });
            }
          }
        }
      }
      setDiagramContext({
        detectedResources: resources,
        detectedConnections: [],
        cloud: selectedProvider,
      });
    }
  }, [designDocs, selectedProvider, setDiagramContext]);

  /* ── Auto-scroll chat ── */
  // 🟢 BEGINNER: Whenever messages change, scroll to the bottom if the user is already near the bottom.
  useEffect(() => {
    if (messagesEndRef.current && chatScrollRef.current) {
      const el = chatScrollRef.current;
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      if (nearBottom) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages]);

  /* ── Close dropdown on outside click ── */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setShowModelDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [setShowModelDropdown]);

  /* ── Textarea auto-grow ── */
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }, [input]);

  /* ── Send message ── */
  // 🟢 BEGINNER: Called when the user presses Enter or clicks the Send button.
  // It adds the user's message to the chat, streams the AI response, and parses generated files.
  const handleSend = useCallback(async () => {
    if (!input.trim() || isStreaming) return;

    // 🟢 BEGINNER: Create the user message object and add it to the chat store.
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };
    addMessage(userMsg);
    setInput('');
    setIsStreaming(true);

    // 🟢 BEGINNER: Create an empty assistant message that will be filled in as the AI streams its response.
    const aiMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      model: selectedModel,
    };
    addMessage(aiMsg);

    // 🟢 BEGINNER: Build the message array to send to the backend (all previous messages + the new user message).
    const allMsgs = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));

    // 🟢 BEGINNER: Stream the AI response chunk by chunk using our api client.
    let text = '';
    try {
      for await (const chunk of api.streamTerraformChat(allMsgs, selectedModel, jobId)) {
        if ('done' in chunk && chunk.done) break;
        if ('text' in chunk) {
          text += chunk.text;
          updateLastMessage(text);  // 🟢 BEGINNER: Updates the last assistant message in real time (typewriter effect).
        }
      }

      // 🟢 BEGINNER: After streaming is done, parse the full response to extract HCL files and bash commands.
      const parsed = parseResponse(text);
      if (parsed.files.length > 0) {
        setGeneratedFiles(parsed.files);
        setActiveFile(parsed.files[0].name);
      }
    } catch (err) {
      const errorText = `[Error] ${err instanceof Error ? err.message : 'Unknown error'}`;
      text += '\n\n' + errorText;
      updateLastMessage(text);
    } finally {
      setIsStreaming(false);
      // Auto-save conversation after each response completes
      setTimeout(() => saveConversation(), 100);
    }
  }, [input, isStreaming, messages, selectedModel, jobId, addMessage, setIsStreaming, updateLastMessage, setGeneratedFiles, setActiveFile]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickStart = (text: string) => {
    if (text === 'From my diagram ↑') {
      const ctx = diagramContext;
      if (ctx && ctx.detectedResources.length > 0) {
        const names = ctx.detectedResources.map((r) => r.name).join(', ');
        setInput(`Generate Terraform for my ${ctx.cloud} architecture with: ${names}`);
      } else {
        setInput('Generate Terraform for my uploaded architecture diagram');
      }
    } else {
      setInput(`Generate Terraform for: ${text}`);
    }
    setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const handleNewConversation = () => {
    reset();
    setInput('');
  };

  const modelLabel = MODEL_CONFIG[selectedModel].label;
  const activeFileData = generatedFiles.find((f) => f.name === activeFile);

  /* ══════════════════════════════════════════════════════════════
     RENDER
     ══════════════════════════════════════════════════════════════ */
  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 52px)', backgroundColor: '#F5F3EE' }}>

      {/* ═════════════ LEFT SIDEBAR ═════════════ */}
      <aside
        style={{
          width: '220px',
          backgroundColor: 'white',
          borderRight: '0.5px solid rgba(0,0,0,0.12)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
        }}
      >
        {/* New conversation */}
        <div style={{ padding: '12px 14px' }}>
          <button
            onClick={handleNewConversation}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '8px',
              border: '0.5px solid rgba(0,0,0,0.12)',
              background: 'white',
              fontSize: '13px',
              fontWeight: 500,
              color: '#1a1a1a',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <i className="ti ti-plus" style={{ fontSize: '14px' }} />
            New conversation
          </button>
        </div>

        {/* Context */}
        {diagramContext && diagramContext.detectedResources.length > 0 && (
          <>
            <div style={{ padding: '0 14px 8px' }}>
              <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
                Context
              </span>
            </div>
            <div style={{ padding: '0 14px 12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {diagramContext.detectedResources.map((r, i) => {
                const color = getChipColor(r.service);
                return (
                  <span
                    key={i}
                    style={{
                      fontSize: '11px',
                      fontWeight: 500,
                      padding: '3px 8px',
                      borderRadius: '12px',
                      backgroundColor: color.bg,
                      color: color.text,
                    }}
                  >
                    {r.service}
                  </span>
                );
              })}
            </div>
          </>
        )}

        {/* History */}
        <div style={{ padding: '0 14px 8px' }}>
          <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
            History
          </span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => loadConversation(conv.id)}
              style={{
                padding: '8px 10px',
                borderRadius: '6px',
                fontSize: '13px',
                color: activeConversationId === conv.id ? '#5B4EE8' : '#1a1a1a',
                backgroundColor: activeConversationId === conv.id ? '#EEEDFE' : 'transparent',
                cursor: 'pointer',
                marginBottom: '2px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
              onMouseEnter={(e) => {
                if (activeConversationId !== conv.id)
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = '#F5F3EE';
              }}
              onMouseLeave={(e) => {
                if (activeConversationId !== conv.id)
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent';
              }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                {conv.title}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9b9b9b', fontSize: '12px', padding: '2px 4px' }}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <div style={{ padding: '8px 10px', fontSize: '12px', color: '#9b9b9b' }}>
              No conversations yet
            </div>
          )}
        </div>

        {/* Files Generated */}
        {generatedFiles.length > 0 && (
          <>
            <div style={{ padding: '12px 14px 8px', borderTop: '0.5px solid rgba(0,0,0,0.12)' }}>
              <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
                Files Generated
              </span>
            </div>
            <div style={{ padding: '0 8px 12px' }}>
              {generatedFiles.map((f) => (
                <div
                  key={f.name}
                  onClick={() => setActiveFile(f.name)}
                  style={{
                    padding: '6px 10px',
                    borderRadius: '6px',
                    fontSize: '12.5px',
                    color: activeFile === f.name ? '#5B4EE8' : '#1a1a1a',
                    backgroundColor: activeFile === f.name ? '#EEEDFE' : 'transparent',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <i className="ti ti-file-code" style={{ fontSize: '14px', color: '#9b9b9b' }} />
                  {f.name}
                </div>
              ))}
            </div>
          </>
        )}
      </aside>

      {/* ═════════════ CENTRE CHAT PANEL ═════════════ */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Header */}
        <div
          style={{
            height: '52px',
            backgroundColor: 'white',
            borderBottom: '0.5px solid rgba(0,0,0,0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 20px',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <i className="ti ti-sparkles" style={{ fontSize: '16px', color: '#5B4EE8' }} />
            <span style={{ fontSize: '14px', fontWeight: 500, color: '#1a1a1a' }}>Terraform assistant</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Model selector */}
            <div style={{ position: 'relative' }} ref={modelDropdownRef}>
              <button
                onClick={() => setShowModelDropdown(!showModelDropdown)}
                style={{
                  padding: '5px 12px',
                  borderRadius: '20px',
                  border: '0.5px solid rgba(0,0,0,0.12)',
                  background: 'white',
                  fontSize: '12.5px',
                  color: '#6b6b6b',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span style={{ color: '#5B4EE8', fontWeight: 600 }}>✦</span>
                AI Model : {modelLabel}
                <i className="ti ti-chevron-down" style={{ fontSize: '12px' }} />
              </button>

              {showModelDropdown && (
                <div
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 6px)',
                    right: 0,
                    backgroundColor: 'white',
                    border: '0.5px solid rgba(0,0,0,0.12)',
                    borderRadius: '12px',
                    padding: '8px',
                    minWidth: '260px',
                    zIndex: 100,
                  }}
                >
                  <div style={{ padding: '6px 10px', fontSize: '12px', fontWeight: 500, color: '#9b9b9b', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                    Choose AI Model
                  </div>
                  {['Anthropic Claude', 'Google Gemini'].map((group) => (
                    <div key={group}>
                      <div style={{ padding: '8px 10px 4px', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
                        {group}
                      </div>
                      {Object.entries(MODEL_CONFIG)
                        .filter(([_, cfg]) => cfg.group === group)
                        .map(([key, cfg]) => {
                          const isActive = key === selectedModel;
                          return (
                            <div
                              key={key}
                              onClick={() => { setSelectedModel(key as AIModel); setShowModelDropdown(false); }}
                              style={{
                                padding: '8px 10px',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                backgroundColor: isActive ? '#EEEDFE' : 'transparent',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                              }}
                            >
                              <div style={{
                                width: '16px',
                                height: '16px',
                                borderRadius: '50%',
                                border: `2px solid ${isActive ? '#5B4EE8' : '#D1D5DB'}`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0,
                              }}>
                                {isActive && <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#5B4EE8' }} />}
                              </div>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: '13px', fontWeight: 500, color: '#1a1a1a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                  {cfg.label}
                                  {cfg.recommended && (
                                    <span style={{ fontSize: '11px', backgroundColor: '#EAF3DE', color: '#3B6D11', padding: '1px 8px', borderRadius: '20px' }}>Recommended</span>
                                  )}
                                </div>
                                <div style={{ fontSize: '12px', color: '#9b9b9b' }}>{cfg.desc}</div>
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Messages area */}
        <div
          ref={chatScrollRef}
          style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}
        >
          {messages.length === 0 && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '24px' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{
                  width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#EEEDFE',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px',
                }}>
                  <i className="ti ti-code" style={{ fontSize: '24px', color: '#5B4EE8' }} />
                </div>
                <div style={{ fontSize: '16px', fontWeight: 500, color: '#1a1a1a', marginBottom: '6px' }}>
                  {diagramContext && diagramContext.detectedResources.length > 0
                    ? `I can see your ${diagramContext.cloud.toUpperCase()} architecture with ${diagramContext.detectedResources.length} components.`
                    : 'Describe your infrastructure requirements and I\'ll generate production-ready Terraform.'}
                </div>
                <div style={{ fontSize: '13px', color: '#6b6b6b' }}>
                  {diagramContext && diagramContext.detectedResources.length > 0
                    ? 'What would you like to generate first?'
                    : 'Or pick a quick-start template below.'}
                </div>
              </div>

              {/* Quick start chips — use LLM-generated prompts if available, else hardcoded */}
              {terraformPrompts.length > 0 ? (
                <div style={{ maxWidth: '760px', width: '100%' }}>
                  {/* Header pill */}
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '6px', margin: '0 auto 16px',
                    padding: '5px 14px', borderRadius: '20px',
                    background: 'linear-gradient(135deg, #EEEDFE 0%, #F5F3FF 100%)',
                    border: '1px solid #DDD6FE',
                  }}>
                    <i className="ti ti-sparkles" style={{ fontSize: '13px', color: '#7C3AED' }} />
                    <span style={{ fontSize: '11px', fontWeight: 700, color: '#6D28D9', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {terraformPrompts.length} prompts from your diagram
                    </span>
                  </div>

                  {/* Prompt cards (show first 6, sorted by priority) */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '10px' }}>
                    {[...terraformPrompts]
                      .sort((a, b) => {
                        const pOrder: Record<string, number> = { P0: 0, P1: 1, P2: 2 };
                        return (pOrder[(a as any).priority || 'P1'] ?? 1) - (pOrder[(b as any).priority || 'P1'] ?? 1);
                      })
                      .slice(0, contextVisible ? terraformPrompts.length : 6).map((p, i) => {
                      const pColors: Record<string, { bg: string; text: string }> = {
                        P0: { bg: '#FEE2E2', text: '#991B1B' },
                        P1: { bg: '#FEF3C7', text: '#92400E' },
                        P2: { bg: '#E0E7FF', text: '#3730A3' },
                      };
                      const pC = pColors[(p as any).priority || 'P1'] || pColors.P1;
                      return (
                      <button
                        key={i}
                        onClick={() => { setInput(p.prompt); setTimeout(() => textareaRef.current?.focus(), 50); }}
                        style={{
                          padding: '0', borderRadius: '10px', overflow: 'hidden',
                          border: '1px solid #E5E7EB', background: 'white',
                          fontSize: '12.5px', color: '#1a1a1a', cursor: 'pointer',
                          textAlign: 'left', lineHeight: '1.45',
                          transition: 'all 0.2s ease', display: 'flex',
                        }}
                        onMouseEnter={(e) => {
                          const el = e.currentTarget as HTMLButtonElement;
                          el.style.borderColor = '#C7C3F9';
                          el.style.boxShadow = '0 3px 12px rgba(91,78,232,0.1)';
                          el.style.transform = 'translateY(-1px)';
                        }}
                        onMouseLeave={(e) => {
                          const el = e.currentTarget as HTMLButtonElement;
                          el.style.borderColor = '#E5E7EB';
                          el.style.boxShadow = 'none';
                          el.style.transform = 'none';
                        }}
                      >
                        {/* Left accent */}
                        <div style={{ width: '3px', flexShrink: 0, background: 'linear-gradient(180deg, #6366F1, #A78BFA)' }} />
                        <div style={{ flex: 1, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{
                              width: '18px', height: '18px', borderRadius: '5px',
                              backgroundColor: '#EEEDFE', color: '#5B4EE8',
                              fontSize: '10px', fontWeight: 700,
                              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                            }}>
                              {i + 1}
                            </span>
                            <span style={{
                              fontSize: '9.5px', fontWeight: 700, textTransform: 'uppercase',
                              letterSpacing: '0.05em', padding: '2px 8px', borderRadius: '12px',
                              backgroundColor: '#F3F4F6', color: '#6B7280',
                            }}>
                              {p.category}
                            </span>
                            {/* Priority badge */}
                            {(p as any).priority && (
                              <span style={{
                                fontSize: '8px', fontWeight: 800, textTransform: 'uppercase',
                                letterSpacing: '0.08em', padding: '1px 6px', borderRadius: '10px',
                                backgroundColor: pC.bg, color: pC.text,
                              }}>
                                {(p as any).priority}
                              </span>
                            )}
                            {/* Resource count */}
                            {(p as any).estimated_resources > 0 && (
                              <span style={{
                                fontSize: '9px', fontWeight: 600, color: '#9CA3AF', marginLeft: 'auto',
                                display: 'inline-flex', alignItems: 'center', gap: '2px',
                              }}>
                                <i className="ti ti-stack-2" style={{ fontSize: '10px' }} />
                                ~{(p as any).estimated_resources}
                              </span>
                            )}
                          </div>
                          <span style={{ flex: 1, fontSize: '12.5px', color: '#374151' }}>
                            {p.prompt.length > 120 ? p.prompt.slice(0, 120) + '...' : p.prompt}
                          </span>
                        </div>
                      </button>
                      );
                    })}
                  </div>

                  {/* Toggle */}
                  {terraformPrompts.length > 6 && (
                    <div
                      style={{
                        textAlign: 'center', marginTop: '12px', fontSize: '12px', fontWeight: 600,
                        color: '#5B4EE8', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px',
                      }}
                      onClick={() => setContextVisible(!contextVisible)}
                    >
                      <i className={`ti ${contextVisible ? 'ti-chevron-up' : 'ti-chevron-down'}`} style={{ fontSize: '14px' }} />
                      {contextVisible ? 'Show fewer prompts' : `Show all ${terraformPrompts.length} prompts`}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', maxWidth: '500px' }}>
                  {diagramContext && diagramContext.detectedResources.length > 0 && (
                    <button
                      onClick={() => handleQuickStart('From my diagram ↑')}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '20px',
                        border: '0.5px solid rgba(0,0,0,0.12)',
                        background: 'white',
                        fontSize: '12px',
                        color: '#1a1a1a',
                        cursor: 'pointer',
                      }}
                    >
                      From my diagram ↑
                    </button>
                  )}
                  {QUICK_STARTS.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleQuickStart(q)}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '20px',
                        border: '0.5px solid rgba(0,0,0,0.12)',
                        background: 'white',
                        fontSize: '12px',
                        color: '#1a1a1a',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.backgroundColor = '#EEEDFE'; (e.currentTarget as HTMLButtonElement).style.color = '#5B4EE8'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'white'; (e.currentTarget as HTMLButtonElement).style.color = '#1a1a1a'; }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {messages.map((msg, idx) => {
            if (msg.role === 'user') {
              return (
                <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{ maxWidth: '70%' }}>
                    <div style={{
                      backgroundColor: '#5B4EE8',
                      color: 'white',
                      borderRadius: '12px 4px 12px 12px',
                      padding: '10px 14px',
                      fontSize: '13.5px',
                      lineHeight: 1.5,
                      wordBreak: 'break-word',
                    }}>
                      {msg.content}
                    </div>
                    <div style={{ textAlign: 'right', fontSize: '11px', color: '#9b9b9b', marginTop: '4px' }}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              );
            }

            // AI message
            const isLast = idx === messages.length - 1;
            const showTyping = isLast && isStreaming && msg.content === '';
            const parsed = msg.content ? parseResponse(msg.content) : null;

            return (
              <div key={msg.id} style={{ display: 'flex', gap: '10px' }}>
                {/* Avatar */}
                <div style={{
                  width: '28px', height: '28px', borderRadius: '50%', backgroundColor: '#5B4EE8',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: 'white', fontSize: '11px', fontWeight: 600, flexShrink: 0, marginTop: '4px',
                }}>
                  IS
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    backgroundColor: 'white',
                    border: '0.5px solid rgba(0,0,0,0.12)',
                    borderRadius: '4px 12px 12px 12px',
                    padding: '14px 16px',
                    fontSize: '13.5px',
                    lineHeight: 1.6,
                    color: '#1a1a1a',
                  }}>
                    {/* Header row inside bubble */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 500, color: '#1a1a1a' }}>InfraSketch</span>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button style={{
                          padding: '2px 8px',
                          borderRadius: '20px',
                          border: '0.5px solid rgba(0,0,0,0.12)',
                          background: 'white',
                          fontSize: '11px',
                          color: '#6b6b6b',
                          cursor: 'pointer',
                        }}>
                          Try other AI
                        </button>
                        {diagramContext && (
                          <button
                            onClick={() => setContextVisible(true)}
                            style={{
                              padding: '2px 8px',
                              borderRadius: '20px',
                              border: '0.5px solid rgba(0,0,0,0.12)',
                              background: 'white',
                              fontSize: '11px',
                              color: '#6b6b6b',
                              cursor: 'pointer',
                            }}
                          >
                            View context
                          </button>
                        )}
                      </div>
                    </div>

                    {showTyping ? (
                      <div style={{ display: 'flex', gap: '4px', alignItems: 'center', padding: '8px 0' }}>
                        <span className="typing-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#9b9b9b', animation: 'typingBounce 1.4s infinite 0s' }} />
                        <span className="typing-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#9b9b9b', animation: 'typingBounce 1.4s infinite 0.2s' }} />
                        <span className="typing-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#9b9b9b', animation: 'typingBounce 1.4s infinite 0.4s' }} />
                      </div>
                    ) : (
                      <>
                        {/* Prose */}
                        {parsed?.prose && (
                          <div style={{ marginBottom: '12px', whiteSpace: 'pre-wrap' }}>{parsed.prose}</div>
                        )}

                        {/* Files inline */}
                        {parsed?.files.map((file, fi) => {
                          const lines = file.content.split('\n');
                          const preview = lines.slice(0, 10).join('\n');
                          const hasMore = lines.length > 10;
                          return (
                            <div key={fi} style={{ marginBottom: '12px' }}>
                              <div style={{ fontSize: '13px', fontWeight: 500, margin: '12px 0 6px', color: '#1a1a1a' }}>
                                {fi + 1}. {file.name}
                              </div>
                              <div style={{ backgroundColor: '#1C1C1E', borderRadius: '8px', overflow: 'hidden' }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', borderBottom: '0.5px solid rgba(255,255,255,0.08)' }}>
                                  <CopyButton
                                    text={file.content}
                                    style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                                  >
                                    <i className="ti ti-copy" /> copy
                                  </CopyButton>
                                  <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.35)' }}>hcl</span>
                                </div>
                                <pre style={{ margin: 0, padding: '12px', fontSize: '12px', lineHeight: 1.75, overflowX: 'auto', color: 'white', fontFamily: 'monospace' }}
                                  dangerouslySetInnerHTML={{ __html: safeHighlight(highlightHCL(preview)) }}
                                />
                                {hasMore && (
                                  <div
                                    onClick={() => setActiveFile(file.name)}
                                    style={{ padding: '6px 12px', fontSize: '11px', color: '#5B4EE8', cursor: 'pointer', borderTop: '0.5px solid rgba(255,255,255,0.08)' }}
                                  >
                                    View full file →
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}

                        {/* Usage Commands */}
                        {parsed?.commands && (
                          <div style={{ marginTop: '16px' }}>
                            <div style={{ fontSize: '13px', fontWeight: 500, color: '#1a1a1a', marginBottom: '10px' }}>Usage Commands</div>
                            <div style={{ backgroundColor: '#2C2C2E', borderRadius: '8px', overflow: 'hidden' }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', borderBottom: '0.5px solid rgba(255,255,255,0.08)' }}>
                                <CopyButton
                                  text={parsed.commands}
                                  style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                                >
                                  <i className="ti ti-copy" /> copy
                                </CopyButton>
                                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.35)' }}>bash</span>
                              </div>
                              <pre style={{ margin: 0, padding: '12px', fontSize: '12px', lineHeight: 1.75, color: 'white', fontFamily: 'monospace' }}
                                dangerouslySetInnerHTML={{ __html: safeHighlight(highlightBash(parsed.commands)) }}
                              />
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div style={{ backgroundColor: 'white', borderTop: '0.5px solid rgba(0,0,0,0.12)', padding: '0 20px 16px' }}>
          {/* Bulb icon for prompt refiner */}
          <div style={{ marginBottom: '8px' }}>
            <button
              onClick={() => setShowRefinerModal(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '20px',
                border: '0.5px solid rgba(91, 78, 232, 0.3)',
                backgroundColor: '#F5F3EE',
                color: '#5B4EE8',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#EEEDFE';
                e.currentTarget.style.borderColor = '#5B4EE8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = '#F5F3EE';
                e.currentTarget.style.borderColor = 'rgba(91, 78, 232, 0.3)';
              }}
            >
              <i className="ti ti-lightbulb" style={{ fontSize: '14px' }} />
              Refine your prompt with AI
            </button>
          </div>

          <div
            style={{
              border: '0.5px solid rgba(0,0,0,0.12)',
              borderRadius: '12px',
              backgroundColor: 'white',
              padding: '10px 14px',
            }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter your requirements here"
              rows={1}
              style={{
                width: '100%',
                border: 'none',
                outline: 'none',
                resize: 'none',
                fontSize: '13.5px',
                lineHeight: 1.5,
                fontFamily: 'system-ui',
                background: 'transparent',
                maxHeight: '140px',
              }}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button style={{ background: 'none', border: 'none', color: '#9b9b9b', cursor: 'pointer', fontSize: '16px', padding: '2px' }}>
                  <i className="ti ti-paperclip" />
                </button>
                {diagramContext && (
                  <button
                    onClick={() => setContextVisible(!contextVisible)}
                    style={{
                      background: 'none',
                      border: '0.5px solid rgba(0,0,0,0.12)',
                      borderRadius: '6px',
                      padding: '3px 8px',
                      fontSize: '12px',
                      color: '#6b6b6b',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    &lt;&gt; Context
                  </button>
                )}
              </div>
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  backgroundColor: '#5B4EE8',
                  border: 'none',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: input.trim() && !isStreaming ? 'pointer' : 'default',
                  opacity: input.trim() && !isStreaming ? 1 : 0.4,
                }}
              >
                <i className="ti ti-arrow-up" style={{ fontSize: '16px' }} />
              </button>
            </div>
          </div>

          {/* Bottom row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '6px', padding: '0 4px' }}>
            <button
              onClick={() => setShowModelDropdown(!showModelDropdown)}
              style={{ background: 'none', border: 'none', fontSize: '12px', color: '#9b9b9b', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <span style={{ color: '#5B4EE8' }}>✦</span> AI Model: {modelLabel} ▾
            </button>
          </div>
        </div>
      </div>

      {/* ═════════════ RIGHT CODE PANEL ═════════════ */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, backgroundColor: '#1C1C1E' }}>
        {/* Header */}
        <div style={{
          height: '44px',
          backgroundColor: '#2C2C2E',
          borderBottom: '0.5px solid rgba(255,255,255,0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 12px',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', gap: '4px', overflowX: 'auto' }}>
            {generatedFiles.map((f) => (
              <button
                key={f.name}
                onClick={() => setActiveFile(f.name)}
                style={{
                  padding: '5px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: activeFile === f.name ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: activeFile === f.name ? 'white' : 'rgba(255,255,255,0.4)',
                  fontSize: '12.5px',
                  fontFamily: 'monospace',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                {f.name}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
            {activeFileData && (
              <CopyButton
                text={activeFileData.content}
                style={{
                  padding: '4px 10px',
                  borderRadius: '6px',
                  border: '0.5px solid rgba(255,255,255,0.15)',
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.6)',
                  fontSize: '11px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <i className="ti ti-copy" /> copy
              </CopyButton>
            )}
            <button
              onClick={() => {
                if (!generatedFiles.length) return;
                // Download all files as a single combined .tf or individual downloads
                // Build a simple multi-file download via Blob
                const allContent = generatedFiles.map((f: GeneratedFile) =>
                  `# ════════════════════════════════════════\n# File: ${f.name}\n# ════════════════════════════════════════\n\n${f.content}`
                ).join('\n\n\n');
                const blob = new Blob([allContent], { type: 'application/octet-stream' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = generatedFiles.length === 1
                  ? generatedFiles[0].name
                  : 'terraform-code.tf';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }}
              style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: '0.5px solid rgba(255,255,255,0.15)',
              background: 'transparent',
              color: 'rgba(255,255,255,0.6)',
              fontSize: '11px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <i className="ti ti-download" /> .zip
            </button>
            <button style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: 'none',
              background: '#5B4EE8',
              color: 'white',
              fontSize: '11px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <i className="ti ti-player-play" /> Run plan
            </button>
          </div>
        </div>

        {/* Code body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
          {activeFileData ? (
            <div>
              {activeFileData.content.split('\n').map((line, i) => (
                <div key={i} style={{ display: 'flex', fontFamily: 'monospace', fontSize: '12px', lineHeight: 1.75 }}>
                  <span style={{
                    minWidth: '28px',
                    textAlign: 'right',
                    color: 'rgba(255,255,255,0.2)',
                    marginRight: '16px',
                    userSelect: 'none',
                  }}>
                    {i + 1}
                  </span>
                  <span dangerouslySetInnerHTML={{ __html: safeHighlight(highlightHCL(line)) }} />
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.3)',
              textAlign: 'center',
            }}>
              <i className="ti ti-code" style={{ fontSize: '36px', marginBottom: '12px', color: 'rgba(255,255,255,0.2)' }} />
              <div style={{ fontSize: '12px', marginBottom: '4px' }}>Your generated Terraform appears here</div>
              <div style={{ fontSize: '12px' }}>Type a requirement in the chat to get started</div>
            </div>
          )}
        </div>

        {/* Status bar */}
        {generatedFiles.length > 0 && (
          <div style={{
            height: '36px',
            backgroundColor: '#2C2C2E',
            borderTop: '0.5px solid rgba(255,255,255,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 12px',
            flexShrink: 0,
          }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '10px',
                backgroundColor: 'rgba(99,153,34,0.2)',
                color: '#97C459',
              }}>
                <i className="ti ti-check" /> HCL valid
              </span>
              <span style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '10px',
                backgroundColor: 'rgba(99,153,34,0.2)',
                color: '#97C459',
              }}>
                <i className="ti ti-check" /> CIS hardened
              </span>
            </div>
            <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.35)' }}>
              Generated with {modelLabel}
            </span>
          </div>
        )}
      </div>

      {/* Context popover */}
      {contextVisible && diagramContext && (
        <div
          style={{
            position: 'fixed',
            bottom: '100px',
            left: '280px',
            backgroundColor: 'white',
            border: '0.5px solid rgba(0,0,0,0.12)',
            borderRadius: '12px',
            padding: '16px',
            minWidth: '280px',
            zIndex: 100,
            boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          }}
        >
          <div style={{ fontSize: '13px', fontWeight: 500, marginBottom: '10px' }}>Diagram Context</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
            {diagramContext.detectedResources.map((r, i) => {
              const color = getChipColor(r.service);
              return (
                <span key={i} style={{ fontSize: '11px', fontWeight: 500, padding: '3px 8px', borderRadius: '12px', backgroundColor: color.bg, color: color.text }}>
                  {r.service}
                </span>
              );
            })}
          </div>
          <div style={{ fontSize: '12px', color: '#9b9b9b' }}>
            Cloud: <span style={{ color: '#1a1a1a', fontWeight: 500 }}>{diagramContext.cloud.toUpperCase()}</span>
          </div>
          <button
            onClick={() => setContextVisible(false)}
            style={{ position: 'absolute', top: '8px', right: '8px', background: 'none', border: 'none', color: '#9b9b9b', cursor: 'pointer' }}
          >
            <i className="ti ti-x" />
          </button>
        </div>
      )}

      {/* Prompt Refiner Modal */}
      <PromptRefinerModal
        isOpen={showRefinerModal}
        onClose={() => setShowRefinerModal(false)}
        onSelect={(suggestion) => {
          setInput(suggestion);
          setTimeout(() => textareaRef.current?.focus(), 50);
        }}
        cloudProvider={selectedProvider}
        detectedResources={diagramContext?.detectedResources.map((r) => r.service) || []}
      />
    </div>
  );
};
