/// <reference types="vite/client" />
import { useEffect, useRef, useState } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../services/api';

const DEFAULT_DRAWIO_URL = window.location.origin + '/drawio/';
const DRAWIO_LIBRARIES = [
  'general',
  'uml',
  'er',
  'bpmn',
  'flowchart',
  'basic',
  'arrows2',
  'networking',
  'aws4',
  'aws3',
  'aws3d',
  'azure2',
  'gcp2',
  'kubernetes',
].join(';');
const DRAWIO_QUERY = `embed=1&proto=json&spin=1&libraries=1&libs=${DRAWIO_LIBRARIES}&ui=kennedy&noSaveBtn=1&saveAndExit=0`;

const buildDrawioUrl = () => {
  const configuredUrl = import.meta.env.VITE_DRAWIO_URL || DEFAULT_DRAWIO_URL;
  const separator = configuredUrl.includes('?') ? '&' : '?';
  return configuredUrl.includes('embed=1')
    ? configuredUrl
    : `${configuredUrl}${separator}${DRAWIO_QUERY}`;
};

const DRAWIO_EMBED_URL = buildDrawioUrl();
const DRAWIO_TARGET_ORIGIN = new URL(DRAWIO_EMBED_URL).origin;
const TRUSTED_DRAWIO_ORIGINS = new Set([
  DRAWIO_TARGET_ORIGIN,
  'https://embed.diagrams.net',
  'https://app.diagrams.net',
  'https://www.draw.io',
]);
const BLANK_DRAWIO_XML = `<mxfile host="app.diagrams.net">
  <diagram id="architecture-studio" name="Page-1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1100" pageHeight="850" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>`;

