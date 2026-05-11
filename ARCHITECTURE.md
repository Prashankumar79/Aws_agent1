# InfraSketch Architecture Documentation

## Overview

InfraSketch is a production-grade AI-powered infrastructure-as-code (IaC) generation platform that converts architecture diagrams into production-ready Terraform code. The system uses a multi-agent AI pipeline with vision analysis, design document generation, and RAG-powered code generation.

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI (Python) | REST API, async job processing |
| **Vision** | Google Gemini 2.5 Pro | Image scanning and component extraction |
| **Design Doc** | AWS Bedrock (Claude Sonnet) | Architecture design documentation |
| **Code Gen** | AWS Bedrock (Claude Sonnet) | Terraform code generation |
| **RAG** | ChromaDB + Sentence Transformers | Knowledge base for Terraform docs |
| **Frontend** | React + TypeScript + Vite | UI, workflow management |
| **State** | Zustand | Client-side state management |

---

## Project Structure

```
Terraform_generator/
├── backend/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py                  # FastAPI app entry point
│   │   ├── agents/                  # AI Agent orchestrators
│   │   │   └── iac_agent.py        # Main IaC generation agent
│   │   ├── api/                     # API routes
│   │   │   ├── upload.py            # File upload endpoint (legacy)
│   │   │   ├── analyse.py           # Analysis endpoint (legacy)
│   │   │   ├── design.py            # Design doc endpoint (legacy)
│   │   │   ├── terraform.py         # Terraform endpoint (legacy)
│   │   │   └── v1/
│   │   │       └── jobs.py         # Job-based pipeline API (current)
│   │   ├── core/                    # Core utilities
│   │   │   ├── config.py            # Settings from .env
│   │   │   ├── constants.py         # Static constants
│   │   │   └── logging.py           # Logging configuration
│   │   ├── db/                      # Database (future use)
│   │   │   ├── models.py            # SQLAlchemy models
│   │   │   └── session.py           # DB session management
│   │   ├── rag/                     # RAG pipeline
│   │   │   ├── knowledge_base.py    # ChromaDB singleton client
│   │   │   ├── ingestion/           # Knowledge base ingestion
│   │   │   │   ├── registry_scraper.py  # Terraform Registry scraper
│   │   │   │   ├── chunker.py       # Markdown chunking by sections
│   │   │   │   └── embedder.py      # Chunk embedding into ChromaDB
│   │   │   ├── retrieval/           # RAG retrieval
│   │   │   │   └── retriever.py     # Semantic + metadata search
│   │   │   └── generation/          # Terraform code generation
│   │   │       ├── code_generator.py    # Bedrock LLM wrapper
│   │   │       ├── context_builder.py    # RAG context assembly
│   │   │       └── validator.py          # HCL validation
│   │   ├── schemas/                 # Pydantic models
│   │   │   ├── api_models.py        # API request/response models
│   │   │   ├── architecture_context.py  # Vision analysis output
│   │   │   ├── cloud_schema.py      # Cloud provider schemas
│   │   │   ├── design_doc.py        # Design document schema
│   │   │   └── terraform_spec.py    # Terraform spec schemas
│   │   └── services/                # Business logic services
│   │       ├── vision_service.py    # Gemini Vision integration
│   │       ├── design_doc_service.py # Bedrock design doc generator
│   │       ├── analysis_service.py  # Analysis orchestration
│   │       ├── bedrock_service.py   # Bedrock client wrapper
│   │       ├── cloud_detector.py    # Cloud detection from image
│   │       └── context_builder.py   # Context assembly
│   ├── scripts/                     # Utility scripts
│   │   ├── ingest_aws.py            # Ingest AWS Terraform docs
│   │   ├── ingest_azure.py          # Ingest Azure Terraform docs
│   │   └── test_pipeline.py         # End-to-end pipeline test
│   ├── requirements.txt             # Python dependencies
│   ├── run.py                       # Uvicorn entry point
│   └── .env                         # Environment variables
└── frontend/                        # React frontend
    ├── src/
    │   ├── App.tsx                  # Main app with workflow stepper
    │   ├── main.jsx                 # React entry point
    │   ├── index.css                # Global styles
    │   ├── components/              # React components
    │   │   ├── DesignDocView.tsx    # Display design document
    │   │   ├── TerraformCodeView.tsx # Display Terraform code
    │   │   ├── actions/             # Action buttons
    │   │   │   └── AnalyseButton.tsx # Start pipeline
    │   │   ├── cloud-selector/      # Cloud provider selection
    │   │   │   ├── CloudSelector.tsx # AWS/Azure selector (GCP removed)
    │   │   │   └── CloudCard.tsx    # Individual cloud card
    │   │   ├── common/              # Common UI components
    │   │   │   ├── LoadingOverlay.tsx # Loading overlay
    │   │   │   └── Notification.tsx # Toast notifications
    │   │   ├── editor/              # Code editor
    │   │   │   └── TerraformViewer.tsx # Terraform code viewer
    │   │   ├── upload/              # File upload
    │   │   │   ├── UploadDropzone.tsx # Drag & drop upload
    │   │   │   ├── FilePreview.tsx   # File preview
    │   │   │   └── FileStatus.tsx   # Upload status
    │   │   └── workflow/            # Workflow components
    │   │       ├── WorkflowStepper.tsx # Step indicator
    │   │       └── ExtractedServices.tsx # Display extracted services
    │   ├── pages/                   # Page components
    │   │   ├── UploadPage.tsx       # Upload + cloud selection
    │   │   ├── AnalysePage.tsx      # Analysis page (legacy)
    │   │   ├── DesignDocPage.tsx    # Design doc page (legacy)
    │   │   ├── TerraformPage.tsx    # Terraform page (legacy)
    │   │   └── ResultsPage.tsx      # Results: design doc + terraform
    │   ├── services/                # API client
    │   │   └── api.ts               # FastAPI client with polling
    │   ├── store/                   # State management
    │   │   └── workflowStore.ts      # Zustand workflow state
    │   └── types/                   # TypeScript types
    │       └── schema.ts            # Shared type definitions
    ├── package.json                 # NPM dependencies
    ├── vite.config.js               # Vite configuration
    └── index.html                   # HTML entry point
```

