/**
 * ================================================================================
 *   frontend/src/store/workflowStore.ts  —  GLOBAL WORKFLOW STATE
 * ================================================================================
 *
 * PURPOSE:
 *   Single source of truth for the 3-step wizard progression.
 *   Every component that needs to know "what step is the user on?" or
 *   "what job is running?" reads from this store.
 *
 * WHY ZUSTAND:
 *   Zustand is a minimal, hook-based state manager. Much simpler than Redux.
 *   No reducers, no actions, no providers — just a `create()` call.
 *   Any component calls `useWorkflowStore()` to read/write state.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • App.tsx              → reads `currentStep` to decide which page to render
 *   • UploadPage.tsx       → sets uploadedFile, selectedProvider, calls setJobId
 *   • DesignDocPage.tsx    → reads jobId + selectedProvider to stream design doc
 *   • TerraformChatPage   → reads jobId + designDocs for diagram context
 *   • WorkflowStepper.tsx  → reads currentStep + steps for sidebar rendering
 *   • components/AnalyseButton.tsx → sets isAnalyzing, jobId, advances currentStep
 *
 * STATE LIFECYCLE:
 *   1. User uploads file → uploadedFile + uploadedFileObject set
 *   2. User clicks Analyse → isAnalyzing=true, jobId set, currentStep → 2
 *   3. Design doc streams → designDocs populated
 *   4. User clicks Terraform → currentStep → 3
 *   5. User resets → reset() brings everything back to initial state
 *
 * PATTERN: Zustand Flat Store
 *   All state and actions in one flat object. No slices, no selectors.
 * ================================================================================
 */

