import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../services/api';
import { useState, useEffect, useRef, useCallback } from 'react';

/* ── Section metadata for sidebar progress ── */
const SECTIONS = [
  { key: 'snapshot',          label: 'Architecture Snapshot',      icon: 'ti-layout-grid' },
  { key: 'flows',             label: 'Data & Traffic Flows',       icon: 'ti-arrows-exchange' },
  { key: 'audit',             label: 'Security & Compliance',      icon: 'ti-shield-check' },
  { key: 'guidance',          label: 'Operational Guidance',       icon: 'ti-bulb' },
  { key: 'terraform_prompts', label: 'Terraform Prompts (20)',     icon: 'ti-terminal-2' },
];

/* ── Category color map for prompt chips ── */
const CATEGORY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  networking:      { bg: '#EFF6FF', text: '#1E40AF', border: '#BFDBFE' },
  iam:             { bg: '#FEF3C7', text: '#92400E', border: '#FDE68A' },
  security:        { bg: '#FEF3C7', text: '#92400E', border: '#FDE68A' },
  compute:         { bg: '#ECFDF5', text: '#065F46', border: '#A7F3D0' },
  storage:         { bg: '#F0FDF4', text: '#166534', border: '#BBF7D0' },
  database:        { bg: '#EFF6FF', text: '#1E3A8A', border: '#BFDBFE' },
  'load balancing': { bg: '#FDF2F8', text: '#9D174D', border: '#FBCFE8' },
  'dns & cdn':     { bg: '#FDF2F8', text: '#9D174D', border: '#FBCFE8' },
  messaging:       { bg: '#F5F3FF', text: '#5B21B6', border: '#DDD6FE' },
  monitoring:      { bg: '#FFFBEB', text: '#78350F', border: '#FDE68A' },
  logging:         { bg: '#FFFBEB', text: '#78350F', border: '#FDE68A' },
  'ci/cd':         { bg: '#F0F9FF', text: '#0C4A6E', border: '#BAE6FD' },
  backup:          { bg: '#F0FDFA', text: '#134E4A', border: '#99F6E4' },
  cost:            { bg: '#FFF7ED', text: '#9A3412', border: '#FED7AA' },
  compliance:      { bg: '#FAF5FF', text: '#6B21A8', border: '#E9D5FF' },
};
function getCategoryColor(cat: string) {
  const key = cat.toLowerCase();
  return CATEGORY_COLORS[key] || { bg: '#F3F4F6', text: '#4B5563', border: '#E5E7EB' };
}

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

    // BEFORE / AFTER diff labels — auto-detect unfenced HCL code after the label
    const isBeforeLabel = /^#{0,4}\s*\*{0,2}BEFORE\*{0,2}\s*$/i.test(t.trim());
    const isAfterLabel  = /^#{0,4}\s*\*{0,2}AFTER\s*(\(production[- ]ready\))?\*{0,2}\s*$/i.test(t.trim());
    if (isBeforeLabel || isAfterLabel) {
      out.push(isBeforeLabel
        ? '<div class="md-diff-label md-diff-before"><i class="ti ti-arrow-down"></i> BEFORE</div>'
        : '<div class="md-diff-label md-diff-after"><i class="ti ti-check"></i> AFTER (production-ready)</div>');
      i++;
      // Skip blank lines between label and code
      while (i < lines.length && !lines[i].trim()) i++;
      // If next line looks like HCL/code (not a heading/label), auto-wrap in code block
      const hclStart = /^(resource|data|module|variable|output|locals|provider|terraform|#|\/\/|\{)/;
      if (i < lines.length && hclStart.test(lines[i].trim())) {
        const codeLines: string[] = [];
        while (i < lines.length) {
          const cl = lines[i];
          const ct = cl.trimEnd();
          // Stop if we hit another BEFORE/AFTER label, heading, or section divider
          if (/^#{1,4}\s/.test(ct) || /^\*{0,2}(BEFORE|AFTER)\*{0,2}/i.test(ct.trim()) || ct.startsWith('---') || ct.startsWith('***')) break;
          // Stop on double blank line (paragraph break)
          if (!ct && i + 1 < lines.length && !lines[i + 1].trim() && codeLines.length > 3) break;
          // Stop if line looks like prose (long sentence without = or { characters) after we have some code
          if (codeLines.length > 2 && ct.length > 60 && !ct.includes('=') && !ct.includes('{') && !ct.includes('}') && !ct.includes('#') && !ct.startsWith(' ') && !ct.startsWith('\t')) break;
          codeLines.push(cl);
          i++;
        }
        // Trim trailing blank lines from code block
        while (codeLines.length && !codeLines[codeLines.length - 1].trim()) codeLines.pop();
        if (codeLines.length > 0) {
          const rawCode = codeLines.join('\n');
          const highlighted = fast ? esc(rawCode) : highlightHCL(rawCode);
          out.push(`<div class="md-code-block"><div class="md-code-header"><span class="md-code-lang">hcl</span><button class="md-code-copy" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText)"><i class="ti ti-copy"></i></button></div><pre class="md-pre">${highlighted}</pre></div>`);
        }
      }
      continue;
    }

    if (!t) {
      out.push('<div class="md-spacer"></div>');
    } else if (t.startsWith('### ')) {
      out.push(`<h3 class="md-h3">${inlineFmt(t.slice(4))}</h3>`);
    } else if (t.startsWith('## ')) {
      out.push(`<h2 class="md-h2"><span class="md-h2-accent"></span>${inlineFmt(t.slice(3))}</h2>`);
    } else if (t.startsWith('# ')) {
      out.push(`<h1 class="md-h1">${inlineFmt(t.slice(2))}</h1>`);
    } else if (t.startsWith('> [!WARNING]')) {
      out.push(`<div class="md-callout md-callout-warn"><div class="md-callout-icon"><i class="ti ti-alert-triangle"></i></div><div class="md-callout-body"><strong>Warning</strong><span>${inlineFmt(t.slice(12).trim())}</span></div></div>`);
    } else if (t.startsWith('> [!IMPORTANT]')) {
      out.push(`<div class="md-callout md-callout-info"><div class="md-callout-icon"><i class="ti ti-info-circle"></i></div><div class="md-callout-body"><strong>Important</strong><span>${inlineFmt(t.slice(14).trim())}</span></div></div>`);
    } else if (t.startsWith('> ')) {
      out.push(`<blockquote class="md-quote">${inlineFmt(t.slice(2))}</blockquote>`);
    } else if (t.startsWith('- ') || t.startsWith('* ')) {
      out.push(`<div class="md-li"><span class="md-bullet"></span>${inlineFmt(t.slice(2))}</div>`);
    } else if (/^\d+\.\s/.test(t)) {
      const match = t.match(/^(\d+)\.\s(.*)/);
      out.push(`<div class="md-li"><span class="md-num">${match![1]}</span>${inlineFmt(match![2])}</div>`);
    } else if (t.startsWith('|')) {
      // ── Proper table rendering: consume all consecutive | rows ──
      const tableRows: string[] = [];
      while (i < lines.length && lines[i].trimEnd().startsWith('|')) {
        tableRows.push(lines[i].trimEnd());
        i++;
      }
      // Parse rows into cells
      const parseCells = (row: string) =>
        row.split('|').slice(1, -1).map(c => c.trim());
      const isSeparator = (row: string) => /^\|[\s\-:|]+\|$/.test(row);
      // Build HTML table
      let tableHTML = '<div class="md-table-wrapper"><table class="md-table">';
      let headerDone = false;
      for (let r = 0; r < tableRows.length; r++) {
        if (isSeparator(tableRows[r])) { headerDone = true; continue; }
        const cells = parseCells(tableRows[r]);
        if (!headerDone && r === 0) {
          tableHTML += '<thead><tr>';
          cells.forEach(c => { tableHTML += `<th>${inlineFmt(c)}</th>`; });
          tableHTML += '</tr></thead><tbody>';
          // If next row is separator, skip it
          if (r + 1 < tableRows.length && isSeparator(tableRows[r + 1])) {
            r++;
            headerDone = true;
          } else {
            headerDone = true;
          }
        } else {
          tableHTML += '<tr>';
          cells.forEach(c => {
            // Detect status indicators
            let cellClass = '';
            if (c.includes('✅')) cellClass = ' class="md-cell-pass"';
            else if (c.includes('❌')) cellClass = ' class="md-cell-fail"';
            else if (c.includes('⚠️')) cellClass = ' class="md-cell-warn"';
            tableHTML += `<td${cellClass}>${inlineFmt(c)}</td>`;
          });
          tableHTML += '</tr>';
        }
      }
      tableHTML += '</tbody></table></div>';
      out.push(tableHTML);
      continue; // skip i++ below since we already advanced
    } else if (t.startsWith('---') || t.startsWith('***')) {
      out.push('<hr class="md-hr"/>');
    } else if (/^(resource|data|module|variable|output|locals|provider|terraform)\s+["'{]/.test(t.trim())) {
      // ── Unfenced HCL block: auto-detect and wrap ──
      const codeLines: string[] = [];
      while (i < lines.length) {
        const cl = lines[i];
        const ct = cl.trimEnd();
        if (/^#{1,4}\s/.test(ct) || /^\*{0,2}(BEFORE|AFTER)\*{0,2}/i.test(ct.trim())) break;
        if (!ct && i + 1 < lines.length && !lines[i + 1].trim() && codeLines.length > 3) break;
        if (codeLines.length > 2 && ct.length > 60 && !ct.includes('=') && !ct.includes('{') && !ct.includes('}') && !ct.includes('#') && !ct.startsWith(' ') && !ct.startsWith('\t')) break;
        codeLines.push(cl);
        i++;
      }
      while (codeLines.length && !codeLines[codeLines.length - 1].trim()) codeLines.pop();
      if (codeLines.length > 0) {
        const rawCode = codeLines.join('\n');
        const highlighted = fast ? esc(rawCode) : highlightHCL(rawCode);
        out.push(`<div class="md-code-block"><div class="md-code-header"><span class="md-code-lang">hcl</span><button class="md-code-copy" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText)"><i class="ti ti-copy"></i></button></div><pre class="md-pre">${highlighted}</pre></div>`);
      }
      continue;
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
  const { designDocs, selectedProvider, jobId, setDesignDocs, setTerraformPrompts, setCurrentStep, terraformPrompts } = useWorkflowStore();

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
      // Strip the terraform_prompts raw text (last section after final ---) from visible content
      // The prompts are shown only as blue cards, not as raw markdown
      const parts = cached.content.split('\n\n---\n\n');
      const visibleParts = parts.length >= 5 ? parts.slice(0, 4) : parts;
      const visibleContent = visibleParts.join('\n\n---\n\n');
      markdownRef.current = visibleContent;
      setRenderedHTML(markdownToHTML(visibleContent, false));
      setStreamComplete(true);
      setCompletedSections(['snapshot', 'flows', 'audit', 'guidance', 'terraform_prompts']);
      setStatusText('Design document complete');
      // Load cached terraform prompts
      if (Array.isArray(cached.terraform_prompts) && cached.terraform_prompts.length > 0) {
        setTerraformPrompts(cached.terraform_prompts);
      }
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

        let activeSection = ''; // local tracking to avoid stale closure on state

        const handleEvent = (data: string) => {
          if (cancelled) return;
          if (data === '[DONE]') {
            setIsStreaming(false);
            setStreamComplete(true);
            setCurrentSection('');
            setStatusText('Design document complete');
            setRenderedHTML(markdownToHTML(markdownRef.current, false));
            api.getJobStatus(jobId).then(job => {
              if (job.design_docs) {
                setDesignDocs(job.design_docs);
                const prompts = job.design_docs?.[selectedProvider]?.terraform_prompts;
                if (Array.isArray(prompts) && prompts.length > 0) {
                  setTerraformPrompts(prompts);
                }
              }
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
              activeSection = parsed.section;
              setCurrentSection(parsed.section);
              setStatusText(`Writing ${parsed.title || parsed.section}...`);
              // Don't add separator before terraform_prompts since we won't render its raw text
              if (markdownRef.current.length > 0 && parsed.section !== 'terraform_prompts') markdownRef.current += '\n\n---\n\n';
            } else if (parsed.type === 'delta') {
              // Skip appending terraform_prompts raw text to the visible markdown body
              // — it will be shown only as the styled blue cards
              if (activeSection !== 'terraform_prompts') {
                markdownRef.current += parsed.text;
                scheduleRender();
              }
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
        setCompletedSections(['snapshot', 'flows', 'audit', 'guidance', 'terraform_prompts']);
        if (Array.isArray(doc.terraform_prompts) && doc.terraform_prompts.length > 0) {
          setTerraformPrompts(doc.terraform_prompts);
        }
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

              {/* ── Terraform Prompt Cards (shown after streaming completes) ── */}
              {streamComplete && terraformPrompts.length > 0 && (
                <div style={{ marginTop: '48px' }}>
                  {/* ── Hero banner ── */}
                  <div style={{
                    background: 'linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%)',
                    borderRadius: '16px', padding: '28px 32px', marginBottom: '24px',
                    position: 'relative', overflow: 'hidden',
                  }}>
                    <div style={{ position: 'absolute', top: '-30px', right: '-20px', width: '180px', height: '180px', borderRadius: '50%', background: 'rgba(255,255,255,0.08)' }} />
                    <div style={{ position: 'absolute', bottom: '-40px', left: '40%', width: '120px', height: '120px', borderRadius: '50%', background: 'rgba(255,255,255,0.05)' }} />
                    <div style={{ position: 'relative', zIndex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
                        <div style={{ width: '40px', height: '40px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.2)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <i className="ti ti-terminal-2" style={{ fontSize: '20px', color: 'white' }} />
                        </div>
                        <div>
                          <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'white', margin: 0, letterSpacing: '-0.01em' }}>
                            Terraform Generation Prompts
                          </h2>
                          <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.75)', marginTop: '2px' }}>
                            {terraformPrompts.length} prompts generated from your architecture diagram
                          </div>
                        </div>
                      </div>
                      <p style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)', margin: 0, lineHeight: '1.55', maxWidth: '600px' }}>
                        Each prompt is tailored to the exact services detected in your diagram.
                        Click any card to open it in the Terraform editor — you can review and edit before generating code.
                      </p>
                    </div>
                  </div>

                  {/* ── Prompt grid ── */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '14px' }}>
                    {terraformPrompts.map((p, i) => {
                      const color = getCategoryColor(p.category);
                      return (
                        <div
                          key={i}
                          onClick={() => {
                            useWorkflowStore.getState().setCurrentStep(3);
                            (window as any).__pendingTfPrompt = p.prompt;
                          }}
                          style={{
                            padding: '0', borderRadius: '12px', overflow: 'hidden',
                            border: '1px solid #E5E7EB', backgroundColor: 'white',
                            cursor: 'pointer', transition: 'all 0.2s ease',
                            display: 'flex', position: 'relative',
                          }}
                          onMouseEnter={e => {
                            const el = e.currentTarget as HTMLDivElement;
                            el.style.boxShadow = '0 4px 20px rgba(91,78,232,0.12)';
                            el.style.transform = 'translateY(-2px)';
                            el.style.borderColor = '#C7C3F9';
                          }}
                          onMouseLeave={e => {
                            const el = e.currentTarget as HTMLDivElement;
                            el.style.boxShadow = 'none';
                            el.style.transform = 'none';
                            el.style.borderColor = '#E5E7EB';
                          }}
                        >
                          {/* Left accent strip */}
                          <div style={{ width: '4px', flexShrink: 0, background: `linear-gradient(180deg, ${color.text}, ${color.border})` }} />

                          <div style={{ flex: 1, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {/* Top row: number + category badge */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{
                                width: '22px', height: '22px', borderRadius: '6px',
                                backgroundColor: color.bg, color: color.text,
                                fontSize: '11px', fontWeight: 700,
                                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                              }}>
                                {i + 1}
                              </span>
                              <span style={{
                                fontSize: '10px', fontWeight: 700, textTransform: 'uppercase',
                                letterSpacing: '0.06em', padding: '3px 10px', borderRadius: '20px',
                                backgroundColor: color.bg, color: color.text,
                              }}>
                                {p.category}
                              </span>
                            </div>

                            {/* Prompt text */}
                            <div style={{ fontSize: '13.5px', color: '#1a1a1a', lineHeight: '1.55', fontWeight: 400 }}>
                              {p.prompt}
                            </div>

                            {/* CTA */}
                            <div style={{
                              display: 'flex', alignItems: 'center', gap: '6px', marginTop: 'auto', paddingTop: '4px',
                            }}>
                              <span style={{
                                fontSize: '11.5px', fontWeight: 600, color: '#5B4EE8',
                                padding: '4px 12px', borderRadius: '6px',
                                backgroundColor: '#EEEDFE',
                                display: 'inline-flex', alignItems: 'center', gap: '4px',
                                transition: 'background-color 0.15s',
                              }}>
                                <i className="ti ti-code" style={{ fontSize: '13px' }} />
                                Generate Code
                                <i className="ti ti-arrow-right" style={{ fontSize: '12px' }} />
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
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