---

## Data Flow

### End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1. Upload image + select cloud
                                    │    (AWS or Azure only)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Client (api.ts)                           │
│  • POST /api/v1/jobs/ (FormData: file + target_clouds)          │
│  • Returns: job_id, status='running'                             │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                             │
│  • jobs.py: create_job()                                         │
│  • Saves file to storage/uploads/{job_id}.{ext}                  │
│  • Creates job record in _jobs dict                              │
│  • Launches background task: _run_pipeline(job_id)              │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│              BACKGROUND PIPELINE (_run_pipeline)                │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Stage 1: Vision Analysis
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                VisionService (vision_service.py)                  │
│  • Uses Google Gemini 2.5 Pro (gemini-2.5-pro)                  │
│  • Analyzes uploaded image                                       │
│  • Extracts: components, connections, cloud provider              │
│  • Returns: {success, analysis: {components, connections}}       │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Convert to graph format
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Graph Builder                                 │
│  • Transforms vision output to standardized graph               │
│  • Format: {nodes: [{id, label, service_type, cloud_provider}], │
│  │          edges: [{source, target, connection_type}]}          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Stage 2: Design Document Generation
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│           DesignDocGenerator (design_doc_service.py)             │
│  • Uses AWS Bedrock (Claude Sonnet)                              │
│  • Input: vision analysis + graph                               │
│  • Generates comprehensive design document (Markdown)             │
│  • Sections: Overview, Components, Network, Security, etc.       │
│  • Returns: {title, content, cloud, architecture_summary}        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Stage 3: Terraform Generation
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   IaCAgent (iac_agent.py)                        │
│  • Checks ChromaDB availability                                  │
│  • If RAG available: use TerraformCodeGenerator                  │
│  • If RAG unavailable: use Jinja2 fallback templates              │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ RAG Path (if ChromaDB populated)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│            TerraformCodeGenerator (code_generator.py)            │
│  • Uses AWS Bedrock (Claude Sonnet)                              │
│  • Input: graph, design_doc, cloud                               │
│  • RAG Retrieval:                                               │
│    ├─ TerraformRetriever retrieves relevant docs                  │
│    ├─ context_builder assembles context                          │
│    └─ Design document appended as authoritative context          │
│  • Generates Terraform files per group (main.tf, vpc.tf, etc.)   │
│  • Returns: [{filename, content}, ...]                           │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Fallback Path (if ChromaDB empty)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Jinja2 Fallback                                │
│  • Generates minimal Terraform: versions.tf, variables.tf, main.tf│
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Stage 4: Validation
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   HCLValidator (validator.py)                     │
│  • Validates generated HCL syntax                                │
│  • Checks for bad patterns                                       │
│  • Adds warning comments to invalid files                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Stage 5: Storage
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   File Storage                                   │
│  • Writes files to storage/outputs/{job_id}/{cloud}/             │
│  • Stores in job record: artifacts_json                           │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Job complete
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Job Status Update                             │
│  • job["status"] = "complete"                                     │
│  • job["pipeline_stage"] = "GENERATED"                           │
│  • job["artifacts_json"] = JSON of generated files               │
│  • job["design_docs_json"] = JSON of design docs                  │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FRONTEND POLLING (api.ts)                        │
│  • Polls GET /api/v1/jobs/{job_id} every 5s                     │
│  • Shows pipeline stage: Vision → Design Doc → Generating       │
│  • When status="complete": fetch results                         │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Fetch Results                                   │
│  • GET /api/v1/jobs/{job_id}/artifacts?cloud={cloud}            │
│  • Returns: {files: [{filename, content}, ...]}                  │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTS PAGE (ResultsPage.tsx)                 │
│  • Left panel: DesignDocView (markdown display)                   │
│  • Right panel: TerraformCodeView (code + download)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Components Explained

