"""
================================================================================
  backend/app/core/config.py  —  CENTRALIZED CONFIGURATION
================================================================================

PURPOSE:
  Loads all environment variables into a typed, validated Python object.
  Every other file imports `settings` from here instead of reading os.environ
  directly. This is the single source of truth for configuration.

WHY IT EXISTS:
  Pydantic BaseSettings gives us:
    • Type safety (wrong type = crash on startup, not later)
    • Default values (works without .env for local dev)
    • Auto-loading from .env file (python-dotenv under the hood)
    • Validation (missing required keys raises clear errors)

CONNECTIONS TO OTHER FILES:
  • main.py          → uses APP_NAME, ALLOWED_ORIGINS for app bootstrap
  • services/*.py    → all AI services read API keys from here
  • rag/*.py         → reads CHROMA_PERSIST_DIR, EMBEDDING_MODEL

IMPORTANT:
  Create a .env file in backend/ with your real secrets:
      GEMINI_API_KEY=sk-...
      AWS_ACCESS_KEY_ID=AKIA...
      AWS_SECRET_ACCESS_KEY=...
  The .env file should NEVER be committed to Git.

PATTERN: Singleton
  `settings = Settings()` is a module-level singleton.
  Import it anywhere:  from app.core.config import settings
================================================================================
"""

# 🟢 BEGINNER: Pydantic BaseSettings automatically reads configuration from:
# 1. Environment variables (like GEMINI_API_KEY=xxx in your terminal)
# 2. A .env file in the project root
# 3. Default values defined right here in the code (lowest priority)
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


# 🟢 BEGINNER: Backend-relative directory (one level up from this file → backend/).
# We compute it here so things like CHROMA_PERSIST_DIR end up at an ABSOLUTE
# path that doesn't depend on which folder you ran the server from.
BACKEND_DIR = Path(__file__).resolve().parents[2]


