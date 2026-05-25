/**
 * InitializeRagButton — initializes RAG document indexing.
 *
 * PURPOSE:
 *   Starts the RAG indexing pipeline by calling api.initializeRAG().
 *   Indexes the uploaded document for chat-based Q&A.
 *
 * CONNECTIONS:
 *   • workflowStore.ts → reads uploadedFileObject, setRAGJobId, setRAGIndexed
 *   • api.ts → calls initializeRAG()
 */

import { useState } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';

interface InitializeRagButtonProps {
  dark?: boolean;
}

export const InitializeRagButton = ({ dark }: InitializeRagButtonProps = {}) => {
  const {
    uploadedFileObject,
    setRAGJobId,
    setRAGIndexed,
  } = useWorkflowStore();

  const [isIndexing, setIsIndexing] = useState(false);
  const [progressLabel, setProgressLabel] = useState('');

  const handleInitialize = async () => {
    if (!uploadedFileObject) {
      alert('Please upload a file first.');
      return;
    }

    setIsIndexing(true);
    setProgressLabel('Starting RAG indexing...');
    try {
      console.groupCollapsed('[RAG] Initialize indexing');
      console.info('[RAG] Input', {
        file: uploadedFileObject.name,
        size: uploadedFileObject.size,
      });

      const result = await api.initializeRAG(uploadedFileObject);

      // Store in workflow store immediately — persisted so RagChatPage can pick it up
      setRAGJobId(result.job_id);
      console.info('[RAG] Indexing job started', result.job_id);

      // Start polling in background — won't block navigation
      pollIndexingStatus(result.job_id);

      console.groupEnd();
    } catch (error) {
      console.error('[RAG] Initialization failed', error);
      console.groupEnd();
      alert('RAG indexing failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
      setIsIndexing(false);
      setProgressLabel('');
    }
  };

  const pollIndexingStatus = async (jobId: string) => {
    const maxPolls = 600;
    const pollInterval = 2000;

    for (let i = 0; i < maxPolls; i++) {
      try {
        const status = await api.getRAGStatus(jobId);

        const stageLabel = status.stage || 'Processing...';
        const progressPct = status.progress ? ` (${status.progress}%)` : '';
        setProgressLabel(`${stageLabel}${progressPct}`);

        if (status.status === 'indexed') {
          setRAGIndexed(true);
          setIsIndexing(false);
          setProgressLabel('✓ Indexed');
          console.info('[RAG] Indexing completed', status);
          return;
        }

        if (status.status === 'failed') {
          setIsIndexing(false);
          setProgressLabel('Failed');
          console.error('[RAG] Indexing failed', status.error);
          return;
        }
      } catch {
        // Network error during poll — continue silently, RagChatPage will re-check
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    setIsIndexing(false);
    setProgressLabel('Timeout — check AI Assistant page');
  };

  return (
    <>
      <button
        onClick={handleInitialize}
        disabled={isIndexing}
        style={{
          backgroundColor: 'transparent',
          border: dark ? '0.5px solid rgba(255,255,255,0.28)' : '0.5px solid rgba(0,0,0,0.28)',
          borderRadius: '8px',
          fontSize: '13px',
          padding: '13px 16px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          transition: 'background-color 0.2s ease',
          width: '100%',
          justifyContent: 'center',
          color: dark ? '#ffffff' : 'inherit',
          opacity: isIndexing ? 0.4 : 1,
          pointerEvents: isIndexing ? 'none' : 'auto'
        }}
        onMouseEnter={(e) => { if (!isIndexing) e.currentTarget.style.backgroundColor = dark ? 'rgba(255,255,255,0.08)' : '#F5F3EE'; }}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
      >
        <svg style={{ width: '14px', height: '14px', color: dark ? '#ffffff' : 'currentColor' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        {isIndexing ? 'Indexing...' : 'Initialize RAG'}
      </button>
      <div style={{ textAlign: 'center', marginTop: '8px' }}>
        <span style={{ fontSize: '12px', color: dark ? 'rgba(255,255,255,0.5)' : '#9b9b9b' }}>
          {isIndexing ? `${progressLabel}` : 'Index document for AI-powered Q&A'}
        </span>
      </div>
    </>
  );
};
