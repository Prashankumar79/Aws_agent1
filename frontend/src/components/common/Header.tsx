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

// 🟢 BEGINNER: Import the global Zustand store so this component can read/write the current step.
import { useWorkflowStore } from '../../store/workflowStore';

// 🟢 BEGINNER: A constant array defining the three navigation tabs at the top of the page.
// Each tab has a step number, label, and icon class.
const TABS = [
  { step: 1, label: 'Upload',          icon: 'ti-upload' },
  { step: 2, label: 'Design document', icon: 'ti-file-description' },
  { step: 3, label: 'Terraform',       icon: 'ti-code' },
  { path: '/architecture-studio', label: 'Architecture Studio', icon: 'ti-sitemap' },
  { path: '/rag-chat', label: 'AI_Assistant', icon: 'ti-message' },
];

// 🟢 BEGINNER: SPA navigation helper — pushes a new URL onto history WITHOUT
// reloading the page (and therefore without wiping the in-memory Zustand store).
// Dispatches a synthetic 'popstate' event so App.tsx (which listens for popstate)
// re-renders with the new pathname.
const navigateTo = (path: string) => {
  if (window.location.pathname === path) return;
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

// 🟢 BEGINNER: The top navigation bar component. It shows the logo, tabs, and user avatar.
// Clicking a tab updates the global currentStep in the workflow store.
export const Header = () => {
  // 🟢 BEGINNER: Subscribe to the Zustand store. Whenever currentStep changes, this component re-renders.
  const { currentStep, setCurrentStep } = useWorkflowStore();
  const currentPath = window.location.pathname;

  const navigateToStep = (step: number) => {
    if (currentPath !== '/') {
      navigateTo('/');
    }
    setCurrentStep(step);
  };

  return (
    // 🟢 BEGINNER: The <header> HTML tag. Inline styles set a fixed height, white background, and bottom border.
    <header style={{ height: '52px', backgroundColor: 'white', borderBottom: '0.5px solid rgba(0,0,0,0.12)' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}>
        {/* 🟢 BEGINNER: Left side — logo and brand name. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '28px', height: '28px', backgroundColor: '#5B4EE8', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="ti ti-rocket" style={{ fontSize: '16px', color: 'white' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span style={{ fontSize: '15px', fontWeight: 500, color: '#1a1a1a' }}>MigrationPilot</span>
            <span style={{ fontSize: '11px', color: '#6b6b6b' }}>HclTech</span>
          </div>
        </div>

        {/* 🟢 BEGINNER: Right side — navigation tabs and user icons. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
          <nav style={{ display: 'flex', gap: '4px', height: '52px', alignItems: 'stretch' }}>
            {/* 🟢 BEGINNER: Loop over the TABS array and render a button for each one. */}
            {TABS.map(tab => {
              // 🟢 BEGINNER: Compare this tab's step number to the global currentStep.
              const isStudioTab = 'path' in tab;
              const isActive = isStudioTab
                ? currentPath === (tab.path || '')
                : currentPath === '/' && tab.step !== undefined && tab.step === currentStep;
              return (
                <button
                  key={isStudioTab ? tab.path : tab.step}
                  onClick={() => {
                    if (isStudioTab && tab.path) {
                      navigateTo(tab.path);
                    } else if (tab.step !== undefined) {
                      navigateToStep(tab.step);
                    }
                  }}
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

          {/* 🟢 BEGINNER: Help icon and user avatar circle. */}
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
