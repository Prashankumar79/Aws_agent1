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

import { create } from 'zustand';

interface WorkflowState {
  currentStep: number;
  steps: { id: number; label: string }[];
  selectedProvider: string;
  uploadedFile: { name: string; size: number; type: string } | null;
  uploadedFileObject: File | null;
  jobId: string | null;
  designDocs: Record<string, any>;
  terraformPrompts: { category: string; prompt: string }[];
  isAnalyzing: boolean;
  setCurrentStep: (step: number) => void;
  setSelectedProvider: (provider: string) => void;
  setUploadedFile: (file: { name: string; size: number; type: string } | null) => void;
  setUploadedFileObject: (file: File | null) => void;
  setJobId: (jobId: string | null) => void;
  setDesignDocs: (docs: Record<string, any>) => void;
  setTerraformPrompts: (prompts: { category: string; prompt: string }[]) => void;
  setIsAnalyzing: (isAnalyzing: boolean) => void;
  reset: () => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
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
  isAnalyzing: false,
  setCurrentStep: (step) => set({ currentStep: step }),
  setSelectedProvider: (provider) => set({ selectedProvider: provider }),
  setUploadedFile: (file) => set({ uploadedFile: file }),
  setUploadedFileObject: (file) => set({ uploadedFileObject: file }),
  setJobId: (jobId) => set({ jobId }),
  setDesignDocs: (docs) => set({ designDocs: docs }),
  setTerraformPrompts: (prompts) => set({ terraformPrompts: prompts }),
  setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
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
    isAnalyzing: false,
  }),
}));
