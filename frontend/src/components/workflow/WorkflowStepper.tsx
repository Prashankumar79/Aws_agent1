/**
 * WorkflowStepper — sidebar showing pipeline progress (1 → 2 → 3).
 *
 * PURPOSE:
 *   Visualizes which of the three workflow stages (Upload, Design doc,
 *   Terraform) is active, completed, or pending. Uses a colored vertical
 *   line and step indicators with animated transitions.
 *
 * WHY IT EXISTS:
 *   Gives users immediate orientation about where they are in the
 *   overall pipeline and what comes next.
 *
 * CONNECTIONS:
 *   • workflowStore.ts → steps array, currentStep
 *   • App.tsx         → rendered as the left sidebar
 */

// 🟢 BEGINNER: Import the global Zustand store to read the current wizard step list and active step.
import { useWorkflowStore } from '../../store/workflowStore';

// 🟢 BEGINNER: Sidebar component that shows the 3-step wizard progress (Upload → Design Doc → Terraform).
// It uses a vertical line, colored circles, and text labels to indicate where the user is.
export const WorkflowStepper = () => {
  const { steps, currentStep, designDocs, selectedProvider, streamedJobId, jobId } = useWorkflowStore();

  // Determine if design doc is complete (has cached content)
  const designDocComplete = !!(designDocs[selectedProvider]?.content);
  // Determine if streaming has been done for this job
  const hasStreamed = streamedJobId === jobId && !!jobId;

  return (
    <aside style={{ width: '220px', backgroundColor: 'white', borderRight: '0.5px solid rgba(0,0,0,0.12)', padding: '12px 0', overflowY: 'auto' }}>
      <div style={{ padding: '12px 10px 6px' }}>
        <span style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b' }}>WORKFLOW</span>
      </div>
      <div style={{ position: 'relative' }}>
        <div style={{ position: 'absolute', left: '11px', top: '11px', bottom: '11px', width: '0.5px', backgroundColor: '#E5E7EB', zIndex: '-1' }} />
        <div
          style={{
            position: 'absolute',
            left: '11px',
            top: '11px',
            width: '0.5px',
            backgroundColor: '#5B4EE8',
            transition: 'all 0.7s ease-out',
            zIndex: '-1',
            height: `${((currentStep - 1) / (steps.length - 1)) * 100}%`
          }}
        />

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {steps.map((step) => {
            const isActive = step.id === currentStep;
            const isCompleted = step.id < currentStep;

            // Dynamic sub-label for Design Doc step
            let subLabel = '';
            if (step.id === 2 && isActive) {
              if (designDocComplete) {
                subLabel = 'Complete';
              } else if (hasStreamed) {
                subLabel = 'Streaming...';
              } else {
                subLabel = 'In progress...';
              }
            }

            return (
              <div
                key={step.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  transition: 'all 0.5s',
                  transform: isActive ? 'translateX(4px)' : 'translateX(0)'
                }}
              >
                <div style={{ position: 'relative' }}>
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '13px',
                      fontWeight: 600,
                      transition: 'all 0.5s',
                      backgroundColor: isActive
                        ? (designDocComplete && step.id === 2 ? '#10B981' : '#5B4EE8')
                        : isCompleted
                        ? '#10B981'
                        : '#F3F4F6',
                      color: (isActive || isCompleted) ? 'white' : '#9CA3AF',
                      transform: isActive ? 'scale(1.1)' : 'scale(1)'
                    }}
                  >
                    {(isCompleted || (isActive && designDocComplete && step.id === 2)) ? (
                      <svg style={{ width: '14px', height: '14px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      step.id
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span
                    style={{
                      fontWeight: 500,
                      transition: 'color 0.5s',
                      fontSize: '13px',
                      color: isActive ? '#1a1a1a' : isCompleted ? '#1a1a1a' : '#9CA3AF'
                    }}
                  >
                    {step.label}
                  </span>
                  {isActive && (
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 500,
                      color: designDocComplete && step.id === 2 ? '#10B981' : '#5B4EE8',
                    }}>
                      {subLabel || 'In progress...'}
                    </span>
                  )}
                  {isCompleted && (
                    <span style={{ fontSize: '11px', color: '#10B981', fontWeight: 500 }}>
                      Completed
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
