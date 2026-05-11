interface NotificationProps {
  message: string;
  type?: 'info' | 'success' | 'warning' | 'error';
}

export const Notification = ({ message, type = 'info' }: NotificationProps) => {
  return (
    <div style={{ 
      backgroundColor: '#E6F1FB', 
      borderRadius: '8px', 
      padding: '10px 14px',
      display: 'flex',
      alignItems: 'center',
      gap: '10px'
    }}>
      <svg className="ti ti-info-circle" style={{ width: '16px', height: '16px', color: '#185FA5' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span style={{ fontSize: '12.5px', color: '#185FA5' }}>{message}</span>
    </div>
  );
};
