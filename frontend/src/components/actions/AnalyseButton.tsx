import { useState } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';
import { LoadingOverlay } from '../common/LoadingOverlay';

export const AnalyseButton = () => {
  const { 
    setCurrentStep, 
    uploadedFile, 
    uploadedFileObject,
    selectedProvider,
    setDesignDocs,
    setJobId,
    isAnalyzing,
    setIsAnalyzing
  } = useWorkflowStore();

  const [pipelineStage, setPipelineStage] = useState('');

  const handleAnalyse = async () => {
    if (!uploadedFileObject || !selectedProvider) return;

    setIsAnalyzing(true);
    setPipelineStage('Uploading...');

    try {
      // Step 1: Start pipeline (uploads file + starts background processing - design doc only)
      const jobResult = await api.startPipeline(uploadedFileObject, [selectedProvider]);
      const jobId = jobResult.job_id;
      setJobId(jobId);

      // Step 2: Poll until graph is built (design doc will stream on the next page)
      const finalJob = await api.waitForCompletion(jobId, (stage) => {
        const stageLabels: Record<string, string> = {
          'UPLOADED': 'Starting...',
          'VISION_RUNNING': 'Analyzing diagram with AI vision...',
          'GRAPH_BUILT': 'Graph ready — preparing streaming...',
          'DESIGN_DOC_GENERATING': 'Generating design document...',
          'DESIGN_DOC_GENERATED': 'Design document ready!',
        };
        setPipelineStage(stageLabels[stage] || stage);
      });

      // Step 3: Store design documents if already available
      if (finalJob.design_docs) {
        setDesignDocs(finalJob.design_docs);
      }

      // Step 4: Move to design doc page (streaming will start automatically)
      setCurrentStep(2);

    } catch (error) {
      console.error('Pipeline failed:', error);
      alert('Pipeline failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      setIsAnalyzing(false);
      setPipelineStage('');
    }
  };

  return (
    <>
      {isAnalyzing && <LoadingOverlay message={pipelineStage} />}
      <button
        onClick={handleAnalyse}
        disabled={!uploadedFileObject || !selectedProvider || isAnalyzing}
        style={{
          backgroundColor: 'transparent',
          border: '0.5px solid rgba(0,0,0,0.28)',
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
          opacity: (!uploadedFileObject || !selectedProvider || isAnalyzing) ? 0.4 : 1,
          pointerEvents: (!uploadedFileObject || !selectedProvider || isAnalyzing) ? 'none' : 'auto'
        }}
        onMouseEnter={(e) => { if (!isAnalyzing && uploadedFileObject && selectedProvider) e.currentTarget.style.backgroundColor = '#F5F3EE'; }}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
      >
        <svg className="ti ti-cpu" style={{ width: '14px', height: '14px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
        </svg>
        {isAnalyzing ? 'Generating Design Doc...' : 'Generate Design Document'}
      </button>
      <div style={{ textAlign: 'center', marginTop: '8px' }}>
        <span style={{ fontSize: '12px', color: '#9b9b9b' }}>Analysis takes 1–3 minutes depending on diagram complexity</span>
      </div>
    </>
  );
};
