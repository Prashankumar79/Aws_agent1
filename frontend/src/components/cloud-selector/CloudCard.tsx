/**
 * CloudCard — clickable card for selecting a cloud provider.
 *
 * PURPOSE:
 *   Displays a single cloud provider (AWS or Azure) with its services list,
 *   visual selection state (checkmark, highlighted border), and hover effects.
 *
 * WHY IT EXISTS:
 *   Abstracted from CloudSelector so the card UI logic (colors, icons,
 *   selection feedback) lives in its own testable unit.
 *
 * CONNECTIONS:
 *   • CloudSelector.tsx  → renders one CloudCard per provider
 *   • UploadPage.tsx     → contains the CloudSelector section
 */

// 🟢 BEGINNER: Import the CloudProvider type so TypeScript knows the shape of the provider prop.
import { CloudProvider } from '../../types/schema';

// 🟢 BEGINNER: Props interface — the parent tells us which provider to show,
// whether it's selected, and what function to call when clicked.
interface CloudCardProps {
  provider: CloudProvider;
  isSelected: boolean;
  onSelect: (providerId: string) => void;
}

// 🟢 BEGINNER: A clickable card that shows one cloud provider (AWS or Azure).
// It changes colors and shows a checkmark when selected.
// Provider color schemes
const PROVIDER_STYLES: Record<string, { selectedBg: string; selectedBorder: string; pillBg: string; pillText: string; checkBg: string }> = {
  aws:   { selectedBg: '#FAEEDA', selectedBorder: '#E8A020', pillBg: '#FAC775', pillText: '#633806', checkBg: '#E8A020' },
  azure: { selectedBg: '#E8F4FD', selectedBorder: '#0C447C', pillBg: '#B5D4F4', pillText: '#0C447C', checkBg: '#5B4EE8' },
  gcp:   { selectedBg: '#E8F5E9', selectedBorder: '#34A853', pillBg: '#A8D5BA', pillText: '#1B5E20', checkBg: '#34A853' },
};

export const CloudCard = ({ provider, isSelected, onSelect }: CloudCardProps) => {
  const styles = PROVIDER_STYLES[provider.id] || PROVIDER_STYLES.azure;

  return (
    // 🟢 BEGINNER: The card container. onClick calls the onSelect function passed from the parent.
    <div
      onClick={() => onSelect(provider.id)}
      style={{
        backgroundColor: isSelected ? styles.selectedBg : 'white',
        borderRadius: '12px',
        border: isSelected ? `1.5px solid ${styles.selectedBorder}` : '0.5px solid rgba(0,0,0,0.12)',
        padding: '18px',
        cursor: 'pointer',
        position: 'relative',
        transition: 'border-color 0.2s ease, background-color 0.2s ease'
      }}
    >
      {/* 🟢 BEGINNER: Top row — provider name pill and selection checkmark. */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        {/* 🟢 BEGINNER: The colored pill badge showing the provider name. */}
        <div style={{
          display: 'inline-flex',
          padding: '4px 12px',
          borderRadius: '20px',
          fontSize: '12px',
          fontWeight: 500,
          backgroundColor: isSelected ? styles.pillBg : '#F0F0F0',
          color: isSelected ? styles.pillText : '#555555'
        }}>
          {provider.name}
        </div>
        {/* 🟢 BEGINNER: Top-right corner — show a filled checkmark circle if selected, empty circle if not. */}
        <div style={{ position: 'absolute', top: '12px', right: '12px' }}>
          {isSelected ? (
            <div style={{ width: '18px', height: '18px', borderRadius: '50%', backgroundColor: styles.checkBg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg style={{ width: '12px', height: '12px', color: 'white' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          ) : (
            <div style={{ width: '18px', height: '18px', borderRadius: '50%', border: '0.5px solid rgba(0,0,0,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
          )}
        </div>
      </div>
      {/* 🟢 BEGINNER: Full provider name and list of supported services. */}
      <div style={{ fontSize: '14px', fontWeight: 500, color: '#1a1a1a', marginBottom: '4px' }}>
        {provider.fullName}
      </div>
      <div style={{ fontSize: '12px', color: '#6b6b6b' }}>
        {provider.services.join(', ')}
      </div>
    </div>
  );
};