// 🟢 BEGINNER: Zustand is a lightweight state management library for React.
// "create" makes a global store that any component can read from or write to.
// "persist" is a Zustand middleware that mirrors selected fields to
// localStorage so they survive page reloads and full navigations.
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
// 🟢 BEGINNER: This interface describes EVERY piece of state and every action in our workflow store.
// It's like a contract: any component using this store knows exactly what data and functions are available.
interface WorkflowState {
  currentStep: number;                                            // 🟢 BEGINNER: Which wizard page is active: 1, 2, or 3.
  steps: { id: number; label: string }[];                         // 🟢 BEGINNER: Array of step definitions for the sidebar.
  selectedProvider: string;                                        // 🟢 BEGINNER: "aws", "azure", or "gcp" — the chosen cloud provider.
  uploadedFile: { name: string; size: string; status: string } | null; // 🟢 BEGINNER: File metadata (name, size string, status) for display.
  uploadedFileObject: File | null;                                // 🟢 BEGINNER: The actual raw File object needed for API upload.
  jobId: string | null;                                           // 🟢 BEGINNER: Backend job ID returned after starting the pipeline.
  designDocs: Record<string, any>;                               // 🟢 BEGINNER: Object holding generated design document sections.
  terraformPrompts: { category: string; prompt: string; priority?: string; complexity?: string; depends_on?: string[]; estimated_resources?: number }[];         // 🟢 BEGINNER: Array of terraform prompt objects extracted from the design doc.
  contextPack: any | null;                                        // 🟢 BEGINNER: AI vision analysis result (components, provider, confidence).
  isAnalyzing: boolean;                                          // 🟢 BEGINNER: True while the backend pipeline is running.
  userPrompt: string;
  companyId: string;                                             // 🟢 BEGINNER: Current company ID for multi-tenant template scoping.
  company: any | null;                                            // 🟢 BEGINNER: Current company details.
  selectedTemplateId: string | null;                             // 🟢 BEGINNER: Selected instruction template ID.
  templates: any[];                                              // 🟢 BEGINNER: Cached list of templates for current company.
  architectureJobId: string | null;                              // 🟢 BEGINNER: Job ID for architecture diagram generation.
  architectureGraph: any | null;                                 // 🟢 BEGINNER: Canonical infrastructure graph.
  architectureXml: string | null;                                 // 🟢 BEGINNER: draw.io XML for architecture diagram.
  ragJobId: string | null;                                       // 🟢 BEGINNER: Job ID for RAG document indexing.
  ragIndexed: boolean;                                           // 🟢 BEGINNER: Whether document is indexed for RAG chat.
  designDocStreamStarted: boolean;                               // Tracks if streaming was explicitly started for current job — prevents re-streaming on navigation
  streamedJobId: string | null;                                  // The jobId that was last streamed — prevents re-streaming on navigation
  setCurrentStep: (step: number) => void;                         // 🟢 BEGINNER: Action to change the active wizard step.
  setSelectedProvider: (provider: string) => void;               // 🟢 BEGINNER: Action to set the chosen cloud provider.
  setUploadedFile: (file: { name: string; size: string; status: string } | null) => void; // 🟢 BEGINNER: Action to save file metadata.
  setUploadedFileObject: (file: File | null) => void;           // 🟢 BEGINNER: Action to save the raw File object.
  setJobId: (jobId: string | null) => void;                     // 🟢 BEGINNER: Action to remember the backend job ID.
  setDesignDocs: (docs: Record<string, any>) => void;            // 🟢 BEGINNER: Action to store completed design documents.
  setTerraformPrompts: (prompts: { category: string; prompt: string; priority?: string; complexity?: string; depends_on?: string[]; estimated_resources?: number }[]) => void; // 🟢 BEGINNER: Action to store terraform prompts.
  setContextPack: (pack: any | null) => void;                    // 🟢 BEGINNER: Action to store the AI vision analysis result.
  setIsAnalyzing: (isAnalyzing: boolean) => void;                // 🟢 BEGINNER: Action to toggle the analyzing spinner.
  setUserPrompt: (prompt: string) => void;                       // 🟢 BEGINNER: Action to set the user's free-form prompt.
  setCompanyId: (companyId: string) => void;                     // 🟢 BEGINNER: Action to set the current company ID.
  setCompany: (company: any | null) => void;                      // 🟢 BEGINNER: Action to set the current company details.
  setSelectedTemplateId: (templateId: string | null) => void;      // 🟢 BEGINNER: Action to set the selected template ID.
  setTemplates: (templates: any[]) => void;                       // 🟢 BEGINNER: Action to set the cached template list.
  setArchitectureJobId: (jobId: string | null) => void;          // 🟢 BEGINNER: Action to set architecture diagram job ID.
  setArchitectureGraph: (graph: any | null) => void;              // 🟢 BEGINNER: Action to set canonical infrastructure graph.
  setArchitectureXml: (xml: string | null) => void;                // 🟢 BEGINNER: Action to set draw.io XML.
  setRAGJobId: (jobId: string | null) => void;                    // 🟢 BEGINNER: Action to set RAG indexing job ID.
  setRAGIndexed: (indexed: boolean) => void;                       // 🟢 BEGINNER: Action to set RAG indexed status.
  setDesignDocStreamStarted: (started: boolean) => void;          // Mark that streaming was explicitly triggered for current job
  setStreamedJobId: (jobId: string | null) => void;               // Record which job was last streamed
  reset: () => void;                                             // 🟢 BEGINNER: Action to reset ALL state back to initial values.
}

