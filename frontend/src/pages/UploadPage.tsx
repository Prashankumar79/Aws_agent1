/**
 * UploadPage — Step 1 of the workflow: file upload + provider selection.
 *
 * PURPOSE:
 *   Orchestrates the upload, preview, cloud provider selection, and
 *   the "Generate Design Document" action. All sections are stacked
 *   vertically in a single-page layout.
 *
 * WHY IT EXISTS:
 *   Centralizes all pre-analysis UI in one place so the user has a
 *   clear linear flow: upload → select provider → click Analyse.
 *
 * CONNECTIONS:
 *   • UploadDropzone.tsx      → handles file drop/select
 *   • FilePreview.tsx         → shows the uploaded file details
 *   • ExtractedServices.tsx   → shows detected services after analysis
 *   • CloudSelector.tsx       → lets user pick AWS or Azure
 *   • AnalyseButton.tsx       → triggers the full pipeline
 *   • ClearButton.tsx         → (currently non-functional) should reset state
 */

import { UploadDropzone } from '../components/upload/UploadDropzone';
import { FilePreview } from '../components/upload/FilePreview';
import { CloudSelector } from '../components/cloud-selector/CloudSelector';
import { Notification } from '../components/common/Notification';
import { AnalyseButton } from '../components/actions/AnalyseButton';
import { ClearButton } from '../components/actions/ClearButton';
import { ExtractedServices } from '../components/workflow/ExtractedServices';
import { useWorkflowStore } from '../store/workflowStore';

export const UploadPage = () => {
  const { uploadedFile } = useWorkflowStore();

  return (
    <main style={{ flex: 1, padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      {/* File Upload Section */}
      <section style={{ marginBottom: '16px' }}>
        <UploadDropzone />
      </section>

      {/* Uploaded File Section */}
      {uploadedFile && (
        <section style={{ marginBottom: '16px' }}>
          <FilePreview file={uploadedFile} />
        </section>
      )}

      {/* Extracted Services Section */}
      <section style={{ marginBottom: '16px' }}>
        <ExtractedServices />
      </section>

      {/* Cloud Provider Selection */}
      <section style={{ marginBottom: '16px' }}>
        <CloudSelector />
      </section>

      {/* Info Message */}
      <section style={{ marginBottom: '16px' }}>
        <Notification
          message="RAG pipeline will retrieve up-to-date cloud provider documentation for each selected cloud before generating the design document."
          type="info"
        />
      </section>

      {/* Action Buttons */}
      <section style={{ display: 'flex', gap: '12px' }}>
        <ClearButton />
        <AnalyseButton />
      </section>
    </main>
  );
};
