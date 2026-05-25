/**
 * AnalyseButton — triggers the full AI pipeline: upload → vision → design doc.
 *
 * PURPOSE:
 *   Starts the backend pipeline by calling api.startPipeline() with the
 *   selected file and provider. Polls job status until completion, then
 *   stores the design docs and advances the user to Step 2 (DesignDocPage).
 *
 * WHY IT EXISTS:
 *   This is the single most important action in the app. Extracting it
 *   into a dedicated component keeps UploadPage.tsx declarative while
 *   allowing the button's complex async lifecycle to be self-contained.
 *
 * KEY CONCEPTS:
 *   • Pipeline stages: UPLOADED → VISION_RUNNING → GRAPH_BUILT →
 *     DESIGN_DOC_GENERATING → DESIGN_DOC_GENERATED.
 *   • The design doc is streamed live on the next page; this component
 *     only needs to wait until GRAPH_BUILT (or DESIGN_DOC_GENERATED).
 *   • LoadingOverlay is shown while polling is active.
 *
 * CONNECTIONS:
 *   • workflowStore.ts   → reads uploadedFileObject, selectedProvider,
 *                            writes jobId, designDocs, currentStep
 *   • api.ts            → startPipeline(), waitForCompletion()
 *   • LoadingOverlay.tsx → shown during async polling
 */

// 🟢 BEGINNER: useState is a React hook that lets this component remember values between renders.
// Here we'll use it to track the current pipeline stage message ("Uploading...", "Analyzing...", etc.).
import { useState } from 'react';
// 🟢 BEGINNER: Import the global store so we can read the uploaded file / selected provider and write the job ID.
import { useWorkflowStore } from '../../store/workflowStore';
// 🟢 BEGINNER: Import the API client that talks to our Python backend.
import { api } from '../../services/api';
// 🟢 BEGINNER: Import the full-screen spinner shown while the pipeline runs.
import { LoadingOverlay } from '../common/LoadingOverlay';

// 🟢 BEGINNER: The most important action button in the app. When clicked, it:
//  1. Uploads the file to the backend
//  2. Starts the AI vision + design doc pipeline
//  3. Polls until ready
//  4. Advances the user to the Design Doc page
export const AnalyseButton = () => {
  // 🟢 BEGINNER: Pull state and actions from the global Zustand store.
  const {
    setCurrentStep,         // 🟢 BEGINNER: Function to change the active wizard step (1, 2, or 3).
    uploadedFile,           // 🟢 BEGINNER: File metadata (name, size) for display.
    uploadedFileObject,     // 🟢 BEGINNER: The actual raw File object needed for the upload API.
    selectedProvider,       // 🟢 BEGINNER: "aws" or "azure" — chosen in the CloudSelector.
    setDesignDocs,          // 🟢 BEGINNER: Store the finished design document in global state.
    setJobId,               // 🟢 BEGINNER: Remember the backend job ID so the next page can stream results.
    setContextPack,         // 🟢 BEGINNER: Store the AI vision analysis result for ExtractedServices.
    isAnalyzing,            // 🟢 BEGINNER: Boolean flag — true while the pipeline is running.
    setIsAnalyzing,         // 🟢 BEGINNER: Toggle the analyzing flag on/off.
    userPrompt,             // 🟢 BEGINNER: User's free-form requirements prompt.
    setTerraformPrompts,    // 🟢 BEGINNER: Store generated Terraform prompts.
    companyId,             // 🟢 BEGINNER: Current company ID for multi-tenant template scoping.
    selectedTemplateId,    // 🟢 BEGINNER: Selected instruction template ID.
    setDesignDocStreamStarted, // Mark that streaming was explicitly triggered
  } = useWorkflowStore();

  // 🟢 BEGINNER: Local React state for the human-readable stage label shown in the loading overlay.
  const [pipelineStage, setPipelineStage] = useState('');

  // 🟢 BEGINNER: The main async function triggered when the user clicks the button.
  const handleAnalyse = async () => {
    // 🟢 BEGINNER: Guard clause — don't do anything if no file or provider is selected.
    if (!uploadedFileObject || !selectedProvider) return;

    setIsAnalyzing(true);
    setPipelineStage('Uploading...');

    try {
      // 🟢 BEGINNER: Step 1 — Call the backend to upload the file and start the AI pipeline.
      // api.startPipeline sends a POST request with the file, selected provider, user prompt, template_id, and company_id.
      const jobResult = await api.startPipeline(
        uploadedFileObject, 
        [selectedProvider], 
        userPrompt,
        selectedTemplateId || '',
        companyId || ''
      );
      const jobId = jobResult.job_id;
      setJobId(jobId);

      // 🟢 BEGINNER: Step 2 — Poll the backend every few seconds until the job is done.
      // waitForCompletion keeps asking "are you done yet?" and calls our callback with the latest stage name.
      const finalJob = await api.waitForCompletion(jobId, (stage) => {
        // 🟢 BEGINNER: Map raw backend stage names to user-friendly text.
        const stageLabels: Record<string, string> = {
          'UPLOADED': 'Starting...',
          'FILE_DETECTED': 'Detecting file type...',
          'PARSING': 'Parsing document...',
          'IMAGE_ANALYZED': 'Analyzing images...',
          'PROMPT_ANALYZED': 'Analyzing your requirements...',
          'IMAGE_AND_PROMPT_ANALYZED': 'Vision + requirements done...',
          'CONTEXT_FUSED': 'Fusing context from all inputs...',
          'GRAPH_READY': 'Design doc streaming starts...',
          'DESIGN_DOC_GENERATING': 'Writing design document...',
          'DESIGN_DOC_GENERATED': 'Design document ready!',
          'TERRAFORM_PROMPTS_GENERATING': 'Generating Terraform prompts...',
          'TERRAFORM_PROMPTS_GENERATED': 'Terraform prompts ready!',
          'AGENTS_RUNNING': 'Vision + Requirements agents running...',
          'COMPLETE': 'Complete!',
          'DOCUMENT_PARSED': 'Document parsed...',
          'DESIGN_DOC_FAILED': 'Design doc failed...',
          'FAILED': 'Pipeline failed!',
        };
        setPipelineStage(stageLabels[stage] || stage);
      });

      // 🟢 BEGINNER: Step 3 — Save design docs if ready.
      if (finalJob.design_docs) {
        setDesignDocs(finalJob.design_docs);
      }

      // 🟢 BEGINNER: Step 3b — Save Terraform prompts if ready.
      if (finalJob.terraform_prompts) {
        setTerraformPrompts(finalJob.terraform_prompts);
      }

      // 🟢 BEGINNER: Step 3c — Save the AI vision analysis result so ExtractedServices can display it.
      if (finalJob.context_pack) {
        setContextPack(finalJob.context_pack);
      }

      // 🟢 BEGINNER: Step 4 — Switch to step 2 (DesignDocPage). Mark stream as explicitly started.
      setDesignDocStreamStarted(true);
      setCurrentStep(2);

    } catch (error) {
      // 🟢 BEGINNER: If anything goes wrong (network error, backend crash), log it and alert the user.
      console.error('Pipeline failed:', error);
      alert('Pipeline failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      // 🟢 BEGINNER: Always run this block, success or failure. Turn off the spinner and clear the stage text.
      setIsAnalyzing(false);
      setPipelineStage('');
    }
  };

  return (
    <>
      {/* 🟢 BEGINNER: If the pipeline is running, render the full-screen LoadingOverlay on top of everything. */}
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
