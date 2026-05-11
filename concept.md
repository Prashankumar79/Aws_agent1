# InfraSketch — Development Log, Bugs & Fixes

> A running journal of real-world issues encountered while building a production-grade AI architecture generator (React + FastAPI + AWS Bedrock), and the patterns used to fix them.

---

## 1. Terraform Page: Static & Hardcoded

### Problem
`TerraformPage.tsx` shipped with a hardcoded `files` array and displayed a single `terraformCode` blob from the Zustand store. Users could not see the actual generated files — the UI was fake.

### Root Cause
The page was built as a placeholder. No API integration existed for fetching artifacts.

### Fix
- Fetched artifacts dynamically from `/api/v1/jobs/{jobId}/artifacts`
- Built the file list from the response
- Rendered each file with `react-syntax-highlighter` + line numbers
- Made buttons functional: copy file, copy all, download file, download zip
- Computed real validation stats (brace balance, encryption, versioning, flow logs) from actual code

### Best Practice
> **Never ship placeholder data in production UI.** If a feature isn't wired to the backend, either hide it or build the integration. Fake data creates false confidence and breaks when real data arrives.

---

## 2. Footer Invisible / Header Static

### Problem
- Footer had `backgroundColor: 'white'` on a `#F5F3EE` page background — completely invisible
- Header nav links were static `<a href="#">` tags with hardcoded active state on "Design document"

### Fix
- Footer: changed to `#EEEDFE` (light purple tint matching brand) + `2px solid #5B4EE8` top border
- Header: connected tabs to `useWorkflowStore` (`currentStep`, `setCurrentStep`), used Tabler icon classes

### Best Practice
> **UI components must respond to application state.** Hardcoded active states and invisible borders are paper cuts that erode user trust. Use your state store as the single source of truth for navigation.

---

## 3. ChatGPT/Claude-like Streaming Design Document

This was the largest feature request — real-time token-by-token streaming from AWS Bedrock. It exposed a chain of issues across the entire stack.

---

### 3.1 Backend: No Token-Level Streaming Method

### Problem
`DesignDocGenerator` only had `_call()` which used `invoke_model()` — a blocking call that returned the full response after ~10-30s. No way to stream tokens.

### Fix
Added `_call_streaming()` using Bedrock's `invoke_model_with_response_stream()`:

```python
def _call_streaming(self, prompt: str, max_tokens: int = 2048):
    resp = self.bedrock_client.invoke_model_with_response_stream(
        modelId=self.bedrock_model, ...
    )
    for event in resp.get("body", []):
        chunk = json.loads(event.get("chunk", {}).get("bytes", b""))
        if chunk.get("type") == "content_block_delta":
            text = chunk.get("delta", {}).get("text", "")
            if text:
                yield text
```

### Best Practice
> **Use native streaming APIs when available.** Bedrock's `invoke_model_with_response_stream` returns chunks via `content_block_delta` events. Do not parse the full response and then split it — that's not real streaming.

---

### 3.2 Backend: Section-Based Events Instead of Token Deltas

### Problem
`generate_design_document_streamed()` yielded one event per section after `_call()` completed. Each event contained the full section text. The frontend had to wait ~30s per section.

### Fix
Rewrote to use `_call_streaming()` and emit fine-grained events:
- `section_start` — sidebar knows which section is active
- `delta` — individual text chunks as Bedrock produces them
- `section_end` — section complete, sidebar shows checkmark

```python
for section_name, prompt, max_tokens in calls:
    yield f"data: {{'type':'section_start','section':...}}"
    for text_chunk in self._call_streaming(prompt, max_tokens=max_tokens):
        yield f"data: {{'type':'delta','text':...}}"
    yield f"data: {{'type':'section_end','section':...}}"
```

### Best Practice
> **Decouple your event schema from your data model.** The SSE protocol should carry small, typed events. The frontend assembles them. Don't ship JSON blobs that mirror your database schema over the wire.

---

### 3.3 Backend: SSE Route Expected Old Format