export default function ArchitectureStudio() {
  const {
    architectureJobId,
    architectureGraph,
    architectureXml,
    setArchitectureJobId,
    setArchitectureGraph,
    setArchitectureXml,
  } = useWorkflowStore();

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isReady, setIsReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState('');
  const [activeXml, setActiveXml] = useState(architectureXml || '');
  const [activeGraph, setActiveGraph] = useState<any | null>(architectureGraph);
  const [activeJobId, setActiveJobId] = useState(architectureJobId || '');
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const jobIdFromUrl = params.get('job_id') || sessionStorage.getItem('architectureJobId') || '';

    if (!jobIdFromUrl || architectureXml) {
      if (architectureXml) {
        setActiveXml(architectureXml);
      }
      return;
    }

    let cancelled = false;
    console.info('[Architecture Studio] Loading diagram from job id', jobIdFromUrl);
    api.getArchitectureGraph(jobIdFromUrl)
      .then((result) => {
        if (cancelled) return;
        setActiveJobId(jobIdFromUrl);
        setActiveGraph(result.graph);
        setActiveXml(result.drawio_xml || '');
        setArchitectureJobId(jobIdFromUrl);
        setArchitectureGraph(result.graph);
        setArchitectureXml(result.drawio_xml || '');
        console.info('[Architecture Studio] Loaded saved diagram', {
          jobId: jobIdFromUrl,
          nodes: result.graph?.nodes?.length || 0,
          edges: result.graph?.edges?.length || 0,
        });
      })
      .catch((error) => {
        console.error('[Architecture Studio] Failed to load saved diagram', error);
        setSaveStatus('Could not load saved diagram');
      });

    return () => {
      cancelled = true;
    };
  }, [architectureXml, setArchitectureGraph, setArchitectureJobId, setArchitectureXml]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (!TRUSTED_DRAWIO_ORIGINS.has(event.origin)) return;

      let data = event.data;
      if (typeof data === 'string') {
        try {
          data = JSON.parse(data);
        } catch {
          return;
        }
      }

      console.log('DRAW.IO EVENT:', data);

      // Handle init event - editor is ready
      if (data.event === 'init') {
        setIsReady(true);
        if (iframeRef.current?.contentWindow) {
          iframeRef.current.contentWindow.postMessage(
            JSON.stringify({ action: 'load', xml: activeXml || BLANK_DRAWIO_XML }),
            DRAWIO_TARGET_ORIGIN
          );
        }
      }

      // Handle save event
      if (data.event === 'save' && data.xml) {
        setActiveXml(data.xml);
        setArchitectureXml(data.xml);
        setIsDirty(false);
        if (activeJobId) {
          setSaveStatus('Saving...');
          api.saveArchitectureGraph(activeJobId, data.xml)
            .then((result) => {
              setActiveGraph(result.graph);
              setArchitectureGraph(result.graph);
              setSaveStatus('Saved');
              console.info('[Architecture Studio] Diagram saved', {
                jobId: activeJobId,
                nodes: result.graph?.nodes?.length || 0,
                edges: result.graph?.edges?.length || 0,
              });
            })
            .catch((error) => {
              console.error('[Architecture Studio] Save failed', error);
              setSaveStatus('Save failed');
              setIsDirty(true);
            });
        } else {
          setSaveStatus('Local draft only');
        }
      }

      if (data.event === 'configure' || data.event === 'draft') {
        setIsDirty(true);
      }

      // Handle export event for downloads
      if (data.event === 'export' && data.data) {
        const format = data.format || 'png';
        
        if (format === 'xmlsvg' || format === 'xml') {
          // XML export — data.data contains the raw XML (possibly as data URI)
          let xml = data.data;
          // If it's a data URI, extract the XML content
          if (xml.startsWith('data:')) {
            const base64Match = xml.match(/base64,(.*)/);
            if (base64Match) {
              xml = atob(base64Match[1]);
            } else {
              xml = decodeURIComponent(xml.split(',')[1] || '');
            }
          }
          
          // Update state with latest XML
          setActiveXml(xml);
          setArchitectureXml(xml);
          setIsDirty(false);
          
          // Save to backend if we have a job ID
          if (activeJobId) {
            setSaveStatus('Saving...');
            api.saveArchitectureGraph(activeJobId, xml)
              .then((result) => {
                setActiveGraph(result.graph);
                setArchitectureGraph(result.graph);
                setSaveStatus('Saved ✓');
                console.info('[Architecture Studio] Diagram saved via export', {
                  jobId: activeJobId,
                  nodes: result.graph?.nodes?.length || 0,
                });
              })
              .catch((error) => {
                console.error('[Architecture Studio] Save failed', error);
                setSaveStatus('Save failed');
              });
          } else {
            setSaveStatus('Saved locally');
          }
        } else {
          // PNG/SVG export — data.data is a data URI, trigger download
          const extension = format === 'svg' ? 'svg' : 'png';
          const link = document.createElement('a');
          link.href = data.data;
          link.download = `architecture-diagram.${extension}`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }
      }

      // Handle autosave
      if (data.event === 'autosave' && data.xml) {
        setActiveXml(data.xml);
        setArchitectureXml(data.xml);
        setIsDirty(true);
        if (activeJobId) {
          api.saveArchitectureGraph(activeJobId, data.xml).then((result) => {
            setActiveGraph(result.graph);
            setArchitectureGraph(result.graph);
            setSaveStatus('Autosaved');
            setIsDirty(false);
          }).catch(() => {
            setSaveStatus('Autosave failed');
          });
        }
      }
    };

    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [activeXml, activeJobId, setArchitectureGraph, setArchitectureXml]);

  const sendAction = (action: object) => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(JSON.stringify(action), DRAWIO_TARGET_ORIGIN);
    }
  };

  const handleDownload = (format: 'png' | 'svg') => {
    sendAction({ action: 'export', format });
  };

  const handleDownloadSource = () => {
    console.info('[Architecture Studio] Source download requested', { jobId: activeJobId || null });
    // DrawIO embed doesn't support 'xml' export via postMessage reliably.
    // Instead, use the current activeXml state which is kept in sync via
    // autosave/save events from the editor.
    const xml = activeXml || '';
    if (!xml) {
      // Try to get it from the editor via export action
      sendAction({ action: 'export', format: 'xmlsvg' });
      return;
    }
    const blob = new Blob([xml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `architecture-diagram${activeJobId ? `-${activeJobId}` : ''}.drawio`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleSave = () => {
    console.info('[Architecture Studio] Save requested', { jobId: activeJobId || null });
    // Request the current XML from DrawIO editor. When DrawIO responds with
    // the 'export' event containing XML, we'll save it to the backend.
    // We use 'xmlsvg' format which returns the raw XML in the data field.
    sendAction({ action: 'export', format: 'xmlsvg' });
  };

  const handleBack = () => {
    window.location.href = '/';
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: '#fff',
      zIndex: 100,
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#fafafa',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            onClick={handleBack}
            style={{
              padding: '6px 14px',
              backgroundColor: '#fff',
              color: '#374151',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            ← Back
          </button>
          <div>
            <h1 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Architecture Studio</h1>
            {activeGraph && (
              <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0' }}>
                {activeGraph.nodes?.length || 0} components, {activeGraph.edges?.length || 0} connections
                {activeJobId ? ` · job ${activeJobId}` : ''}
              </p>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {!isReady && (
            <span style={{ fontSize: '12px', color: '#9ca3af', marginRight: '8px' }}>Loading editor...</span>
          )}
          {saveStatus && (
            <span style={{ fontSize: '12px', color: saveStatus.includes('failed') ? '#dc2626' : '#6b7280', marginRight: '8px' }}>
              {saveStatus}{isDirty ? ' · unsaved edits' : ''}
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={!isReady}
            style={{
              padding: '6px 14px',
              backgroundColor: isReady ? '#5B4EE8' : '#e5e7eb',
              color: isReady ? 'white' : '#9ca3af',
              border: 'none',
              borderRadius: '6px',
              cursor: isReady ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Save
          </button>
          <button
            onClick={() => handleDownload('png')}
            disabled={!isReady}
            style={{
              padding: '6px 14px',
              backgroundColor: isReady ? '#10b981' : '#e5e7eb',
              color: isReady ? 'white' : '#9ca3af',
              border: 'none',
              borderRadius: '6px',
              cursor: isReady ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Download PNG
          </button>
          <button
            onClick={() => handleDownload('svg')}
            disabled={!isReady}
            style={{
              padding: '6px 14px',
              backgroundColor: isReady ? '#3b82f6' : '#e5e7eb',
              color: isReady ? 'white' : '#9ca3af',
              border: 'none',
              borderRadius: '6px',
              cursor: isReady ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Download SVG
          </button>
          <button
            onClick={handleDownloadSource}
            disabled={!isReady}
            style={{
              padding: '6px 14px',
              backgroundColor: isReady ? '#111827' : '#e5e7eb',
              color: isReady ? 'white' : '#9ca3af',
              border: 'none',
              borderRadius: '6px',
              cursor: isReady ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Download .drawio
          </button>
        </div>
      </div>

      {/* Editor */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <iframe
          ref={iframeRef}
          title="drawio"
          src={DRAWIO_EMBED_URL}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
          }}
        />
      </div>
    </div>
  );
}
