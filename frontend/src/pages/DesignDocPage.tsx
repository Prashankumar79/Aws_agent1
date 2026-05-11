import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../services/api';
import { useState, useEffect, useRef, useCallback } from 'react';

/* ── Section metadata for sidebar progress ── */
const SECTIONS = [
  { key: 'snapshot', label: 'Architecture Snapshot', icon: 'ti-layout-grid' },
  { key: 'flows',    label: 'Data & Traffic Flows', icon: 'ti-arrows-exchange' },
  { key: 'audit',    label: 'Security & Compliance', icon: 'ti-shield-check' },
  { key: 'guidance', label: 'Operational Guidance',  icon: 'ti-bulb' },
];

/* ── Escape HTML ── */
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ── HCL syntax highlighting ── */
function highlightHCL(code: string): string {
  let html = esc(code);
  // Comments
  html = html.replace(/(#.*$)/gm, '<span class="hcl-comment">$1</span>');
  // String literals (double quotes, handle nested escapes simply)
  html = html.replace(
    /"([^"\\]*(\\.[^"\\]*)*)"/g,
    '<span class="hcl-string">"$1"</span>'
  );
  // Keywords / built-ins
  html = html.replace(
    /\b(resource|data|module|variable|output|locals|provider|terraform|backend)\b/g,
    '<span class="hcl-keyword">$1</span>'
  );
  // Common function calls
  html = html.replace(
    /\b(jsonencode|merge|concat|tolist|toset|map|list|file|templatefile|lookup|try|can|contains|length|flatten|zipmap)\b/g,
    '<span class="hcl-func">$1</span>'
  );
  // Interpolation ${...}
  html = html.replace(
    /(\$\{)([^}]+)(\})/g,
    '<span class="hcl-interp">$1</span><span class="hcl-expr">$2</span><span class="hcl-interp">$3</span>'
  );
  // Numbers
  html = html.replace(/\b(\d+)\b/g, '<span class="hcl-num">$1</span>');
  // Boolean / null
  html = html.replace(/\b(true|false|null)\b/g, '<span class="hcl-bool">$1</span>');
  return html;
}

/* ── Convert raw markdown to styled HTML ──
   Fast line-by-line parser: handles incomplete / streaming markdown
   gracefully (no real parser = no crashes on cut-off content).
   `fast=true` skips expensive HCL syntax highlighting so streaming
   stays smooth; full highlighting runs once at the end.             */
function markdownToHTML(md: string, fast = false): string {
  if (!md || !md.trim()) return '';

  function inlineFmt(text: string): string {
    let out = esc(text);
    out = out.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return out;
  }

  const lines = md.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trimEnd();

    // Fenced code block — consume until closing ``` or end of input
    if (t.startsWith('```')) {
      const lang = t.slice(3).trim().split(' ')[0];
      const codeLines: string[] = [];
      i++;
      while (i < lines.length) {
        const l = lines[i].trimEnd();
        if (l.startsWith('```')) { i++; break; }
        codeLines.push(lines[i]);
        i++;
      }
      const rawCode = codeLines.join('\n');
      const isHCL = lang === 'hcl' || lang === 'tf' || lang === 'terraform';
      const highlighted = (isHCL && !fast) ? highlightHCL(rawCode) : esc(rawCode);
      const badge = lang ? `<span class="md-code-lang">${lang}</span>` : '';
      out.push(`<div class="md-code-block"><div class="md-code-header">${badge}<button class="md-code-copy" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText)"><i class="ti ti-copy"></i></button></div><pre class="md-pre">${highlighted}</pre></div>`);
      continue;
    }

    // BEFORE / AFTER diff labels
    if (/^BEFORE\s*$/i.test(t.trim())) {
      out.push('<div class="md-diff-label md-diff-before"><i class="ti ti-arrow-down"></i> BEFORE</div>');
      i++;
      continue;
    }
    if (/^AFTER\s*\(production-ready\)\s*$/i.test(t.trim()) || /^AFTER\s*$/i.test(t.trim())) {
      out.push('<div class="md-diff-label md-diff-after"><i class="ti ti-check"></i> AFTER (production-ready)</div>');
      i++;
      continue;
    }

    if (!t) {
      out.push('<div class="md-spacer"></div>');
    } else if (t.startsWith('### ')) {
      out.push(`<h3 class="md-h3">${inlineFmt(t.slice(4))}</h3>`);
    } else if (t.startsWith('## ')) {
      out.push(`<h2 class="md-h2">${inlineFmt(t.slice(3))}</h2>`);
    } else if (t.startsWith('# ')) {
      out.push(`<h1 class="md-h1">${inlineFmt(t.slice(2))}</h1>`);
    } else if (t.startsWith('> [!WARNING]')) {
      out.push(`<div class="md-callout md-callout-warn"><i class="ti ti-alert-triangle"></i><span>${inlineFmt(t.slice(12).trim())}</span></div>`);
    } else if (t.startsWith('> [!IMPORTANT]')) {
      out.push(`<div class="md-callout md-callout-info"><i class="ti ti-info-circle"></i><span>${inlineFmt(t.slice(14).trim())}</span></div>`);
    } else if (t.startsWith('> ')) {
      out.push(`<blockquote class="md-quote">${inlineFmt(t.slice(2))}</blockquote>`);
    } else if (t.startsWith('- ') || t.startsWith('* ')) {
      out.push(`<div class="md-li"><span class="md-bullet">•</span>${inlineFmt(t.slice(2))}</div>`);
    } else if (/^\d+\.\s/.test(t)) {
      const match = t.match(/^(\d+)\.\s(.*)/);
      out.push(`<div class="md-li"><span class="md-num">${match![1]}.</span>${inlineFmt(match![2])}</div>`);
    } else if (t.startsWith('|')) {
      out.push(`<div class="md-table-row">${esc(t)}</div>`);
    } else if (t.startsWith('---') || t.startsWith('***')) {
      out.push('<hr class="md-hr"/>');
    } else {
      out.push(`<p class="md-p">${inlineFmt(t)}</p>`);
    }
    i++;
  }

  return out.join('\n');
}

/* ══════════════════════════════════════════════════════════════
   Component — ChatGPT-like streaming design document
   ══════════════════════════════════════════════════════════════ */
export const DesignDocPage = () => {
  const { designDocs, selectedProvider, jobId, setDesignDocs } = useWorkflowStore();

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamComplete, setStreamComplete] = useState(false);
  const [currentSection, setCurrentSection] = useState('');
  const [completedSections, setCompletedSections] = useState<string[]>([]);
  const [statusText, setStatusText] = useState('');
  const [renderedHTML, setRenderedHTML] = useState('');
  const [copied, setCopied] = useState(false);
  const [streamKey, setStreamKey] = useState(0); // increment via handleRegenerate to re-run the stream effect

  const markdownRef = useRef('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRenderLenRef = useRef(0);
  const isStreamingRef = useRef(false); // ref mirror of isStreaming — keeps scheduleRender stable

  const designDoc = designDocs[selectedProvider];

  /* Keep isStreamingRef in sync with isStreaming state.
     This lets scheduleRender read the current streaming status WITHOUT
     being re-created every time isStreaming flips — which was the root
     cause of the disconnect/reconnect loop (gen 1 → gen 2 → gen 3).   */
  useEffect(() => { isStreamingRef.current = isStreaming; }, [isStreaming]);

  /* ── Flush accumulated markdown to rendered HTML (throttled) ──
     Uses isStreamingRef (a ref) instead of isStreaming (state) so this
     callback NEVER gets recreated mid-stream. A changing scheduleRender
     reference was causing startStreaming to be recreated, which triggered
     a spurious third effect mount on top of React Strict Mode's two.    */
  const scheduleRender = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      const len = markdownRef.current.length;
      if (len <= lastRenderLenRef.current) return;
      // While streaming, wait for a meaningful chunk before re-rendering
      if (isStreamingRef.current && len - lastRenderLenRef.current < 200) return;
      lastRenderLenRef.current = len;
      setRenderedHTML(markdownToHTML(markdownRef.current, isStreamingRef.current));
    }, isStreamingRef.current ? 200 : 80);
  }, []); // ← empty deps: never recreated, reads live values via refs

  /* ── Auto-scroll to bottom when content changes ── */
  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      const el = scrollRef.current;
      // Only auto-scroll if user is near the bottom (within 120px)
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (nearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [renderedHTML, isStreaming]);

  /* ── Main streaming effect ──────────────────────────────────────────────────
     Self-contained: opens the SSE stream, processes events, cleans up.
     Uses a local `cancelled` flag (the standard React pattern) instead of
     shared generation counters. React Strict Mode fires mount→cleanup→mount;
     the first run's async code sees `cancelled=true` immediately and stops.
     `streamKey` is the only external trigger: incrementing it (via
     handleRegenerate) forces this effect to re-run and restart the stream. */
  useEffect(() => {
    if (!jobId || !selectedProvider) return;

    // Serve cached content (skip streaming if already generated)
    const cached = designDocs[selectedProvider];
    if (cached?.content && streamKey === 0) {
      markdownRef.current = cached.content;
      setRenderedHTML(markdownToHTML(cached.content, false));
      setStreamComplete(true);
      setCompletedSections(['snapshot', 'flows', 'audit', 'guidance']);
      setStatusText('Design document complete');
      return;
    }

    // ── Setup ────────────────────────────────────────────────────────────
    let cancelled = false;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    markdownRef.current = '';
    lastRenderLenRef.current = 0;
    setRenderedHTML('');
    setIsStreaming(true);
    setStreamComplete(false);
    setCurrentSection('');
    setCompletedSections([]);
    setStatusText('Connecting to AI...');

    // ── SSE buffer parser (inline — splits on \n\n, fires onEvent per event) ─
    const processBuffer = (buf: string, onEvent: (d: string) => void): string => {
      const parts = buf.split('\n\n');
      const leftover = parts.pop() || '';
      for (const part of parts) {
        let data = '';
        for (const line of part.trim().split('\n'))
          if (line.startsWith('data: ')) data += line.slice(6);
        if (data) onEvent(data);
      }
      return leftover;
    };

    const cloud = selectedProvider.toLowerCase();
    const url = `/api/v1/jobs/${jobId}/stream-design-doc-sections?cloud=${cloud}`;
    console.log('[DesignDoc] Opening stream:', url);

    // ── Fetch SSE stream ──────────────────────────────────────────────────
    fetch(url, { signal: ctrl.signal, headers: { Accept: 'text/event-stream' } })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        if (!response.body) throw new Error('No response body');

        console.log('[DesignDoc] Stream connected');
        setStatusText('Generating design document...');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const handleEvent = (data: string) => {
          if (cancelled) return;
          if (data === '[DONE]') {
            setIsStreaming(false);
            setStreamComplete(true);
            setCurrentSection('');
            setStatusText('Design document complete');
            setRenderedHTML(markdownToHTML(markdownRef.current, false));
            api.getJobStatus(jobId).then(job => {
              if (job.design_docs) setDesignDocs(job.design_docs);
            }).catch(() => {});
            return;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'error') {
              setIsStreaming(false);
              setStatusText('Error: ' + parsed.message);
              ctrl.abort();
              return;
            }
            if (parsed.type === 'section_start') {
              setCurrentSection(parsed.section);
              setStatusText(`Writing ${parsed.title || parsed.section}...`);
              if (markdownRef.current.length > 0) markdownRef.current += '\n\n---\n\n';
            } else if (parsed.type === 'delta') {
              markdownRef.current += parsed.text;
              scheduleRender();
            } else if (parsed.type === 'section_end') {
              setCompletedSections(prev => [...prev, parsed.section]);
            }
          } catch (e) {
            console.error('[DesignDoc] Parse error:', e, data.slice(0, 200));
          }
        };

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done || cancelled) break;
          buffer += decoder.decode(value, { stream: true });
          buffer = processBuffer(buffer, handleEvent);
        }
        if (!cancelled && buffer.trim()) processBuffer(buffer + '\n\n', handleEvent);
        if (!cancelled) setIsStreaming(false);
      })
      .catch((err: any) => {
        if (err.name === 'AbortError' || cancelled) {
          console.log('[DesignDoc] Stream cancelled (expected in Strict Mode)');
          return;
        }
        console.error('[DesignDoc] Stream error:', err);
        setIsStreaming(false);
        setStatusText('Stream failed — loading from cache...');
        loadFallback(); // attempt to load already-generated doc from backend
      });

    // ── Cleanup: React Strict Mode fires this immediately on first mount ──
    return () => {
      cancelled = true;
      ctrl.abort();
      abortRef.current = null;
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, selectedProvider, streamKey]);

  /* ── Fallback: load from backend if SSE fails ── */
  const loadFallback = useCallback(async () => {
    if (!jobId || !selectedProvider) return;
    setStatusText('Loading document...');
    try {
      const job = await api.getJobStatus(jobId);
      const doc = job.design_docs?.[selectedProvider];
      if (doc?.content) {
        markdownRef.current = doc.content;
        setRenderedHTML(markdownToHTML(doc.content, false));
        setDesignDocs(job.design_docs!);
        setCompletedSections(['snapshot', 'flows', 'audit', 'guidance']);
      }
      setStreamComplete(true);
      setStatusText('Design document complete');
    } catch {
      setStatusText('Failed to load document');
    }
  }, [jobId, selectedProvider, setDesignDocs]);

  /* ── Actions ── */
  const handleDownload = async () => {
    if (!jobId || !selectedProvider) return;
    try {
      const blob = await api.downloadDesignDocPdf(jobId, selectedProvider);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selectedProvider}-design-doc.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      alert('Download failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  };

  const handleRegenerate = () => {
    setStreamKey(k => k + 1); // triggers streaming useEffect to re-run cleanly
  };

  const buttonsDisabled = isStreaming;

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 52px)' }}>
      {/* ── Left Sidebar: Section Progress ── */}
      <div style={{
        width: '240px', backgroundColor: 'white',
        borderRight: '0.5px solid rgba(0,0,0,0.12)',
        padding: '12px 0', overflowY: 'auto', flexShrink: 0,
      }}>
        <div style={{ padding: '12px 14px 8px' }}>
          <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
            SECTIONS
          </span>
        </div>

        {SECTIONS.map((sec) => {
          const isCompleted = completedSections.includes(sec.key);
          const isActive = currentSection === sec.key;
          const isPending = !isCompleted && !isActive;

          return (
            <div
              key={sec.key}
              style={{
                padding: '10px 14px',
                margin: '2px 8px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '13px',
                fontWeight: isActive ? 500 : 400,
                backgroundColor: isActive ? '#EEEDFE' : 'transparent',
                color: isCompleted ? '#3B6D11' : isActive ? '#5B4EE8' : '#9b9b9b',
                transition: 'all 0.3s ease',
              }}
            >
              {/* Status icon */}
              {isCompleted ? (
                <i className="ti ti-circle-check" style={{ fontSize: '16px', color: '#3B6D11' }} />
              ) : isActive ? (
                <i className="ti ti-loader-2 animate-spin-smooth" style={{ fontSize: '16px', color: '#5B4EE8' }} />
              ) : (
                <i className="ti ti-circle-dashed" style={{ fontSize: '16px', color: '#d0d0d0' }} />
              )}

              <div>
                <div style={{ color: isCompleted ? '#1a1a1a' : isActive ? '#1a1a1a' : '#9b9b9b' }}>
                  {sec.label}
                </div>
                {isActive && (
                  <div style={{ fontSize: '11px', color: '#5B4EE8', marginTop: '1px' }}>
                    Generating...
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Sidebar actions */}
        <div style={{ padding: '16px 14px 8px', marginTop: '16px', borderTop: '0.5px solid rgba(0,0,0,0.12)' }}>
          <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>
            EXPORT
          </span>
        </div>
        <div
          onClick={!buttonsDisabled ? handleDownload : undefined}
          style={{
            padding: '10px 14px', margin: '2px 8px', borderRadius: '10px',
            display: 'flex', alignItems: 'center', gap: '10px',
            fontSize: '13px', color: buttonsDisabled ? '#d0d0d0' : '#1a1a1a',
            cursor: buttonsDisabled ? 'default' : 'pointer',
          }}
        >
          <i className="ti ti-file-type-pdf" style={{ fontSize: '16px' }} />
          Download PDF
        </div>
        <div
          style={{
            padding: '10px 14px', margin: '2px 8px', borderRadius: '10px',
            display: 'flex', alignItems: 'center', gap: '10px',
            fontSize: '13px', color: '#1a1a1a', cursor: 'pointer',
            backgroundColor: copied ? '#EAF3DE' : 'transparent',
            transition: 'background-color 0.2s',
          }}
          onClick={async () => {
            const text = markdownRef.current || (designDoc?.content ?? '');
            if (!text) return;
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } catch {
              // Fallback for older browsers / non-secure contexts
              const ta = document.createElement('textarea');
              ta.value = text;
              document.body.appendChild(ta);
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }
          }}
        >
          <i className={copied ? 'ti ti-check' : 'ti ti-clipboard'} style={{ fontSize: '16px', color: copied ? '#3B6D11' : '#1a1a1a' }} />
          {copied ? 'Copied!' : 'Copy Markdown'}
        </div>
      </div>

      {/* ── Main Content ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Content Area */}
        <div
          ref={scrollRef}
          style={{
            flex: 1, overflowY: 'auto', padding: '32px 40px',
            backgroundColor: '#FAFAFA',
          }}
        >
          {/* Streaming content */}
          {(renderedHTML || isStreaming) ? (
            <div className="streaming-content">
              <div className="md-body">
                <div dangerouslySetInnerHTML={{ __html: renderedHTML }} />
                {isStreaming && <span className="stream-cursor" />}
              </div>
            </div>
          ) : (
            /* Empty state */
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', minHeight: '400px', color: '#9b9b9b',
            }}>
              <i className="ti ti-file-description" style={{ fontSize: '48px', marginBottom: '16px', color: '#d0d0d0' }} />
              <div style={{ fontSize: '15px', fontWeight: 500, color: '#6b6b6b', marginBottom: '6px' }}>
                No design document yet
              </div>
              <div style={{ fontSize: '13px' }}>
                Upload a diagram and run analysis to generate one
              </div>
            </div>
          )}
        </div>

        {/* ── Bottom Bar ── */}
        <div style={{
          padding: '12px 24px',
          borderTop: '0.5px solid rgba(0,0,0,0.12)',
          backgroundColor: 'white',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {/* Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#6b6b6b' }}>
            {isStreaming ? (
              <i className="ti ti-loader-2 animate-spin-smooth" style={{ fontSize: '16px', color: '#5B4EE8' }} />
            ) : streamComplete ? (
              <i className="ti ti-circle-check" style={{ fontSize: '16px', color: '#3B6D11' }} />
            ) : (
              <i className="ti ti-clock" style={{ fontSize: '16px' }} />
            )}
            <span>{statusText}</span>
            {isStreaming && (
              <span style={{
                fontSize: '11px', color: '#5B4EE8', backgroundColor: '#EEEDFE',
                padding: '2px 8px', borderRadius: '10px', marginLeft: '4px',
              }}>
                LIVE
              </span>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleRegenerate}
              disabled={buttonsDisabled}
              className="ds-button"
              style={{ opacity: buttonsDisabled ? 0.4 : 1 }}
            >
              <i className="ti ti-refresh" style={{ fontSize: '14px', marginRight: '6px' }} />
              Regenerate
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
