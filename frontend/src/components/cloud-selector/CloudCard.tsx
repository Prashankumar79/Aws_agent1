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

import { CloudProvider } from '../../types/schema';

interface CloudCardProps {
  provider: CloudProvider;
  isSelected: boolean;
  onSelect: (providerId: string) => void;
}

export const CloudCard = ({ provider, isSelected, onSelect }: CloudCardProps) => {
  const isAWS = provider.id === 'aws';
  
  return (
    <div
      onClick={() => onSelect(provider.id)}
      style={{
        backgroundColor: isSelected && isAWS ? '#FAEEDA' : 'white',
        borderRadius: '12px',
        border: isSelected && isAWS ? '1.5px solid #E8A020' : '0.5px solid rgba(0,0,0,0.12)',
        padding: '18px',
        cursor: 'pointer',
        position: 'relative',
        transition: 'border-color 0.2s ease'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ 
          display: 'inline-flex', 
          padding: '4px 12px', 
          borderRadius: '20px', 
          fontSize: '12px', 
          fontWeight: 500,
          backgroundColor: isSelected && isAWS ? '#FAC775' : '#B5D4F4',
          color: isSelected && isAWS ? '#633806' : '#0C447C'
        }}>
          {provider.name}
        </div>
        <div style={{ position: 'absolute', top: '12px', right: '12px' }}>
          {isSelected ? (
            <div style={{ width: '18px', height: '18px', borderRadius: '50%', backgroundColor: isAWS ? '#E8A020' : '#5B4EE8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg style={{ width: '12px', height: '12px', color: 'white' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          ) : (
            <div style={{ width: '18px', height: '18px', borderRadius: '50%', border: '0.5px solid rgba(0,0,0,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
          )}
        </div>
      </div>
      <div style={{ fontSize: '14px', fontWeight: 500, color: '#1a1a1a', marginBottom: '4px' }}>
        {provider.fullName}
      </div>
      <div style={{ fontSize: '12px', color: '#6b6b6b' }}>
        {provider.services.join(', ')}
      </div>
    </div>
  );
};
