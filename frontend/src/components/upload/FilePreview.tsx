/**
 * FilePreview — displays the uploaded file name, size, and status badge.
 */
import { UploadedFile } from '../../types/schema';

interface FilePreviewProps {
  file: UploadedFile;
}

export const FilePreview = ({ file }: FilePreviewProps) => {
  return (
    <div style={{
      backgroundColor: 'white',
      borderRadius: '12px',
      border: '0.5px solid rgba(0,0,0,0.12)',
      padding: '12px 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '36px', height: '36px',
          backgroundColor: '#EEF2FF',
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <svg style={{ width: '18px', height: '18px', color: '#5B4EE8' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <p style={{ fontSize: '13.5px', fontWeight: 500, color: '#111827', marginBottom: '2px' }}>{file.name}</p>
          <p style={{ fontSize: '12px', color: '#6b6b6b' }}>{file.size} · ready to analyse</p>
        </div>
      </div>
      <span style={{
        padding: '3px 10px',
        backgroundColor: '#ECFDF5',
        color: '#065F46',
        borderRadius: '20px',
        fontSize: '12px',
        fontWeight: 500,
      }}>
        ✓ {file.status}
      </span>
    </div>
  );
};
