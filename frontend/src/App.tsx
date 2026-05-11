/**
 * ================================================================================
 *   frontend/src/App.tsx  —  ROOT APPLICATION COMPONENT
 * ================================================================================
 *
 * PURPOSE:
 *   The layout shell. It renders the Header, Footer, WorkflowStepper sidebar,
 *   and switches between the three main pages based on currentStep.
 *
 * WHY IT EXISTS:
 *   Every React app needs a root component. This one acts as a lightweight
 *   router / state machine: step 1 = upload, step 2 = design doc, step 3 = terraform.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • store/workflowStore.ts        → currentStep drives page switching
 *   • components/workflow/WorkflowStepper.tsx  → sidebar showing 1-2-3 progress
 *   • pages/UploadPage.tsx          → step 1: diagram upload
 *   • pages/DesignDocPage.tsx         → step 2: streaming design doc viewer
 *   • pages/TerraformChatPage.tsx     → step 3: AI chat + code generation
 *   • components/common/Header.tsx    → top navigation bar
 *   • components/common/Footer.tsx    → bottom credits / links
 *
 * STATE MACHINE:
 *   Step 1 (Upload)    → user uploads diagram, clicks Analyse
 *   Step 2 (Design Doc)  → vision analysis runs, design doc streams
 *   Step 3 (Terraform)   → user chats with AI to generate infrastructure code
 *
 * NOTE ON LAYOUT:
 *   Step 3 (TerraformChatPage) gets zero padding because it handles its own
 *   full-screen layout with a chat panel and code editor side-by-side.
 * ================================================================================
 */

import React from 'react';
import { WorkflowStepper } from './components/workflow/WorkflowStepper';
import { UploadPage } from './pages/UploadPage';
import { DesignDocPage } from './pages/DesignDocPage';
import { TerraformChatPage } from './pages/TerraformChatPage';
import { Header } from './components/common/Header';
import { Footer } from './components/common/Footer';
import { useWorkflowStore } from './store/workflowStore';

function App() {
  // Pull the current wizard step from global Zustand store.
  // This is the single source of truth for "which page am I on?"
  const { currentStep } = useWorkflowStore();

  // ── Page router ──────────────────────────────────────────────────────────
  // Simple switch — no react-router needed because the flow is strictly linear.
  // The user progresses 1 → 2 → 3; there are no deep links or back buttons.
  const renderPage = () => {
    switch (currentStep) {
      case 1:
        return <UploadPage />;         // Diagram upload + cloud selection
      case 2:
        return <DesignDocPage />;      // Streaming design document
      case 3:
        return <TerraformChatPage />;  // Conversational Terraform generation
      default:
        return <UploadPage />;
    }
  };

  return (
    // Full-height flex column: Header → Content → Footer
    <div style={{ minHeight: '100vh', backgroundColor: '#F5F3EE', color: '#1a1a1a', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar with app logo and navigation */}
      <Header />

      {/* Main content area: sidebar + page */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Stepper sidebar is hidden on step 3 (Terraform has its own layout) */}
        {currentStep !== 3 && <WorkflowStepper />}

        {/* Page content — padding varies by step */}
        <main style={{ flex: 1, padding: currentStep === 3 ? 0 : '24px', overflow: 'hidden' }}>
          {renderPage()}
        </main>
      </div>

      {/* Bottom bar */}
      <Footer />
    </div>
  );
}

export default App;
