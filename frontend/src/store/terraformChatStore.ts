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

// 🟢 BEGINNER: Zustand's create function makes a global state store accessible from any component.
import { create } from 'zustand';

// 🟢 BEGINNER: Interface describing one chat message (user question or AI answer).
export interface ChatMessage {
  id: string;                               // 🟢 BEGINNER: Unique identifier for this message.
  role: 'user' | 'assistant' | 'system';     // 🟢 BEGINNER: Who sent it — the user, the AI, or a hidden system instruction.
  content: string;                            // 🟢 BEGINNER: The actual text of the message.
  timestamp: number;                          // 🟢 BEGINNER: Unix timestamp (milliseconds since 1970) for sorting/display.
  model?: string;                             // 🟢 BEGINNER: Optional — which AI model generated this message.
}

// 🟢 BEGINNER: Interface describing one generated code file (e.g., main.tf).
export interface GeneratedFile {
  name: string;       // 🟢 BEGINNER: Filename like "main.tf".
  language: string;   // 🟢 BEGINNER: Programming language for syntax highlighting ("hcl", "bash", etc.).
  content: string;    // 🟢 BEGINNER: The actual code text.
}

// 🟢 BEGINNER: A TypeScript union type — a variable of this type can ONLY be one of these four strings.
export type AIModel =
  | 'claude-sonnet-4-6'
  | 'claude-haiku-4-5'
  | 'gemini-2.5-flash'
  | 'gemini-2.5-pro';

// 🟢 BEGINNER: Interface describing ALL state and actions for the Terraform chat page.
interface ConversationSummary {
  id: string;
  title: string;       // First user message (truncated)
  timestamp: number;
  messageCount: number;
}

interface TerraformChatState {
  messages: ChatMessage[];                    // 🟢 BEGINNER: Array of all chat messages in the conversation.
  generatedFiles: GeneratedFile[];           // 🟢 BEGINNER: Files extracted from the latest AI response.
  activeFile: string | null;                 // 🟢 BEGINNER: Which file is currently shown in the code editor.
  isStreaming: boolean;                      // 🟢 BEGINNER: True while the AI is still typing its response.
  selectedModel: AIModel;                    // 🟢 BEGINNER: Which AI model the user chose (Claude or Gemini).
  showModelDropdown: boolean;                 // 🟢 BEGINNER: Whether the model selector dropdown is open.
  contextVisible: boolean;                   // 🟢 BEGINNER: Whether the diagram context sidebar is visible.
  diagramContext: {                           // 🟢 BEGINNER: Structured data about detected resources from the vision analysis.
    detectedResources: { name: string; service: string; chipColor?: string }[];
    detectedConnections: { from: string; to: string }[];
    cloud: string;
  } | null;
  conversations: ConversationSummary[];      // Persisted conversation history
  activeConversationId: string | null;       // Currently active conversation

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
  saveConversation: () => void;              // Save current chat to history
  loadConversation: (id: string) => void;    // Load a past conversation
  deleteConversation: (id: string) => void;  // Remove from history
}

// 🟢 BEGINNER: Load the user's previously selected model from browser localStorage, or default to Claude Sonnet.
// typeof window !== 'undefined' is needed because localStorage only exists in the browser, not during server-side rendering.
const DEFAULT_MODEL: AIModel =
  (typeof window !== 'undefined' && localStorage.getItem('infrasketch_tf_model') as AIModel) ||
  'claude-sonnet-4-6';

// ── localStorage helpers for conversation persistence ────────────────────────
const CONVERSATIONS_KEY = 'infrasketch_tf_conversations';
const MESSAGES_KEY_PREFIX = 'infrasketch_tf_msgs_';

function loadConversations(): ConversationSummary[] {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveConversations(convos: ConversationSummary[]) {
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(convos.slice(0, 50)));
  } catch {
    // Storage can fail in private browsing or when quota is exceeded.
  }
}

function loadMessages(id: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(MESSAGES_KEY_PREFIX + id);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function persistMessages(id: string, messages: ChatMessage[]) {
  try {
    localStorage.setItem(MESSAGES_KEY_PREFIX + id, JSON.stringify(messages));
  } catch {
    // Chat history persistence is best-effort.
  }
}

function removeMessages(id: string) {
  try {
    localStorage.removeItem(MESSAGES_KEY_PREFIX + id);
  } catch {
    // Ignore storage cleanup failures; in-memory state is already updated.
  }
}

// 🟢 BEGINNER: Create the global store. Any component can read or write this state.
export const useTerraformChatStore = create<TerraformChatState>((set, get) => ({
  messages: [],
  generatedFiles: [],
  activeFile: null,
  isStreaming: false,
  selectedModel: DEFAULT_MODEL,
  showModelDropdown: false,
  contextVisible: false,
  diagramContext: null,
  conversations: loadConversations(),
  activeConversationId: null,

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

  // Save current conversation to history before starting a new one
  saveConversation: () => {
    const { messages, activeConversationId, conversations } = get();
    if (messages.length === 0) return;

    const id = activeConversationId || `conv_${Date.now()}`;
    const firstUserMsg = messages.find(m => m.role === 'user');
    const title = firstUserMsg
      ? firstUserMsg.content.slice(0, 40) + (firstUserMsg.content.length > 40 ? '...' : '')
      : 'Untitled conversation';

    // Persist messages
    persistMessages(id, messages);

    // Update conversation list
    const existing = conversations.filter(c => c.id !== id);
    const updated: ConversationSummary[] = [
      { id, title, timestamp: Date.now(), messageCount: messages.length },
      ...existing,
    ].slice(0, 50);

    saveConversations(updated);
    set({ conversations: updated, activeConversationId: id });
  },

  // Load a past conversation
  loadConversation: (id) => {
    const msgs = loadMessages(id);
    set({
      messages: msgs,
      activeConversationId: id,
      generatedFiles: [],
      activeFile: null,
      isStreaming: false,
    });
  },

  // Delete a conversation from history
  deleteConversation: (id) => {
    removeMessages(id);
    const { conversations } = get();
    const updated = conversations.filter(c => c.id !== id);
    saveConversations(updated);
    set({ conversations: updated });
  },

  // Reset: save current conversation first, then clear
  reset: () => {
    const { messages, saveConversation: save } = get();
    if (messages.length > 0) {
      save(); // Auto-save before clearing
    }
    set({
      messages: [],
      generatedFiles: [],
      activeFile: null,
      isStreaming: false,
      contextVisible: false,
      diagramContext: null,
      activeConversationId: null,
    });
  },
}));
