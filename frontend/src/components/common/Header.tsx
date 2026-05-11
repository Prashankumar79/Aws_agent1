/**
 * Header — top navigation bar with branding and workflow tabs.
 *
 * PURPOSE:
 *   Shows the InfraSketch logo, three workflow tabs (Upload, Design doc,
 *   Terraform), and a user avatar. Tabs are clickable for navigation.
 *
 * CONNECTIONS:
 *   • App.tsx          → renders Header at the top of every page
 *   • workflowStore.ts → currentStep / setCurrentStep controls tab state
 */

import { useWorkflowStore } from '../../store/workflowStore';

const TABS = [
  { step: 1, label: 'Upload',          icon: 'ti-upload' },
  { step: 2, label: 'Design document', icon: 'ti-file-description' },
  { step: 3, label: 'Terraform',       icon: 'ti-code' },
];

export const Header = () => {
  const { currentStep, setCurrentStep } = useWorkflowStore();

  return (
    <header style={{ height: '52px', backgroundColor: 'white', borderBottom: '0.5px solid rgba(0,0,0,0.12)' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '28px', height: '28px', backgroundColor: '#5B4EE8', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="ti ti-box" style={{ fontSize: '16px', color: 'white' }} />
          </div>
          <span style={{ fontSize: '15px', fontWeight: 500, color: '#1a1a1a' }}>InfraSketch</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
          <nav style={{ display: 'flex', gap: '4px', height: '52px', alignItems: 'stretch' }}>
            {TABS.map(tab => {
              const isActive = tab.step === currentStep;
              return (
                <button
                  key={tab.step}
                  onClick={() => setCurrentStep(tab.step)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '0 14px',
                    fontSize: '13.5px',
                    fontWeight: isActive ? 500 : 400,
                    color: isActive ? '#5B4EE8' : '#6b6b6b',
                    borderBottom: isActive ? '2px solid #5B4EE8' : '2px solid transparent',
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <i className={`ti ${tab.icon}`} style={{ fontSize: '15px' }} />
                  {tab.label}
                </button>
              );
            })}
          </nav>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button style={{ width: '30px', height: '30px', borderRadius: '50%', border: '0.5px solid rgba(0,0,0,0.12)', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <i className="ti ti-help" style={{ fontSize: '16px', color: '#6b6b6b' }} />
            </button>
            <div style={{ width: '30px', height: '30px', borderRadius: '50%', backgroundColor: '#5B4EE8', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontSize: '12px', fontWeight: 500 }}>
              IS
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