### Backend

#### `app/main.py`
- **Purpose**: FastAPI application entry point
- **Responsibilities**:
  - Initialize FastAPI app with CORS middleware
  - Include API routers (`/api/upload`, `/api/v1/jobs`)
  - Startup event: Check ChromaDB knowledge base availability
  - Health check endpoint (`/health`)
- **Dependencies**: `app.api.upload`, `app.api.v1.jobs`, `app.core.config`

#### `app/api/v1/jobs.py`
- **Purpose**: Job-based pipeline API (current primary API)
- **Endpoints**:
  - `POST /api/v1/jobs/` - Upload file + start pipeline
  - `GET /api/v1/jobs/{job_id}` - Poll job status
  - `GET /api/v1/jobs/{job_id}/artifacts` - Fetch generated files
  - `GET /api/v1/jobs/{job_id}/artifacts/download` - Download ZIP
- **Data Flow**:
  1. Uploads file to `storage/uploads/`
  2. Creates job record in `_jobs` dict (in-memory, production would use DB)
  3. Launches background task `_run_pipeline()`
  4. Returns job_id immediately
- **Pipeline Stages**:
  - `UPLOADED` → `VISION_RUNNING` → `GRAPH_BUILT` → `DESIGN_DOC_GENERATING` → `DESIGN_DOC_GENERATED` → `GENERATING` → `GENERATED` / `FAILED`

#### `app/agents/iac_agent.py`
- **Purpose**: Main orchestrator for Terraform code generation
- **Responsibilities**:
  - Check ChromaDB availability
  - Route to RAG generation or Jinja2 fallback
  - Validate generated HCL
  - Write files to storage
- **Fallback Strategy**: If ChromaDB is empty or RAG fails, generates minimal Terraform templates

#### `app/services/vision_service.py`
- **Purpose**: Google Gemini Vision integration for image scanning
- **Technology**: `google.genai` SDK (not deprecated `google.generativeai`)
- **Model**: `gemini-2.5-pro` (configurable via `GEMINI_VISION_MODEL`)
- **Output**: Components, connections, cloud provider detection
- **Key Methods**:
  - `analyze_diagram(image_path)` - Main analysis method
  - `_build_analysis_prompt()` - Constructs vision prompt
  - `_parse_vision_response()` - Parses JSON response from Gemini