### Problem
The `/stream-design-doc-sections` route parsed `{"section":"snapshot","data":{...}}` and accumulated `section_data`. It didn't know about `delta` events.

### Fix
Updated the route to:
- Track `current_section` from `section_start` events
- Accumulate `delta.text` into `section_texts[section]`
- Forward **every** chunk to the client immediately (don't buffer)

### Best Practice
> **The server is a pipe, not a gatekeeper.** For streaming endpoints, parse what you need for storage, then yield the raw chunk. Don't hold chunks in memory waiting for "complete" events.

---

### 3.4 Backend: Pipeline Auto-Generated Design Doc Before Streaming

### Problem
`_run_pipeline()` always ran Stage 2 (design doc generation) synchronously. The streaming endpoint had nothing to do — the doc was already generated and stored.

### Fix
Modified pipeline to stop at `GRAPH_BUILT` when `run_terraform=False`:

```python
if run_terraform:
    # generate design doc + terraform
else:
    job["status"] = "graph_ready"
    job["pipeline_stage"] = "GRAPH_BUILT"
    return  # streaming will generate on-demand
```

### Best Practice
> **Separate pipeline stages with clear exit points.** Don't generate data that will be generated again by a different mechanism. Each stage should be idempotent and skippable.

---

### 3.5 Frontend: API Type Didn't Include `graph_ready`

### Problem
`JobResponse.status` was typed as `'running' | 'complete' | 'failed' | 'design_doc_ready'`. When the backend returned `graph_ready`, TypeScript flagged it as an error.

### Fix
```typescript
status: 'running' | 'complete' | 'failed' | 'design_doc_ready' | 'graph_ready';
```

### Best Practice
> **Keep frontend types in sync with backend states.** If you add a new status on the server, add it to the client type immediately. A single missing union member can break polling logic.

---

### 3.6 Frontend: `EventSource` Blocked by Proxy

### Problem
The browser preview proxy (used by the IDE) buffers SSE connections. `EventSource.onmessage` never fired — no events reached the frontend. Console showed the stream opening but no data.

### Fix
Switched to `fetch()` + `ReadableStream` + manual SSE parsing:

```typescript
const response = await fetch(url, { headers: { Accept: 'text/event-stream' }});
const reader = response.body!.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  buffer = processSSEBuffer(buffer, handleEvent);
}
```

### Best Practice
> **Avoid `EventSource` in proxy environments.** `fetch` + `ReadableStream` gives you full control over buffering, cancellation (via `AbortController`), and error handling. It's the industry standard for AI chat apps (OpenAI, Anthropic SDKs all use this).

---

### 3.7 Frontend: `hasMountedRef` Broke React Strict Mode

### Problem
Used a `hasMountedRef` guard to prevent double `useEffect` runs:

```typescript
if (hasMountedRef.current) return;
hasMountedRef.current = true;
startStreaming();
```

In React Strict Mode:
1. Mount → starts stream
2. Unmount → cleanup aborts stream ("Stream cancelled")
3. Remount → `hasMountedRef` is `true` → **never restarts**

### Fix
Removed `hasMountedRef`. Used `jobId` as the effect dependency:

```typescript
useEffect(() => {
  if (jobId && !designDoc?.content) {
    startStreaming();
  }
  return () => { abortRef.current?.abort(); };
}, [jobId]);
```

### Best Practice
> **Never use `hasMountedRef` in React.** It breaks Strict Mode, breaks concurrent features, and hides real bugs. If you need to prevent duplicate work, make your operations idempotent or use proper cancellation via `AbortController`.

---

### 3.8 Frontend: Render Performance During Streaming

### Problem
Appending a text chunk and calling `setState` on every delta caused React to re-render 50+ times per second. The UI stuttered.

### Fix (Initial)
Accumulated markdown in a `useRef`, batched HTML rendering via `requestAnimationFrame`:

```typescript
const scheduleRender = useCallback(() => {
  if (rafRef.current) return;
  rafRef.current = requestAnimationFrame(() => {
    rafRef.current = null;
    setRenderedHTML(markdownToHTML(markdownRef.current));
  });
}, []);
```

### Fix (Refined — see 3.10)
`requestAnimationFrame` still fired at 60fps, re-processing the entire markdown on every frame. Switched to a 100ms `setTimeout` throttle + length check:

```typescript
const scheduleRender = useCallback(() => {
  if (timerRef.current) return;
  timerRef.current = setTimeout(() => {
    timerRef.current = null;
    if (markdownRef.current.length <= lastRenderLenRef.current) return;
    lastRenderLenRef.current = markdownRef.current.length;
    setRenderedHTML(markdownToHTML(markdownRef.current));
  }, 100); // ~10fps — smooth like ChatGPT
}, []);
```

### Best Practice
> **Batch high-frequency updates, but don't over-render.** `requestAnimationFrame` is 60fps — too fast for markdown parsing. Use a 80-120ms timer for streaming text to avoid visual jitter.

---

### 3.9 Frontend: Auto-Scroll Annoyance

### Problem
Auto-scrolling to bottom on every update made it impossible to read earlier sections while new text arrived.

### Fix
Only auto-scroll if the user is already near the bottom:

```typescript
const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
if (nearBottom) el.scrollTop = el.scrollHeight;
```

### Best Practice
> **Respect the user's scroll position.** In streaming UIs, auto-scroll is helpful only when the user is already following the bottom. If they've scrolled up to read, leave them there.

---

### 3.10 Frontend: Streaming Text Vibrates / Cursor Jitters

### Problem
Even with `requestAnimationFrame` batching, the text felt like it was "vibrating" or "freezing" during streaming. Not smooth like ChatGPT.

### Root Cause — Two Issues

1. **60fps is too fast for markdown parsing.** `requestAnimationFrame` fires every ~16ms. On each frame, `markdownToHTML()` splits the entire accumulated text, runs regex on every line, and rebuilds the HTML. As the text grows, this gets slower. The DOM is completely replaced 60 times per second.

2. **Cursor resets CSS animation.** The blinking cursor was concatenated into the `dangerouslySetInnerHTML` string:
   ```tsx
   __html: renderedHTML + '<span class="stream-cursor"></span>'
   ```
   Every time `renderedHTML` changed, the `<span>` was destroyed and recreated. The CSS `animation: blink` restarted from 0%, causing visible stutter and layout recalculation.

### Fix

1. **Throttle to 100ms** instead of rAF:
   ```typescript
   timerRef.current = setTimeout(() => {
     // ...render
   }, 100); // ~10fps
   ```

2. **Skip redundant renders** — track last rendered length:
   ```typescript
   if (markdownRef.current.length <= lastRenderLenRef.current) return;
   lastRenderLenRef.current = markdownRef.current.length;
   ```

3. **Move cursor outside `dangerouslySetInnerHTML`** — render as a persistent React element:
   ```tsx
   <div className="md-body">
     <div dangerouslySetInnerHTML={{ __html: renderedHTML }} />
     {isStreaming && <span className="stream-cursor" />}
   </div>
   ```
   The cursor is now a stable DOM node. Its CSS animation runs independently and never resets.

### Best Practice
> **Never put animated elements inside `dangerouslySetInnerHTML`.** Any element that needs CSS animation (cursor, spinners, progress bars) must be a separate React component outside the innerHTML. InnerHTML complete replacement destroys and recreates DOM nodes, which restarts animations and causes layout thrashing.

---

## 4. General Best Practices Applied

| Practice | Where Applied |
|----------|--------------|
| **Use `AbortController` for all async work** | Stream cancellation, fetch cleanup, polling teardown |
| **Type safety across API boundaries** | `JobResponse.status` union matches all backend states |
| **Proxy-safe SSE** | `fetch` + `ReadableStream` instead of `EventSource` |
| **Batched DOM updates** | `requestAnimationFrame` coalescing during streaming |
| **Smart auto-scroll** | Only scroll when user is near bottom |
| **Section progress UI** | Sidebar shows real-time status per section |
| **Fallback paths** | If SSE fails, load pre-generated doc from `/jobs/{id}` |
| **Idempotent pipeline stages** | Each stage can be skipped or retried independently |

---

## 5. Architecture Decisions

### Why `fetch` over `EventSource`?
- `EventSource` doesn't support custom headers, POST bodies, or `AbortController`
- Proxy buffering breaks SSE event delivery in preview environments
- `fetch` + `ReadableStream` is what OpenAI, Anthropic, and every major AI SDK uses

### Why stop the pipeline at `GRAPH_BUILT`?
- Design doc generation is the longest stage (~2-4 minutes for 4 Bedrock calls)
- Streaming keeps the user engaged while work happens
- If the user leaves and returns, the streaming endpoint is idempotent

### Why accumulate markdown in a ref?
- React state is for UI that needs to trigger re-renders
- Markdown text is "render data" — it only needs to exist when we call `markdownToHTML()`
- `useRef` avoids 50+ re-renders per second

---

---

## 6. Terraform Generation: Basic / Static / Repetitive

### Problem
When ChromaDB was empty (common in dev/local), `IaCAgent` fell back to Jinja2 templates that produced the same 3 files every time: `versions.tf`, `variables.tf`, and a nearly-empty `main.tf`. The output was completely static — no actual resources, no node-specific configuration, no design document context. Every diagram produced identical Terraform.

### Root Cause
The Jinja fallback was a placeholder. It didn't use:
- The architecture graph nodes (types, labels, connections)
- The design document content (security guidance, data flows)
- Any Terraform best-practice patterns per service type

### Fix: SmartTerraformService + In-Memory Pattern Registry

**Created two new backend services:**

1. **`terraform_pattern_registry.py`** — In-memory RAG knowledge base
   - Maps 15+ AWS service types (EC2, Lambda, S3, RDS, DynamoDB, VPC, ALB, API Gateway, SQS, SNS, IAM, Secrets Manager, CloudWatch, ElastiCache, CloudFront) to production-ready Terraform patterns
   - Each pattern includes: required config blocks, security rules, related resources
   - Canonical name mapping so vision-extracted labels like "bucket", "db", "queue" resolve to the right pattern

2. **`smart_terraform_service.py`** — Rich prompt builder + LLM caller
   - Builds a prompt with 4 sections:
     - **Graph topology**: every node + edge listed
     - **Design document summary**: up to 4000 chars of the design doc
     - **Retrieved patterns**: security rules + required config for each detected service
     - **Instructions**: output format (JSON with `files` array), HCL rules
   - Calls Bedrock with `temperature=0.1` for deterministic output
   - Parses JSON response into structured `[{filename, content}]` list
   - Falls back to minimal files only if LLM response is unparseable

3. **Updated `iac_agent.py`**
   - Replaced `_jinja_fallback()` with `_smart_generation()`
   - Now uses `SmartTerraformService` whenever ChromaDB is empty
   - Still falls back to `TerraformGeneratorService` (4-call chained pipeline) when ChromaDB is populated
   - Extracts design doc content from the `summary` dict properly

### Best Practice
> **Never use Jinja templates for infrastructure generation.** A Jinja template has zero understanding of architecture context. If you can't query a vector DB, build an in-memory pattern registry and inject it into the LLM prompt. The LLM will generate context-aware code that respects the actual nodes, edges, and security guidance from the design document.

### Files Changed
- `backend/app/services/terraform_pattern_registry.py` *(new)*
- `backend/app/services/smart_terraform_service.py` *(new)*
- `backend/app/agents/iac_agent.py`

---

## 7. Current Status

- ✅ Header is dynamic with Tabler icons
- ✅ Footer has visible brand color
- ✅ Terraform page fetches and displays real files dynamically
- ✅ Design doc streams token-by-token from Bedrock
- ✅ Section progress sidebar updates in real time
- ✅ Blinking cursor during streaming
- ✅ Smart auto-scroll
- ✅ Fallback to pre-generated doc if streaming fails
- ✅ Terraform generation uses architecture graph nodes + design doc + retrieved patterns
- ✅ No more static Jinja fallback — every diagram gets unique Terraform

---

*Last updated: May 10, 2026*
