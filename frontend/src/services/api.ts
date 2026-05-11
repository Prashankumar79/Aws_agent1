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

const API_BASE_URL = ''; // Empty = use relative paths (proxied by Vite dev server)

/** Shape of a completed design document returned from the backend. */
export interface DesignDoc {
  title: string;                  // e.g. "AWS Architecture — Design Document"
  content: string;                // Full Markdown text (15 sections)
  cloud: string;                  // "AWS" or "Azure"
  architecture_summary: string;   // First few lines of executive summary
  component_count: number;        // Number of cloud components detected by vision
  connection_count: number;       // Number of connections detected by vision
  terraform_prompts?: { category: string; prompt: string }[];  // 20 LLM-generated prompts
}

/**
 * Shape of the job status object returned by GET /api/v1/jobs/:id.
 * Jobs are stored in-memory on the backend (_jobs dict in jobs.py).
 *
 * Status progression:
 *   running → graph_ready → design_doc_ready → complete
 *                                               → failed (at any stage)
 */
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
}

/** Shape returned by the design-doc download endpoint (used for PDF/MD export). */
export interface DesignDocResponse {
  job_id: string;
  cloud: string;
  content: string;
}

const log = (message: string, data?: any) => {
  console.log(`[API] ${message}`, data || '');
};

const logError = (message: string, error?: any) => {
  console.error(`[API ERROR] ${message}`, error || '');
};

export const api = {
  /**
   * Upload a diagram and start the full pipeline.
   * Returns immediately with a job_id to poll.
   */
  async startPipeline(file: File, targetClouds: string[]): Promise<JobResponse> {
    log(`Starting pipeline for file: ${file.name}, clouds: ${targetClouds}`);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_clouds', targetClouds.join(','));

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
    const MAX_POLLS = 120; // 10 minutes max at 5s intervals
    const POLL_INTERVAL = 5000;

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
};
