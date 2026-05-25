/**
 * UploadPage — Step 1: file upload + cloud selection + template + requirements.
 */

import { UploadDropzone } from '../components/upload/UploadDropzone';
import { FilePreview } from '../components/upload/FilePreview';
import { CloudSelector } from '../components/cloud-selector/CloudSelector';
import { AnalyseButton } from '../components/actions/AnalyseButton';
import { ArchitectureDiagramButton } from '../components/actions/ArchitectureDiagramButton';
import { InitializeRagButton } from '../components/actions/InitializeRagButton';
import { ClearButton } from '../components/actions/ClearButton';
import { ExtractedServices } from '../components/workflow/ExtractedServices';
import { TemplateSelector } from '../components/templates/TemplateSelector';
import { useWorkflowStore } from '../store/workflowStore';

export const UploadPage = () => {
  const { uploadedFile, reset, userPrompt, setUserPrompt, selectedProvider } = useWorkflowStore();

  const getPlaceholder = () => {
    switch (selectedProvider) {
      case 'azure':
        return 'Example: 3-tier web app on Azure with VNet, ALB, VM Scale Set in private subnets, Azure SQL in private subnet, Blob Storage. Naming: {env}-{app}-{resource}. Tags: Environment, Owner, CostCenter. No public VMs. Encryption everywhere.';
      case 'gcp':
        return 'Example: 3-tier web app on GCP with VPC, Cloud LB, Cloud Run in private subnets, Cloud SQL in private subnet, GCS. Naming: {env}-{app}-{resource}. Tags: Environment, Owner, CostCenter. No public instances. Encryption everywhere.';
      default:
        return 'Example: Migrate on-prem Oracle DB and 3-tier Java app to AWS. RDS Multi-AZ PostgreSQL in private subnets, ALB + EC2 Auto Scaling, S3 for static assets. Naming: {client}-{env}-{region}-{resource}. Tags: CostCenter, Owner, Environment. No public EC2. PCI-DSS compliance.';
    }
  };

  return (
    <main style={{ flex: 1, padding: '32px 24px', maxWidth: '900px', margin: '0 auto', width: '100%' }}>

      {/* Upload dropzone */}
      <section style={{ marginBottom: '16px' }}>
        <UploadDropzone />
      </section>

      {/* File preview — only shown after upload */}
      {uploadedFile && (
        <section style={{ marginBottom: '16px' }}>
          <FilePreview file={uploadedFile} />
        </section>
      )}

      {/* Cloud provider */}
      <section style={{ marginBottom: '16px' }}>
        <CloudSelector />
      </section>

      {/* Governance template */}
      <section style={{ marginBottom: '16px' }}>
        <TemplateSelector onTemplateSelect={() => {}} />
      </section>

      {/* Requirements textarea */}
      <section style={{
        marginBottom: '16px',
        padding: '16px 20px',
        border: '0.5px solid rgba(0,0,0,0.12)',
        borderRadius: '12px',
        backgroundColor: 'white',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}>
        <h2 style={{ fontSize: '14px', fontWeight: 600, color: '#1a1a1a', marginBottom: '6px' }}>
          Describe Your Requirements
        </h2>
        <p style={{ fontSize: '13px', color: '#6b6b6b', marginBottom: '10px' }}>
          Tell the AI about your {selectedProvider?.toUpperCase() || 'cloud'} architecture needs, naming conventions, compliance requirements, and specific services.
        </p>
        <textarea
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          placeholder={getPlaceholder()}
          style={{
            width: '100%',
            minHeight: '110px',
            padding: '10px 12px',
            borderRadius: '8px',
            border: '0.5px solid rgba(0,0,0,0.15)',
            fontSize: '13.5px',
            fontFamily: 'inherit',
            resize: 'vertical',
            lineHeight: 1.55,
            color: '#374151',
            outline: 'none',
            transition: 'border-color 0.15s ease',
            boxSizing: 'border-box',
          }}
          onFocus={(e) => e.target.style.borderColor = '#5B4EE8'}
          onBlur={(e) => e.target.style.borderColor = 'rgba(0,0,0,0.15)'}
        />
      </section>

      {/* Detected services */}
      <section style={{ marginBottom: '16px' }}>
        <ExtractedServices />
      </section>

      {/* Action buttons */}
      <section style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}><AnalyseButton /></div>
        <div style={{ flex: 1 }}><ArchitectureDiagramButton /></div>
        <div style={{ flex: 1 }}><InitializeRagButton /></div>
        <ClearButton onClick={reset} />
      </section>

    </main>
  );
};