#### `app/services/design_doc_service.py`
- **Purpose**: AWS Bedrock integration for design document generation
- **Technology**: AWS Bedrock (Claude Sonnet)
- **Model**: Configurable via `AWS_BEDROCK_MODEL` (default: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`)
- **Input**: Vision analysis result + target cloud
- **Output**: Markdown design document with sections:
  - Architecture Overview
  - Component Details
  - Network Architecture
  - Data Flow
  - Security & Compliance
  - Cost Optimization
  - Operational Excellence
  - Migration/Deployment Strategy

#### `app/rag/knowledge_base.py`
- **Purpose**: ChromaDB singleton client and collection management
- **Collections**:
  - `aws_resources` - AWS Terraform provider docs
  - `azure_resources` - Azure Terraform provider docs
  - `aws_modules` - AWS modules
  - `azure_modules` - Azure modules
  - `security_rules` - CIS benchmark rules
- **Functions**:
  - `get_collection(name)` - Get or create collection
  - `list_collection_stats()` - Return document counts

#### `app/rag/ingestion/registry_scraper.py`
- **Purpose**: Scrape Terraform Registry for provider documentation
- **Target Resources**: Pre-defined lists for AWS and Azure (VPC, EC2, S3, RDS, etc.)
- **Rate Limiting**: 0.5s between index requests, 1.0s per doc
- **Retry**: 3 attempts with exponential backoff

#### `app/rag/ingestion/chunker.py`
- **Purpose**: Split documentation into chunks for embedding
- **Strategy**:
  - Split by `##` (level-2 headings)
  - If section > 1500 chars, split by `###` (level-3)
  - Prepend metadata to each chunk (resource type, cloud, section)
  - Skip sections < 50 chars
- **Output**: List of chunk dicts with chunk_id, resource_type, cloud, section, content

#### `app/rag/ingestion/embedder.py`
- **Purpose**: Embed chunks into ChromaDB
- **Embedding Model**: `all-mpnet-base-v2` (Sentence Transformers)
- **Batching**: 50 chunks per upsert
- **Security Rules**: Hardcoded CIS benchmark rules for AWS/Azure

#### `app/rag/retrieval/retriever.py`
- **Purpose**: Retrieve relevant documentation for resources
- **Search Strategy**:
  1. **Semantic Search**: Query by resource + description
  2. **Keyword Filter**: Filter by exact resource_type + cloud (uses `$and` operator)
  3. **Security Rules**: Retrieve CIS rules for resource
- **Prioritization**: `example_usage` > `argument_reference` > `overview`
- **Error Handling**: Falls back to empty results on query failure

#### `app/rag/generation/code_generator.py`
- **Purpose**: Generate Terraform code using LLM + RAG
- **Technology**: AWS Bedrock (Claude Sonnet)
- **Input**: Graph, RAG context, design document (as context)
- **File Groups**: Organizes resources into files:
  - AWS: `main.tf`, `networking.tf`, `compute.tf`, `storage.tf`, `security.tf`, `monitoring.tf`, `versions.tf`, `variables.tf`, `locals.tf`
  - Azure: Similar structure with Azure-specific resources
- **Design Document Integration**: Appends full design doc as authoritative context before RAG context
- **Rate Limiting**: ~4s between Bedrock calls

#### `app/rag/generation/context_builder.py`
- **Purpose**: Assemble RAG context string for LLM prompt
- **Components**:
  - Architecture summary
  - Human-confirmed answers (if any)
  - Retrieved documentation chunks
  - Security rules
- **Output**: Formatted context string

#### `app/rag/generation/validator.py`
- **Purpose**: Validate generated HCL code
- **Checks**:
  - Syntax validity using `python-hcl2`
  - Bad patterns (e.g., hardcoded secrets, missing tags)
  - Resource count warnings
- **Output**: Validation result with warnings

### Frontend

#### `App.tsx`
- **Purpose**: Main application component
- **Workflow Steps**:
  1. Upload (UploadPage)
  2. Analyse (UploadPage with processing overlay)
  3. Results (ResultsPage)
- **Components**: WorkflowStepper (sidebar), dynamic page rendering

#### `services/api.ts`
- **Purpose**: API client for backend communication
- **Methods**:
  - `startPipeline(file, targetClouds)` - POST to create job
  - `getJobStatus(jobId)` - GET job status
  - `getArtifacts(jobId, cloud)` - GET generated files
  - `downloadArtifacts(jobId, cloud)` - GET ZIP blob
  - `waitForCompletion(jobId, onProgress)` - Poll until complete
- **Polling**: 5s intervals, 10-minute max timeout
- **Error Handling**: Extracts `detail` from error responses

#### `store/workflowStore.ts`
- **Purpose**: Zustand state management
- **State**:
  - `currentStep` - Current workflow step (1-3)
  - `selectedProvider` - Selected cloud (aws/azure)
  - `uploadedFile` - File metadata
  - `uploadedFileObject` - Actual File object
  - `designDocs` - Design documents per cloud
  - `terraformCode` - Generated Terraform code
  - `isAnalyzing` - Loading state
- **Actions**: Setters for each state, reset function

#### `components/cloud-selector/CloudSelector.tsx`
- **Purpose**: Cloud provider selection
- **Providers**: AWS, Azure (GCP removed)
- **Grid**: 2-column layout (was 3-column with GCP)

#### `components/actions/AnalyseButton.tsx`
- **Purpose**: Trigger pipeline execution
- **Flow**:
  1. Call `api.startPipeline()` → get job_id
  2. Call `api.waitForCompletion()` → poll with stage updates
  3. Store design docs from response
  4. Fetch artifacts
  5. Set terraform code in store
  6. Navigate to ResultsPage (step 3)

#### `pages/ResultsPage.tsx`
- **Purpose**: Display pipeline results
- **Layout**: 2-column grid
  - Left: DesignDocView
  - Right: TerraformCodeView

#### `components/DesignDocView.tsx`
- **Purpose**: Display design document
- **Display**: Preformatted markdown text
- **Header**: Title, component count, connection count

#### `components/TerraformCodeView.tsx`
- **Purpose**: Display generated Terraform code
- **Display**: Syntax-highlighted code (green on dark background)
- **Actions**: Download button (saves as `infrastructure.tf`)

---

## Configuration

### Backend Environment Variables (`.env`)

| Variable | Purpose | Default |
|----------|---------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for vision | Required |
| `GEMINI_VISION_MODEL` | Gemini model for image analysis | `gemini-2.5-pro` |
| `AWS_ACCESS_KEY_ID` | AWS access key for Bedrock | Required |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for Bedrock | Required |
| `AWS_DEFAULT_REGION` | AWS region for Bedrock | `us-east-1` |
| `AWS_BEDROCK_MODEL` | Bedrock model ID | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `UPLOAD_DIR` | Upload storage path | `storage/uploads` |
| `OUTPUT_DIR` | Output storage path | `storage/outputs` |
| `CHROMA_PERSIST_DIR` | ChromaDB storage path | `./chroma_db` |

### Frontend Configuration

- **API Base URL**: Empty string (uses Vite proxy to `http://localhost:8000`)
- **Proxy**: `/api` → `http://localhost:8000` (vite.config.js)
- **Dev Server**: `http://localhost:5173` (default)

---

## RAG Knowledge Base Setup

### Ingestion Scripts

```bash
# Ingest AWS Terraform provider docs
cd backend
python scripts/ingest_aws.py

# Ingest Azure Terraform provider docs
python scripts/ingest_azure.py
```

### Ingestion Process

1. **Scraping**: `registry_scraper.py` fetches docs from Terraform Registry
2. **Chunking**: `chunker.py` splits docs by markdown headings
3. **Embedding**: `embedder.py` creates embeddings and stores in ChromaDB
4. **Security Rules**: Hardcoded CIS benchmark rules are embedded

### Collections

| Collection | Purpose | Approx. Size |
|------------|---------|-------------|
| `aws_resources` | AWS provider docs | 500-1000 chunks |
| `azure_resources` | Azure provider docs | 400-800 chunks |
| `security_rules` | CIS benchmark rules | ~20 chunks |

---

## Error Handling & Resilience

### Backend

- **Vision Failure**: Returns error message, pipeline fails
- **ChromaDB Unavailable**: Falls back to Jinja2 templates
- **RAG Retrieval Failure**: Returns empty chunks, LLM generates without docs
- **Bedrock Failure**: Raises RuntimeError, pipeline fails
- **Validation Failure**: Adds warning comments to files, does not fail pipeline

### Frontend

- **Upload Error**: Displays error detail from backend
- **Polling Timeout**: Fails after 10 minutes
- **Network Error**: Displays error message, allows retry

---

## Known Issues & Limitations

1. **In-Memory Job Storage**: `_jobs` dict is in-memory (production should use database)
2. **ChromaDB Filter Syntax**: Must use `$and` operator for compound filters
3. **GCP Disabled**: Removed from frontend, backend still has partial support
4. **RAG Ingestion**: Network-dependent, may fail if Terraform Registry is down
5. **Rate Limits**: Hard-coded rate limits in code (should be configurable)

---

## Future Improvements

1. **Database**: Replace in-memory `_jobs` with PostgreSQL/SQLite
2. **Authentication**: Add user authentication and job isolation
3. **GCP Support**: Re-enable GCP with proper testing
4. **Module Support**: Generate modular Terraform code
5. **Cost Estimation**: Add cloud cost estimation from generated code
6. **Version History**: Track job history and Terraform versions
7. **Real-time Updates**: WebSocket for real-time pipeline progress
8. **Testing**: Add comprehensive test suite (pytest, Playwright)

---

## Deployment

### Backend

```bash
cd backend
pip install -r requirements.txt
python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Production

- Backend: Use Gunicorn/Uvicorn with proper logging
- Frontend: Build with `npm run build`, serve with nginx
- Database: Configure PostgreSQL for job storage
- ChromaDB: Use persistent storage or cloud-hosted vector DB
