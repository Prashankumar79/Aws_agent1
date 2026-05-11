import { useRef } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';

export const UploadDropzone = () => {
  const { setUploadedFile, setUploadedFileObject } = useWorkflowStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const supportedFormats = ['PNG', 'JPG', 'PDF', 'SVG', 'DRAWIO', 'LUCIDCHART'];

  const handleFile = (file: File) => {
    setUploadedFile({
      name: file.name,
      size: file.size > 0 ? (file.size / 1024 / 1024).toFixed(1) + ' MB' : '0.0 MB',
      status: 'ready',
    });
    setUploadedFileObject(file);
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div>
      {/* Top area */}
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <div style={{ 
          display: 'inline-flex', 
          alignItems: 'center', 
          gap: '6px', 
          padding: '6px 12px', 
          backgroundColor: '#EEEDFE', 
          color: '#534AB7', 
          border: '0.5px solid #AFA9EC', 
          borderRadius: '20px', 
          fontSize: '12px',
          marginBottom: '16px'
        }}>
          <svg className="ti ti-sparkles" style={{ width: '14px', height: '14px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
          </svg>
          AI-powered · RAG-retrieved cloud docs
        </div>
        <h1 style={{ fontSize: '22px', fontWeight: 500, lineHeight: 1.35, marginBottom: '8px', color: '#1a1a1a' }}>
          Turn your architecture diagram into a design document
        </h1>
        <p style={{ fontSize: '14px', color: '#6b6b6b' }}>
          Upload any AWS or Azure diagram and get validated, CIS-hardened infrastructure code ready for deployment
        </p>
      </div>

      {/* Drop zone card */}
      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        style={{
          backgroundColor: 'white',
          borderRadius: '12px',
          border: '1.5px dashed rgba(0,0,0,0.2)',
          padding: '60px 40px',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'border-color 0.2s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = '#5B4EE8'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(0,0,0,0.2)'}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleChange}
          accept=".png,.jpg,.jpeg,.pdf,.svg,.drawio"
          style={{ display: 'none' }}
        />
        <div>
          <div style={{ 
            display: 'inline-flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            width: '44px', 
            height: '44px', 
            borderRadius: '10px', 
            border: '0.5px solid rgba(0,0,0,0.12)', 
            marginBottom: '16px'
          }}>
            <svg className="ti ti-upload" style={{ width: '20px', height: '20px', color: '#6b6b6b' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <p style={{ fontSize: '15px', fontWeight: 500, color: '#1a1a1a', marginBottom: '4px' }}>
            Drop your diagram here
          </p>
          <p style={{ fontSize: '13px', color: '#6b6b6b', marginBottom: '16px' }}>
            PNG, JPG, PDF, SVG, Draw.io export (up to 50 MB)
          </p>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handleClick(); }}
            style={{
              backgroundColor: 'transparent',
              border: '0.5px solid rgba(0,0,0,0.28)',
              borderRadius: '8px',
              fontSize: '12.5px',
              padding: '8px 16px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background-color 0.2s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5F3EE'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            <svg className="ti ti-folder-open" style={{ width: '14px', height: '14px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            Choose file
          </button>
        </div>
        <div style={{ marginTop: '16px', display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center' }}>
          {supportedFormats.map((format) => (
            <span
              key={format}
              style={{
                padding: '3px 10px',
                border: '0.5px solid rgba(0,0,0,0.12)',
                borderRadius: '20px',
                fontSize: '11px',
                color: '#6b6b6b'
              }}
            >
              {format}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
