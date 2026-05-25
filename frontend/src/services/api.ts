/**
 * ================================================================================
 *   frontend/src/services/api.ts  —  BACKEND HTTP CLIENT
 * ================================================================================
 *
 * PURPOSE:
 *   All HTTP communication between the React frontend and the FastAPI backend
 *   lives here. Components never call `fetch()` directly — they call api.*.
 *   This keeps network logic centralized and easy to mock for testing.
 *
 * WHY EMPTY API_BASE_URL:
 *   vite.config.ts (or vite.config.js) defines a proxy:
 *     "/api" → "http://localhost:8000"
 *   So fetch("/api/v1/...") goes to the backend without CORS issues.
 *   In production, nginx would proxy the same paths.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • UploadPage.tsx / AnalyseButton.tsx  → api.startPipeline() + waitForCompletion()
 *   • DesignDocPage.tsx                   → api.getJobStatus() + downloadDesignDocPdf()
 *   • TerraformChatPage.tsx               → api.streamTerraformChat()
 *   • backend/api/v1/jobs.py              → all endpoints consumed here
 *
 * BACKEND ENDPOINTS USED:
 *   POST /api/v1/jobs/                                  → startPipeline()
 *   GET  /api/v1/jobs/:id                               → getJobStatus()
 *   GET  /api/v1/jobs/:id/stream-design-doc-sections    → DesignDocPage.tsx (direct fetch)
 *   POST /api/v1/jobs/terraform/chat/stream             → streamTerraformChat()
 *   GET  /api/v1/jobs/:id/design-doc/:cloud             → downloadDesignDocPdf()
 *
 * NOTE ON STREAMING:
 *   DesignDocPage.tsx opens the SSE stream directly (not through api.ts) because
 *   it needs fine-grained control over AbortController and ReadableStream.
 *   streamTerraformChat() IS in api.ts and uses an AsyncGenerator pattern.
 * ================================================================================
 */

// 🟢 BEGINNER: Empty string means "use relative paths" — Vite's dev server proxies /api to localhost:8000.
const API_BASE_URL = '';

// 🟢 BEGINNER: TypeScript interface describing a finished design document returned by the backend.
export interface DesignDoc {
  title: string;                  // e.g. "AWS Architecture — Design Document"
  content: string;                // Full Markdown text (15 sections)
  cloud: string;                  // "AWS" or "Azure"
  architecture_summary: string;   // First few lines of executive summary
  component_count: number;        // Number of cloud components detected by vision
  connection_count: number;       // Number of connections detected by vision
  terraform_prompts?: { category: string; prompt: string }[];  // 20 LLM-generated prompts
}

// 🟢 BEGINNER: TypeScript interface describing the JSON returned when we poll job status.
// The backend stores jobs in-memory (_jobs dict in jobs.py).
export interface JobResponse {
  job_id: string;
  status: 'running' | 'complete' | 'failed' | 'design_doc_ready' | 'graph_ready';
  pipeline_stage: string;               // human-readable current stage name
  filename?: string;                    // original uploaded filename
  target_clouds?: string[];             // ["aws"] or ["azure"]
  error_message?: string | null;        // populated on failure
  artifacts?: Record<string, { filename: string; size: number }[]>;
  available_clouds?: string[];          // clouds with completed design docs
  design_docs?: Record<string, DesignDoc>; // key = "aws" or "azure"
  terraform_prompts?: { category: string; prompt: string }[];  // generated Terraform prompts
  context_pack?: any;                   // AI vision analysis result (components, provider, confidence)
  user_prompt?: string;                 // user's free-form requirements prompt
  validation_report?: any | null;       // policy validation report
  policy_conflicts?: any[] | null;        // detected policy conflicts
}

// 🟢 BEGINNER: Interface for the design document download endpoint response.
export interface DesignDocResponse {
  job_id: string;
  cloud: string;
  content: string;
}

