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

// 🟢 BEGINNER: useEffect/useState for SPA navigation; the React import isn't needed
// because Vite/TypeScript use the modern JSX transform.
import { useEffect, useState } from 'react';
// 🟢 BEGINNER: Import the sidebar stepper component (shows Upload → Design Doc → Terraform progress).
import { WorkflowStepper } from './components/workflow/WorkflowStepper';
// 🟢 BEGINNER: Import the three main page components. Only one is rendered at a time based on currentStep.
import { UploadPage } from './pages/UploadPage';
import { DesignDocPage } from './pages/DesignDocPage';
import { TerraformChatPage } from './pages/TerraformChatPage';
import ArchitectureStudio from './pages/ArchitectureStudio';
import { RagChatPage } from './pages/RagChatPage';
// 🟢 BEGINNER: Import shared layout components (top navigation bar and bottom footer).
import { Header } from './components/common/Header';
import { Footer } from './components/common/Footer';
// 🟢 BEGINNER: Import the global Zustand store so we know which wizard step is active.
import { useWorkflowStore } from './store/workflowStore';

function App() {
  // 🟢 BEGINNER: Subscribe to the global store. Whenever currentStep changes (e.g., user clicks a tab
  // or the pipeline advances), this component re-renders and shows the correct page.
  const { currentStep } = useWorkflowStore();

  // 🟢 BEGINNER: Track the URL pathname in React state so SPA navigation
  // (pushState + popstate event) actually re-renders the app. Without this,
  // navigating to /rag-chat would update the URL but the page wouldn't switch.
  const [pathname, setPathname] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // 🟢 BEGINNER: Check if we're on the Architecture Studio or RAG Chat page (separate routes)
  const isArchitectureStudio = pathname === '/architecture-studio';
  const isRAGChat = pathname === '/rag-chat';
  // 🟢 BEGINNER: Sidebar shows ONLY on the Design Doc step. Upload and Terraform
  // pages have their own dense layouts and don't benefit from the stepper.
  const showSidebar = !isArchitectureStudio && !isRAGChat && currentStep === 2;

  // 🟢 BEGINNER: Return the appropriate page based on currentStep or route
  const renderPage = () => {
    if (isArchitectureStudio) {
      return <ArchitectureStudio />;
    }
    
    if (isRAGChat) {
      return <RagChatPage />;
    }
    
    switch (currentStep) {
      case 1:
        return <UploadPage />;          // 🟢 BEGINNER: Step 1 — file upload and cloud selection.
      case 2:
        return <DesignDocPage />;       // 🟢 BEGINNER: Step 2 — streaming AI-generated design document.
      case 3:
        return <TerraformChatPage />;  // 🟢 BEGINNER: Step 3 — chat with AI to generate Terraform code.
      default:
        return <UploadPage />;
    }
  };

  return (
    // 🟢 BEGINNER: The root container. minHeight: 100vh ensures it fills the entire screen height.
    // display: flex + flexDirection: column stacks Header, Content, and Footer vertically.
    <div style={{ minHeight: '100vh', backgroundColor: '#F2F2F7', color: '#1a1a1a', display: 'flex', flexDirection: 'column' }}>
      {/* 🟢 BEGINNER: Top navigation bar with logo and tabs. Always visible. */}
      <Header />

      {/* 🟢 BEGINNER: Main content area. display: flex puts the sidebar and page side-by-side. flex: 1 makes this area grow to fill available space. */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 🟢 BEGINNER: Sidebar stepper is shown ONLY on the Design Doc step. */}
        {showSidebar && <WorkflowStepper />}

        {/* 🟢 BEGINNER: The active page is rendered here. Always with consistent padding. */}
        <main style={{ flex: 1, padding: '24px', overflow: 'hidden' }}>
          {renderPage()}
        </main>
      </div>

      {/* 🟢 BEGINNER: Bottom footer with copyright and links. Always visible. */}
      <Footer />
    </div>
  );
}

export default App;