# 🟢 BEGINNER: This class holds ALL configuration values for the entire backend.
# Instead of reading os.environ everywhere, every file just imports "settings" from here.
class Settings(BaseSettings):
    """Application settings — loaded from .env file and environment variables.

    Pydantic BaseSettings automatically reads values from:
      1. Environment variables (highest priority)
      2. .env file in project root
      3. Default values defined below (lowest priority)
    """

    # ── App Configuration ──────────────────────────────────────────────────
    APP_NAME: str = "AWS Architecture AI"   # 🟢 BEGINNER: Displayed in API root response and logs.
    ENVIRONMENT: str = "development"        # development | staging | production
    DEBUG: bool = False                     # 🟢 BEGINNER: If True, shows detailed error messages and enables /docs.
    LOG_LEVEL: str = "INFO"                 # 🟢 BEGINNER: Controls how much the server logs (DEBUG, INFO, WARNING, ERROR).

    # ── Server Configuration ────────────────────────────────────────────────
    BACKEND_PORT: int = 8000                # 🟢 BEGINNER: The port uvicorn listens on.
    FRONTEND_PORT: int = 3000               # 🟢 BEGINNER: Used to generate the CORS allowed origin.

    # ── CORS Configuration ───────────────────────────────────────────────
    CORS_ORIGIN: str = "http://localhost:3000"                            # 🟢 BEGINNER: Default frontend URL.
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"  # 🟢 BEGINNER: Comma-separated list of domains allowed to call this API.

    # ── AI Model Keys (REQUIRED for the app to work) ─────────────────────
    GEMINI_API_KEY: str = ""                            # 🟢 BEGINNER: Your Google AI Studio API key. Free tier available.
    GEMINI_MODEL: str = "gemini-2.5-flash"              # 🟢 BEGINNER: Default Gemini model for text tasks.
    GEMINI_RPM_LIMIT: int = 15                          # 🟢 BEGINNER: Requests-per-minute safety guard to avoid rate limits.
    GEMINI_VISION_MODEL: str = "gemini-2.5-pro"         # 🟢 BEGINNER: Stronger model used for analyzing architecture diagrams.
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"         # 🟢 BEGINNER: Faster/cheaper fallback for text-only tasks.

    # ── AWS Configuration ─────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""                                                       # 🟢 BEGINNER: AWS IAM key. Needs permission to call Bedrock InvokeModel.
    AWS_SECRET_ACCESS_KEY: str = ""                                                   # 🟢 BEGINNER: Secret part of the AWS key pair.
    AWS_DEFAULT_REGION: str = "us-east-1"                                             # 🟢 BEGINNER: AWS region where Bedrock is accessed.
    AWS_BEDROCK_MODEL: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"           # 🟢 BEGINNER: Claude model ID on Bedrock (for final generation).
    AWS_BEDROCK_HAIKU_MODEL: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"      # 🟢 BEGINNER: Haiku model ID on Bedrock (for context compression).
    AWS_TEXTRACT_ENABLED: bool = False                                                # 🟢 BEGINNER: Reserved flag for future AWS Textract OCR; OCR currently runs through Gemini Vision.

    # ── Storage Configuration ───────────────────────────────────────────
    STORAGE_TYPE: str = "local"               # 🟢 BEGINNER: "local" saves files to disk; "s3" would use AWS S3 in production.
    STORAGE_BASE_PATH: str = "./data"         # 🟢 BEGINNER: Root folder for all saved data.
    UPLOAD_DIR: str = "storage/uploads"       # 🟢 BEGINNER: Where uploaded diagram images are saved.
    PROCESSED_DIR: str = "storage/processed"  # 🟢 BEGINNER: Where OCR/vision output files go.
    OUTPUT_DIR: str = "storage/outputs"       # 🟢 BEGINNER: Where generated design docs and Terraform code are saved.

    # ── Image Processing ─────────────────────────────────────────────────
    MAX_IMAGE_SIZE_MB: int = 50  # 🟢 BEGINNER: Rejects uploads larger than 50 MB.
    TILE_SIZE: int = 1024        # 🟢 BEGINNER: For future multi-tile image analysis (not used yet).
    TILE_OVERLAP: int = 128      # 🟢 BEGINNER: Overlap between tiles to avoid cutting off objects at edges.

    # ── Confidence Thresholds ────────────────────────────────────────────
    CONFIDENCE_THRESHOLD_LOW: float = 0.65   # 🟢 BEGINNER: Below this, AI detections are flagged as "needs review".
    CONFIDENCE_THRESHOLD_HIGH: float = 0.85  # 🟢 BEGINNER: Above this, detections are auto-accepted.

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_PATH: str = "archlens.db"  # 🟢 BEGINNER: SQLite file path. Currently unused (jobs stored in JobStore).

    # ── RAG (Retrieval-Augmented Generation) Configuration ────────────────
    # 🟢 BEGINNER: Qdrant is the vector database that stores embeddings for the RAG chat feature.
    QDRANT_URL: str = "http://localhost:6333"
    RAG_COLLECTION_NAME: str = "infra_documents"

    # 🟢 BEGINNER: bge-small-en-v1.5: 33M params, 384 dim — 10x faster than BGE-M3, 92% quality.
    # Perfect for English documents (resumes, architecture docs, PDFs).
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # 🟢 BEGINNER: Larger chunks (1024 chars ≈ 200 words) give Haiku more context per retrieved section.
    # Overlap of 100 chars ensures sentences at chunk boundaries aren't lost.
    RAG_CHUNK_SIZE: int = 1024
    RAG_CHUNK_OVERLAP: int = 100

    # ── RAG retrieval tuning (hybrid search) ─────────────────────────────
    # 🟢 BEGINNER: How many candidates each branch (dense + sparse) returns
    # before Qdrant fuses them with Reciprocal Rank Fusion server-side.
    RAG_PREFETCH_LIMIT: int = 25
    # 🟢 BEGINNER: Final number of candidates the LLM (or reranker) sees.
    RAG_TOP_K: int = 5
    # 🟢 BEGINNER: Toggle the BGE cross-encoder reranker. Accurate but slow
    # (~150-300 ms on CPU). Set to false for sub-second responses if RRF alone is enough.
    RAG_USE_RERANKER: bool = True
    # 🟢 BEGINNER: BM25 model name from fastembed. The default Qdrant/bm25 is
    # ~5 MB, runs entirely on CPU, and encodes a query in ~1 ms.
    RAG_BM25_MODEL: str = "Qdrant/bm25"

    # LLM semantic cache. L1 exact cache is safe for all tasks; L2 semantic
    # matching is intentionally limited to lower-risk tasks so design docs and
    # Terraform prompts do not leak assumptions across similar architectures.
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_L1_MAX_SIZE: int = 500
    SEMANTIC_CACHE_L2_ENABLED: bool = True
    SEMANTIC_CACHE_L2_SCORE_THRESHOLD: float = 0.94
    SEMANTIC_CACHE_L2_TASK_TYPES: str = "template_compression,image_compression,prompt_compression,prompt_suggestions,rag_synthesis,terraform_chat,prompt_analysis,component_extraction"
    SEMANTIC_CACHE_VERSION: str = "v2"

    # 🟢 BEGINNER: Legacy ChromaDB store. Resolved to an ABSOLUTE path under backend/
    # so it points to the same folder no matter where you run python from.
    CHROMA_PERSIST_DIR: str = str(BACKEND_DIR / "chroma_db")

    # ── LangChain ────────────────────────────────────────────────────────
    LANGCHAIN_VERBOSE: bool = False  # 🟢 BEGINNER: If True, prints every LLM call to the server console (very noisy).

    # ── LangSmith Observability ──────────────────────────────────────────
    LANGSMITH_TRACING: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com/"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "Aws_agent"

    # ── Client Profile & Policy Engine ───────────────────────────────────
    ENABLE_REPAIR_LOOP: bool = True
    MAX_REPAIR_ATTEMPTS: int = 1
    DEFAULT_CLIENT_PROFILE: str = "default"

    # ── Auth (optional API key) ──────────────────────────────────────────
    # 🟢 BEGINNER: If set, every API route requires header `X-API-Key: <value>`.
    # Leave empty in development; STRONGLY recommended for production deployments.
    API_KEY: str = ""

    # ── LLM Gateway / Cost Control ───────────────────────────────────────
    DAILY_BUDGET_USD: float = 5.00        # 🟢 BEGINNER: Hard daily spend cap across all LLM calls. Resets at midnight.

    # ── Job lifecycle ────────────────────────────────────────────────────
    JOB_TTL_HOURS: int = 168              # 🟢 BEGINNER: Purge jobs older than this (default = 1 week).
    PIPELINE_TIMEOUT_SECONDS: int = 1800  # 🟢 BEGINNER: Hard cap on a pipeline run (default = 30 min).

    @property
    def allowed_origins_list(self) -> List[str]:
        """🟢 BEGINNER: Helper that returns ALLOWED_ORIGINS as a clean Python list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"prod", "production"}

    def validate_production_ready(self) -> None:
        """Fail fast when production is configured unsafely."""
        if not self.is_production:
            return

        errors: list[str] = []
        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if not self.API_KEY or len(self.API_KEY) < 32:
            errors.append("API_KEY must be set to a 32+ character secret in production")
        if not self.GEMINI_API_KEY or self.GEMINI_API_KEY.startswith("your_"):
            errors.append("GEMINI_API_KEY must be configured in production")
        if not self.AWS_ACCESS_KEY_ID or self.AWS_ACCESS_KEY_ID.startswith("your_"):
            errors.append("AWS_ACCESS_KEY_ID must be configured in production")
        if not self.AWS_SECRET_ACCESS_KEY or self.AWS_SECRET_ACCESS_KEY.startswith("your_"):
            errors.append("AWS_SECRET_ACCESS_KEY must be configured in production")
        if "*" in self.allowed_origins_list:
            errors.append("ALLOWED_ORIGINS must not contain '*' in production")

        if errors:
            raise RuntimeError("Production configuration is unsafe: " + "; ".join(errors))

    # 🟢 BEGINNER: Pydantic v2 way to configure a Settings class. The old
    # `class Config:` style still works but emits a deprecation warning.
    model_config = SettingsConfigDict(
        env_file=".env",       # 🟢 BEGINNER: Load values from a .env file in the backend folder.
        case_sensitive=True,    # 🟢 BEGINNER: Variable names in .env must match EXACT case.
        extra="ignore",         # 🟢 BEGINNER: Don't crash if .env contains keys we don't know about.
    )


# 🟢 BEGINNER: Create a single global instance. Every other module imports this "settings" object.
# It's a "singleton" — one shared instance used everywhere.
settings = Settings()