export interface ArchitectureDiagramResponse {
  job_id: string;
  status: 'running' | 'completed' | 'failed';
  pipeline_stage: string;
  progress: number;
  progress_log?: { stage: string; message: string; progress: number; timestamp: number }[];
  error_message?: string | null;
  graph?: any;
  drawio_xml?: string;
  filename?: string;
}

// RAG retrieval-only response with structured sources
export interface RagSource {
  id: number;
  text: string;
  snippet: string;
  section: string | null;
  score: number;
  score_pct: number;
  chunk_index: number | null;
  matched_terms: string[];
  match_count: number;
}

export interface RagResponse {
  error?: string | null;
  query?: string;
  query_terms?: string[];
  filename?: string;
  total?: number;
  sources?: RagSource[];
  summary?: string;
  haiku_used?: boolean;
}

// 🟢 BEGINNER: Interface for company objects.
export interface Company {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

// 🟢 BEGINNER: Interface for instruction template objects.
export interface InstructionTemplate {
  id: string;
  company_id: string | null;
  name: string;
  description: string;
  content: string;
  created_at: string;
  updated_at: string;
  is_default: boolean;
  is_company_default: boolean;
}

// 🟢 BEGINNER: Simple helper to prefix API log messages with [API] so they're easy to spot in the browser console.
const log = (message: string, data?: any) => {
  console.log(`[API] ${message}`, data || '');
};

// 🟢 BEGINNER: Simple helper for error logs with a red [API ERROR] prefix.
const logError = (message: string, error?: any) => {
  console.error(`[API ERROR] ${message}`, error || '');
};

// 🟢 BEGINNER: The frontend API client. All HTTP calls go through this object.
// Components never call fetch() directly — they call api.startPipeline(), api.getJobStatus(), etc.
export const api = {
  /**
   * Upload a diagram and start the full pipeline.
   * Returns immediately with a job_id to poll.
   */
  async startPipeline(
    file: File,
    targetClouds: string[],
    userPrompt?: string,
    templateId?: string,
    companyId?: string
  ): Promise<JobResponse> {
    log(`Starting pipeline for file: ${file.name}, clouds: ${targetClouds}, template_id: ${templateId}, company_id: ${companyId}`);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_clouds', targetClouds.join(','));
    if (userPrompt) {
      formData.append('user_prompt', userPrompt);
    }
    if (templateId) {
      formData.append('template_id', templateId);
    }
    if (companyId) {
      formData.append('company_id', companyId);
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Upload failed (${response.status})`, err);
      throw new Error(err.detail || `Upload failed (${response.status})`);
    }

    const result = await response.json();
    log(`Pipeline started, job_id: ${result.job_id}`);
    return result;
  },

  /**
   * Poll job status until complete or failed.
   */
  async getJobStatus(jobId: string): Promise<JobResponse> {
    log(`Polling job status: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Status check failed (${response.status})`, err);
      throw new Error(err.detail || `Status check failed (${response.status})`);
    }

    const result = await response.json();
    log(`Job ${jobId} status: ${result.status}, stage: ${result.pipeline_stage}`);
    return result;
  },

  /**
   * Poll until job completes or fails. Returns final job state.
   */
  async waitForCompletion(jobId: string, onProgress?: (stage: string) => void): Promise<JobResponse> {
    log(`Waiting for job completion: ${jobId}`);
    const MAX_POLLS = 600; // 10 minutes max at 1s intervals
    const POLL_INTERVAL = 1000;

    for (let i = 0; i < MAX_POLLS; i++) {
      const job = await this.getJobStatus(jobId);

      if (onProgress) {
        onProgress(job.pipeline_stage);
      }

      if (job.status === 'complete' || job.status === 'design_doc_ready' || job.status === 'graph_ready') {
        log(`Job ${jobId} completed with status: ${job.status}`);
        return job;
      }
      if (job.status === 'failed') {
        logError(`Job ${jobId} failed: ${job.error_message}`);
        throw new Error(job.error_message || 'Pipeline failed');
      }

      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
    }

    logError(`Job ${jobId} timed out after 10 minutes`);
    throw new Error('Pipeline timed out after 10 minutes');
  },

  /**
   * Stream conversational Terraform generation via SSE.
   */
  async *streamTerraformChat(
    messages: { role: string; content: string }[],
    model: string,
    analysisId?: string | null,
    context?: Record<string, any> | null
  ): AsyncGenerator<{ text: string } | { done: true }, void> {
    const body = JSON.stringify({ messages, model, analysis_id: analysisId, context });
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/terraform/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Chat stream failed (${response.status})`);
    }

    if (!response.body) throw new Error('No response body');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            yield { done: true };
            return;
          }
          try {
            const parsed = JSON.parse(data);
            yield { text: parsed.text };
          } catch {
            // ignore malformed lines
          }
        }
      }
    }

    // Flush any remaining buffered data after the stream ends
    if (buffer.trim()) {
      const lines = buffer.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            yield { done: true };
            return;
          }
          try {
            const parsed = JSON.parse(data);
            yield { text: parsed.text };
          } catch {
            // ignore malformed lines
          }
        }
      }
    }
  },

  /**
   * Download design document PDF.
   */
  async downloadDesignDocPdf(jobId: string, cloud: string): Promise<Blob> {
    log(`Downloading design doc PDF for job: ${jobId}, cloud: ${cloud}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/design-doc/${cloud}`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Design doc PDF download failed (${response.status})`, err);
      throw new Error(err.detail || `Design doc PDF download failed (${response.status})`);
    }

    log('Design doc PDF downloaded successfully');
    return await response.blob();
  },

  /**
   * Company management - Create a new company.
   */
  async createCompany(name: string): Promise<Company> {
    log(`Creating company: ${name}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/companies/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Company creation failed (${response.status})`, err);
      throw new Error(err.detail || `Company creation failed (${response.status})`);
    }

    const result = await response.json();
    log(`Company created: ${result.id}`);
    return result;
  },

  /**
   * Company management - Get a company by ID.
   */
  async getCompany(companyId: string): Promise<Company> {
    log(`Getting company: ${companyId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/companies/${companyId}`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Company fetch failed (${response.status})`, err);
      throw new Error(err.detail || `Company fetch failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Company management - List all companies.
   */
  async listCompanies(): Promise<Company[]> {
    log('Listing companies');
    const response = await fetch(`${API_BASE_URL}/api/v1/companies/`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Company list failed (${response.status})`, err);
      throw new Error(err.detail || `Company list failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Template management - List templates for a company.
   * Retries up to 2 times on transient 500 errors (backend may be starting up).
   */
  async listTemplates(companyId: string): Promise<InstructionTemplate[]> {
    log(`Listing templates for company: ${companyId}`);
    const MAX_RETRIES = 2;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/templates/`, {
          headers: { 'X-Company-Id': companyId },
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          // Retry on 500 (transient server error), but not on 4xx (client error)
          if (response.status >= 500 && attempt < MAX_RETRIES) {
            logError(`Template list failed (${response.status}), retrying (${attempt + 1}/${MAX_RETRIES})...`, err);
            await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
            continue;
          }
          logError(`Template list failed (${response.status})`, err);
          throw new Error(err.detail || `Template list failed (${response.status})`);
        }

        return await response.json();
      } catch (e: any) {
        lastError = e;
        if (e.message?.includes('fetch') && attempt < MAX_RETRIES) {
          // Network error — retry
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
          continue;
        }
        throw e;
      }
    }
    throw lastError || new Error('Template list failed after retries');
  },

  /**
   * Template management - Get a template by ID.
   */
  async getTemplate(templateId: string, companyId: string): Promise<InstructionTemplate> {
    log(`Getting template: ${templateId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/templates/${templateId}`, {
      headers: { 'X-Company-Id': companyId },
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Template fetch failed (${response.status})`, err);
      throw new Error(err.detail || `Template fetch failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Template management - Create a new template.
   */
  async createTemplate(companyId: string, template: Omit<InstructionTemplate, 'id' | 'created_at' | 'updated_at'>): Promise<InstructionTemplate> {
    log(`Creating template for company: ${companyId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/templates/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Company-Id': companyId },
      body: JSON.stringify(template),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Template creation failed (${response.status})`, err);
      throw new Error(err.detail || `Template creation failed (${response.status})`);
    }

    const result = await response.json();
    log(`Template created: ${result.id}`);
    return result;
  },

  /**
   * Template management - Update a template.
   */
  async updateTemplate(templateId: string, companyId: string, template: Partial<InstructionTemplate>): Promise<InstructionTemplate> {
    log(`Updating template: ${templateId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/templates/${templateId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Company-Id': companyId },
      body: JSON.stringify(template),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Template update failed (${response.status})`, err);
      throw new Error(err.detail || `Template update failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Template management - Delete a template.
   */
  async deleteTemplate(templateId: string, companyId: string): Promise<void> {
    log(`Deleting template: ${templateId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/templates/${templateId}`, {
      method: 'DELETE',
      headers: { 'X-Company-Id': companyId },
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Template deletion failed (${response.status})`, err);
      throw new Error(err.detail || `Template deletion failed (${response.status})`);
    }

    log('Template deleted successfully');
  },

  /**
   * Generate architecture diagram from uploaded file.
   */
  async generateArchitectureDiagram(
    file: File,
    targetClouds: string,
    onProgress?: (job: ArchitectureDiagramResponse) => void,
    diagramType: string = 'hld',
    customInstruction: string = '',
    toBeCloud: string = '',
  ): Promise<{ job_id: string; graph: any; drawio_xml: string }> {
    const tracePrefix = `[Architecture Pipeline:${file.name}]`;
    console.groupCollapsed(`${tracePrefix} start`);
    console.info(`${tracePrefix} Uploading file`, { file: file.name, size: file.size, targetClouds, diagramType });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_clouds', targetClouds);
    formData.append('diagram_type', diagramType);
    if (customInstruction) formData.append('custom_instruction', customInstruction);
    if (toBeCloud) formData.append('to_be_cloud', toBeCloud);

    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/architecture-diagram`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Architecture diagram generation failed (${response.status})`, err);
      console.error(`${tracePrefix} failed to start`, err);
      console.groupEnd();
      throw new Error(err.detail || `Architecture diagram generation failed (${response.status})`);
    }

    const started: ArchitectureDiagramResponse = await response.json();
    console.info(`${tracePrefix} job accepted`, started);
    log(`Architecture diagram job started, job_id: ${started.job_id}`);

    const completed = await this.waitForArchitectureDiagram(started.job_id, (job) => {
      console.info(`${tracePrefix} ${job.progress}% ${job.pipeline_stage}`, job);
      onProgress?.(job);
    });

    console.info(`${tracePrefix} completed`, {
      jobId: completed.job_id,
      nodes: completed.graph?.nodes?.length || 0,
      edges: completed.graph?.edges?.length || 0,
    });
    console.groupEnd();

    return {
      job_id: completed.job_id,
      graph: completed.graph,
      drawio_xml: completed.drawio_xml || '',
    };
  },

  async getArchitectureDiagramStatus(jobId: string): Promise<ArchitectureDiagramResponse> {
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/architecture-diagram/${jobId}`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Architecture diagram status failed (${response.status})`, err);
      throw new Error(err.detail || `Architecture diagram status failed (${response.status})`);
    }

    return await response.json();
  },

  async waitForArchitectureDiagram(
    jobId: string,
    onProgress?: (job: ArchitectureDiagramResponse) => void
  ): Promise<ArchitectureDiagramResponse> {
    // 20-minute polling budget. Most jobs finish in 60-180s, but very large
    // documents with LLD or migration_wave can take 5-10 minutes. The backend
    // has a 600s pipeline timeout that will fail the job with a clear error
    // before this client-side timeout fires.
    const MAX_POLLS = 600;
    const POLL_INTERVAL = 2000; // 2s — keeps server load low during long generations
    let lastStage = '';

    for (let i = 0; i < MAX_POLLS; i++) {
      const job = await this.getArchitectureDiagramStatus(jobId);

      if (job.pipeline_stage !== lastStage) {
        lastStage = job.pipeline_stage;
        log(`Architecture diagram ${jobId}: ${job.pipeline_stage} (${job.progress}%)`);
      }

      onProgress?.(job);

      if (job.status === 'completed') {
        if (!job.graph || !job.drawio_xml) {
          throw new Error('Architecture diagram completed without graph or draw.io XML');
        }
        return job;
      }

      if (job.status === 'failed') {
        throw new Error(job.error_message || 'Architecture diagram generation failed');
      }

      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
    }

    throw new Error('Architecture diagram generation timed out after 20 minutes. Try a simpler diagram type or smaller document.');
  },

  /**
   * Get architecture graph for a job.
   */
  async getArchitectureGraph(jobId: string): Promise<{ graph: any; drawio_xml: string }> {
    log(`Getting architecture graph: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/graph`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Get architecture graph failed (${response.status})`, err);
      throw new Error(err.detail || `Get architecture graph failed (${response.status})`);
    }

    const data = await response.json();
    log('Architecture graph retrieved successfully');
    return data;
  },

  /**
   * Save updated architecture graph.
   */
  async saveArchitectureGraph(jobId: string, xml: string): Promise<{ graph: any }> {
    log(`Saving architecture graph: ${jobId}`);
    const formData = new FormData();
    formData.append('xml', xml);

    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/graph`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Save architecture graph failed (${response.status})`, err);
      throw new Error(err.detail || `Save architecture graph failed (${response.status})`);
    }

    const data = await response.json();
    log('Architecture graph saved successfully');
    return data;
  },

  /**
   * Initialize RAG indexing for a document.
   */
  async initializeRAG(file: File): Promise<{ job_id: string; status: string }> {
    log(`Initializing RAG for file: ${file.name}`);
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/v1/rag/index`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`RAG initialization failed (${response.status})`, err);
      throw new Error(err.detail || `RAG initialization failed (${response.status})`);
    }

    const data = await response.json();
    log(`RAG indexing job started: ${data.job_id}`);
    return data;
  },

  /**
   * Get RAG indexing status.
   */
  async getRAGStatus(jobId: string): Promise<{ job_id: string; status: string; stage: string; progress: number; error?: string; filename?: string; chunks_count?: number; collection_name?: string }> {
    const response = await fetch(`${API_BASE_URL}/api/v1/rag/index/${jobId}`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Get RAG status failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Query RAG (returns structured JSON with sources, no streaming).
   */
  async ragQuery(query: string): Promise<RagResponse> {
    const response = await fetch(`${API_BASE_URL}/api/v1/rag/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `RAG query failed (${response.status})`);
    }

    return await response.json();
  },

  /**
   * Chat with RAG (legacy SSE-style wrapper kept for compatibility).
   */
  async ragChat(query: string, onChunk: (chunk: string) => void): Promise<void> {
    const result = await this.ragQuery(query);
    if (result.error) {
      onChunk(result.error);
      return;
    }
    onChunk(JSON.stringify(result));
  },

  /**
   * Suggest refined Terraform prompts using Haiku.
   */
  async suggestTerraformPrompt(roughPrompt: string, cloudProvider: string, detectedResources: string[]): Promise<string[]> {
    log(`Suggesting Terraform prompts for: ${roughPrompt}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/suggest-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rough_prompt: roughPrompt,
        cloud_provider: cloudProvider,
        detected_resources: detectedResources,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      logError(`Suggest prompt failed (${response.status})`, err);
      throw new Error(err.detail || `Suggest prompt failed (${response.status})`);
    }

    const data = await response.json();
    log(`Generated ${data.suggestions.length} prompt suggestions`);
    return data.suggestions;
  },
};