// 🟢 BEGINNER: Create the global store. The "set" function merges partial state updates into the existing state.
// 🟢 BEGINNER: We wrap with `persist(...)` so a CURATED subset of fields is mirrored
// to localStorage. Without this, navigating to /rag-chat (which is a full page
// load, see Header.tsx) would wipe ragIndexed → user sees the empty state even
// after a successful index. The `partialize` callback below picks ONLY the
// stable identifiers worth persisting; we explicitly avoid persisting the raw
// File object (it can't be JSON-serialised) or the streaming docs (they are
// re-fetched from the backend on demand).
export const useWorkflowStore = create<WorkflowState>()(persist((set) => ({
  currentStep: 1,                     // 🟢 BEGINNER: Start on step 1 (Upload page).
  steps: [                            // 🟢 BEGINNER: Define the three wizard steps shown in the sidebar.
    { id: 1, label: 'Upload' },
    { id: 2, label: 'Design Doc' },
    { id: 3, label: 'Terraform' },
  ],
  selectedProvider: 'aws',            // 🟢 BEGINNER: Default to AWS.
  uploadedFile: null,                 // 🟢 BEGINNER: No file uploaded yet.
  uploadedFileObject: null,           // 🟢 BEGINNER: No raw file object yet.
  jobId: null,                        // 🟢 BEGINNER: No job started yet.
  designDocs: {},                     // 🟢 BEGINNER: Empty object — will hold sections by key.
  terraformPrompts: [],             // 🟢 BEGINNER: Empty array — populated after design doc generation.
  contextPack: null,
  isAnalyzing: false,               // 🟢 BEGINNER: Not analyzing on app start.
  userPrompt: '',                    // 🟢 BEGINNER: No user prompt yet.
  companyId: '',                     // 🟢 BEGINNER: No company selected yet.
  company: null,                     // 🟢 BEGINNER: No company details yet.
  selectedTemplateId: null,        // 🟢 BEGINNER: No template selected yet.
  templates: [],                     // 🟢 BEGINNER: Empty template list.
  architectureJobId: null,         // 🟢 BEGINNER: No architecture diagram job yet.
  architectureGraph: null,         // 🟢 BEGINNER: No architecture graph yet.
  architectureXml: null,           // 🟢 BEGINNER: No draw.io XML yet.
  ragJobId: null,                   // 🟢 BEGINNER: No RAG indexing job yet.
  ragIndexed: false,               // 🟢 BEGINNER: Document not indexed yet.
  designDocStreamStarted: false,   // Stream has not been explicitly started yet.
  streamedJobId: null,             // No job has been streamed yet.
  // 🟢 BEGINNER: Each setter calls set({ field: value }) which updates ONLY that field in the global state.
  setCurrentStep: (step) => set({ currentStep: step }),
  setSelectedProvider: (provider) => set({ selectedProvider: provider }),
  setUploadedFile: (file) => set({ uploadedFile: file }),
  setUploadedFileObject: (file) => set({ uploadedFileObject: file }),
  setJobId: (jobId) => set({ jobId }),
  setDesignDocs: (docs) => set({ designDocs: docs }),
  setTerraformPrompts: (prompts) => set({ terraformPrompts: prompts }),
  setContextPack: (pack) => set({ contextPack: pack }),
  setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setUserPrompt: (userPrompt) => set({ userPrompt }),
  setCompanyId: (companyId) => set({ companyId }),
  setCompany: (company) => set({ company }),
  setSelectedTemplateId: (templateId) => set({ selectedTemplateId: templateId }),
  setTemplates: (templates) => set({ templates }),
  setArchitectureJobId: (jobId) => set({ architectureJobId: jobId }),
  setArchitectureGraph: (graph) => set({ architectureGraph: graph }),
  setArchitectureXml: (xml) => set({ architectureXml: xml }),
  setRAGJobId: (jobId) => set({ ragJobId: jobId }),
  setRAGIndexed: (indexed) => set({ ragIndexed: indexed }),
  setDesignDocStreamStarted: (started) => set({ designDocStreamStarted: started }),
  setStreamedJobId: (jobId) => set({ streamedJobId: jobId }),
  // 🟢 BEGINNER: Reset restores every field to its initial value, useful for "Start Over" functionality.
  reset: () => set({
    currentStep: 1,
    steps: [
      { id: 1, label: 'Upload' },
      { id: 2, label: 'Design Doc' },
      { id: 3, label: 'Terraform' },
    ],
    selectedProvider: 'aws',
    uploadedFile: null,
    uploadedFileObject: null,
    jobId: null,
    designDocs: {},
    terraformPrompts: [],
    contextPack: null,
    isAnalyzing: false,
    userPrompt: '',
    companyId: '',
    company: null,
    selectedTemplateId: null,
    templates: [],
    architectureJobId: null,
    architectureGraph: null,
    architectureXml: null,
    ragJobId: null,
    ragIndexed: false,
    designDocStreamStarted: false,
    streamedJobId: null,
  }),
}), {
  // 🟢 BEGINNER: Persist config — controls what survives a page reload.
  name: 'infrasketch-workflow',
  storage: createJSONStorage(() => localStorage),
  // 🟢 BEGINNER: partialize picks ONLY the stable fields worth persisting.
  // Files can't be JSON-serialised, and large blobs (designDocs, contextPack)
  // are re-fetched from the backend on demand using the persisted IDs.
  partialize: (state) => ({
    selectedProvider: state.selectedProvider,
    companyId: state.companyId,
    selectedTemplateId: state.selectedTemplateId,
    jobId: state.jobId,
    streamedJobId: state.streamedJobId,
    architectureJobId: state.architectureJobId,
    ragJobId: state.ragJobId,
    ragIndexed: state.ragIndexed,
  }),
  version: 2,
}));
