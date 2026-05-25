/**
 * Notification — info / success / warning / error banner.
 *
 * PURPOSE:
 *   Displays contextual messages to the user (e.g. "RAG pipeline will
 *   retrieve up-to-date cloud provider documentation...").
 *
 * CONNECTIONS:
 *   • UploadPage.tsx → renders an info notification above action buttons
 */

// 🟢 BEGINNER: This defines the input props (properties) that this component accepts.
// TypeScript will warn us if we forget to pass "message" or pass the wrong "type".
interface NotificationProps {
  message: string;                    // 🟢 BEGINNER: The text to display inside the banner.
  type?: 'info' | 'success' | 'warning' | 'error';  // 🟢 BEGINNER: Visual style; "?" means it's optional (defaults to 'info').
}

// 🟢 BEGINNER: A functional React component that displays a colored info banner.
// It receives "message" and "type" from its parent component.
export const Notification = ({ message, type = 'info' }: NotificationProps) => {
  return (
    // 🟢 BEGINNER: Inline styles set the background color, padding, and layout (flex with centered items).
    <div style={{
      backgroundColor: '#E6F1FB',
      borderRadius: '8px',
      padding: '10px 14px',
      display: 'flex',
      alignItems: 'center',
      gap: '10px'
    }}>
      {/* 🟢 BEGINNER: An SVG icon (info circle) drawn with vector paths. It scales without getting blurry. */}
      <svg className="ti ti-info-circle" style={{ width: '16px', height: '16px', color: '#185FA5' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {/* 🟢 BEGINNER: The actual text message passed from the parent. */}
      <span style={{ fontSize: '12.5px', color: '#185FA5' }}>{message}</span>
    </div>
  );
};
