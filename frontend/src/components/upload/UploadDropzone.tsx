/**
 * UploadDropzone — file input area with drag-and-drop support.
 * Redesigned to match MigrationPilot reference UI.
 */

import { useRef, useState } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';

export const UploadDropzone = () => {
  const { setUploadedFile, setUploadedFileObject } = useWorkflowStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const supportedFormats = ['PNG', 'JPG', 'PDF', 'SVG', 'DOCX', 'TXT', 'MD', 'CSV', 'XLSX'];

  const handleFile = (file: File) => {
    setUploadedFile({
      name: file.name,
      size: file.size > 0 ? (file.size / 1024 / 1024).toFixed(1) + ' MB' : '0.0 MB',
      status: 'ready',
    });
    setUploadedFileObject(file);
  };

  const handleClick = () => fileInputRef.current?.click();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  return (
    <div style={{ maxWidth: '860px', margin: '0 auto', width: '100%' }}>

      {/* ── Hero info card ─────────────────────────────────────────────── */}
      <div style={{
        textAlign: 'center',
        padding: '28px 32px 24px',
        background: 'linear-gradient(135deg, #EEEDFE 0%, #E8E6FD 100%)',
        border: '1px solid #C7C3F9',
        borderRadius: '16px',
        marginBottom: '16px',
      }}>
        {/* AI powered pill */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '5px 14px',
          backgroundColor: '#5B4EE8',
          color: 'white',
          borderRadius: '20px',
          fontSize: '12px',
          fontWeight: 500,
          marginBottom: '16px',
          boxShadow: '0 2px 8px rgba(91,78,232,0.35)',
        }}>
          <svg style={{ width: '13px', height: '13px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
          </svg>
          AI powered
        </div>

        <h1 style={{ fontSize: '24px', fontWeight: 600, color: '#1a1a1a', marginBottom: '10px', letterSpacing: '-0.3px' }}>
          Upload Migration Document
        </h1>
        <p style={{ fontSize: '13.5px', color: '#4B5563', marginBottom: '10px', lineHeight: 1.6, maxWidth: '640px', margin: '0 auto 10px' }}>
          The multi-agent pipeline will parse your document, analyze architecture diagrams, extract migration requirements, and generate a design document with Terraform configuration.
        </p>
        <p style={{ fontSize: '12.5px', color: '#5B4EE8', fontWeight: 500 }}>
          Supports PDF, DOCX, PNG, JPG — architecture diagrams, HLD/LLD documents, or inventory exports.
        </p>
      </div>

      {/* ── Dropzone card ──────────────────────────────────────────────── */}
      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        style={{
          backgroundColor: isDragging ? '#F5F3FF' : 'white',
          borderRadius: '16px',
          border: isDragging ? '2px dashed #5B4EE8' : '1.5px dashed #D1D5DB',
          padding: '52px 40px 36px',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'border-color 0.2s ease, background-color 0.2s ease',
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        }}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleChange}
          accept=".png,.jpg,.jpeg,.pdf,.svg,.drawio,.docx,.txt,.md,.csv,.xlsx,.xls"
          style={{ display: 'none' }}
        />

        {/* Upload icon */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '48px',
          height: '48px',
          borderRadius: '12px',
          backgroundColor: '#F3F4F6',
          marginBottom: '16px',
        }}>
          <svg style={{ width: '22px', height: '22px', color: '#6B7280' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>

        <p style={{ fontSize: '15px', fontWeight: 500, color: '#111827', marginBottom: '4px' }}>
          Drag and drop file here
        </p>
        <p style={{ fontSize: '13px', color: '#9CA3AF', marginBottom: '20px' }}>
          or click to browse — max 50 MB
        </p>

        {/* Choose file button */}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); handleClick(); }}
          style={{
            backgroundColor: 'white',
            border: '1px solid #D1D5DB',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 500,
            padding: '8px 20px',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '7px',
            color: '#374151',
            transition: 'background-color 0.15s ease, border-color 0.15s ease',
            marginBottom: '24px',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#F9FAFB';
            e.currentTarget.style.borderColor = '#9CA3AF';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'white';
            e.currentTarget.style.borderColor = '#D1D5DB';
          }}
        >
          <svg style={{ width: '14px', height: '14px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          Choose file
        </button>

        {/* Format pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', justifyContent: 'center' }}>
          {supportedFormats.map((fmt) => (
            <span
              key={fmt}
              style={{
                padding: '3px 10px',
                border: '1px solid #E5E7EB',
                borderRadius: '20px',
                fontSize: '11.5px',
                color: '#6B7280',
                backgroundColor: '#F9FAFB',
                fontWeight: 400,
              }}
            >
              {fmt}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
