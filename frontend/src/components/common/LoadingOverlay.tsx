/**
 * LoadingOverlay — full-screen spinner shown while the pipeline runs.
 * Used only by AnalyseButton.tsx.
 */
interface LoadingOverlayProps {
  message?: string;
}

export const LoadingOverlay = ({ message }: LoadingOverlayProps) => {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      backgroundColor: 'rgba(255,255,255,0.85)',
      backdropFilter: 'blur(4px)',
    }}>
      {/* Spinner */}
      <div style={{ position: 'relative', width: '56px', height: '56px', marginBottom: '24px' }}>
        <div style={{
          width: '56px', height: '56px', borderRadius: '50%',
          border: '3px solid #EEEDFE',
          borderTopColor: '#5B4EE8',
          animation: 'spin 0.8s linear infinite',
        }} />
      </div>

      <p style={{ fontSize: '16px', fontWeight: 500, color: '#1a1a1a', marginBottom: '6px' }}>
        {message || 'Analysing your architecture...'}
      </p>
      <p style={{ fontSize: '13px', color: '#6b6b6b', marginBottom: '24px' }}>
        This may take 1–3 minutes depending on diagram complexity
      </p>

      {/* Pipeline stage pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {['Vision', 'Context', 'Design Doc', 'Terraform'].map((step, i) => (
          <div key={step} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{
              padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 500,
              backgroundColor: '#EEEDFE', color: '#5B4EE8',
            }}>
              {step}
            </span>
            {i < 3 && <div style={{ width: '16px', height: '1px', backgroundColor: '#D1D5DB' }} />}
          </div>
        ))}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};
