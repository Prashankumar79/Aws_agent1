/**
 * ================================================================================
 *   frontend/src/store/terraformChatStore.ts  —  TERRAFORM CHAT STATE
 * ================================================================================
 *
 * PURPOSE:
 *   Manages all state for the Terraform chat interface (Step 3):
 *   chat history, generated HCL files, active file selection, streaming
 *   status, AI model choice, and the detected diagram context.
 *
 * WHY SEPARATE FROM workflowStore:
 *   workflowStore manages the wizard pipeline (step progression, job ID).
 *   terraformChatStore manages the conversational UI state — these are
 *   different concerns with different lifecycles. Separating them keeps
 *   each store small and focused.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • TerraformChatPage.tsx  → primary consumer: reads/writes all state here
 *   • workflowStore.ts       → reads jobId + designDocs to build diagramContext
 *   • services/api.ts        → streamTerraformChat() updates messages here
 *
 * KEY STATE:
 *   messages[]         Chat history in Anthropic format (role + content)
 *   generatedFiles[]   Parsed HCL files from the latest assistant response
 *   activeFile         Which file the code editor is displaying
 *   isStreaming        True while a Bedrock/Gemini response is in-flight
 *   selectedModel      Which AI model to call (persisted to localStorage)
 *   diagramContext     Vision analysis output injected into every system prompt
 *
 * PERSISTENCE:
 *   selectedModel is persisted to localStorage so the user's model preference
 *   survives a page refresh. All other state is in-memory only.
 *
 * PATTERN: Zustand Flat Store with action co-location
 *   Actions and state live in the same object. `updateLastMessage` is the
 *   most complex action — it mutates the last assistant message in-place
 *   during streaming to produce a typewriter effect.
 * ================================================================================
 */

import { create } from 'zustand';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  model?: string;
}

export interface GeneratedFile {
  name: string;
  language: string;
  content: string;
}

export type AIModel =
  | 'claude-sonnet-4-6'
  | 'claude-haiku-4-5'
  | 'gemini-2.5-flash'
  | 'gemini-2.5-pro';

interface TerraformChatState {
  messages: ChatMessage[];
  generatedFiles: GeneratedFile[];
  activeFile: string | null;
  isStreaming: boolean;
  selectedModel: AIModel;
  showModelDropdown: boolean;
  contextVisible: boolean;
  diagramContext: {
    detectedResources: { name: string; service: string; chipColor?: string }[];
    detectedConnections: { from: string; to: string }[];
    cloud: string;
  } | null;

  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (content: string) => void;
  setGeneratedFiles: (files: GeneratedFile[]) => void;
  setActiveFile: (name: string | null) => void;
  setIsStreaming: (val: boolean) => void;
  setSelectedModel: (model: AIModel) => void;
  setShowModelDropdown: (val: boolean) => void;
  setContextVisible: (val: boolean) => void;
  setDiagramContext: (ctx: TerraformChatState['diagramContext']) => void;
  reset: () => void;
}

const DEFAULT_MODEL: AIModel =
  (typeof window !== 'undefined' && localStorage.getItem('infrasketch_tf_model') as AIModel) ||
  'claude-sonnet-4-6';

export const useTerraformChatStore = create<TerraformChatState>((set) => ({
  messages: [],
  generatedFiles: [],
  activeFile: null,
  isStreaming: false,
  selectedModel: DEFAULT_MODEL,
  showModelDropdown: false,
  contextVisible: false,
  diagramContext: null,

  setMessages: (messages) => set({ messages }),
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateLastMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages];
      if (msgs.length > 0 && msgs[msgs.length - 1].role === 'assistant') {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
      }
      return { messages: msgs };
    }),
  setGeneratedFiles: (files) => set({ generatedFiles: files }),
  setActiveFile: (name) => set({ activeFile: name }),
  setIsStreaming: (val) => set({ isStreaming: val }),
  setSelectedModel: (model) => {
    localStorage.setItem('infrasketch_tf_model', model);
    set({ selectedModel: model });
  },
  setShowModelDropdown: (val) => set({ showModelDropdown: val }),
  setContextVisible: (val) => set({ contextVisible: val }),
  setDiagramContext: (ctx) => set({ diagramContext: ctx }),
  reset: () =>
    set({
      messages: [],
      generatedFiles: [],
      activeFile: null,
      isStreaming: false,
      contextVisible: false,
      diagramContext: null,
    }),
}));
