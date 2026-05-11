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

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings — loaded from .env file and environment variables.

    Pydantic BaseSettings automatically reads values from:
      1. Environment variables (highest priority)
      2. .env file in project root
      3. Default values defined below (lowest priority)
    """

    # ── App Configuration ──────────────────────────────────────────────────
    # APP_NAME appears in API root response and startup logs.
    APP_NAME: str = "AWS Architecture AI"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Server Configuration ────────────────────────────────────────────────
    # BACKEND_PORT is where uvicorn listens.
    # FRONTEND_PORT is used for CORS origin generation.
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000

    # ── CORS Configuration ───────────────────────────────────────────────
    # ALLOWED_ORIGINS must include every domain that serves the React frontend.
    # Comma-separated list. In production, list exact origins, not "*".
    CORS_ORIGIN: str = "http://localhost:3000"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── AI Model Keys (REQUIRED for the app to work) ─────────────────────
    # GEMINI_API_KEY   → Google AI Studio API key (free tier available)
    # AWS credentials  → needed for Bedrock Claude access (not free)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_RPM_LIMIT: int = 15          # Rate limit safety guard
    GEMINI_VISION_MODEL: str = "gemini-2.5-pro"    # Diagram analysis
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"     # Fallback text tasks

    # ── AWS Configuration ─────────────────────────────────────────────────
    # These credentials need Bedrock InvokeModel permission.
    # Model ID format: us.anthropic.claude-sonnet-4-5-20250929-v1:0
    # The "us." prefix means the model is in the US region partition.
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_BEDROCK_MODEL: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    AWS_TEXTRACT_ENABLED: bool = True

    # ── Storage Configuration ───────────────────────────────────────────
    # All file paths are relative to backend/ working directory.
    # In production, switch STORAGE_TYPE to "s3" and set bucket name.
    STORAGE_TYPE: str = "local"
    STORAGE_BASE_PATH: str = "./data"
    UPLOAD_DIR: str = "storage/uploads"       # Raw diagram uploads
    PROCESSED_DIR: str = "storage/processed"  # OCR / vision outputs
    OUTPUT_DIR: str = "storage/outputs"       # Generated docs / code

    # ── Image Processing ─────────────────────────────────────────────────
    # MAX_IMAGE_SIZE_MB prevents users from uploading multi-gigabyte scans.
    # TILE_SIZE / TILE_OVERLAP are for future multi-tile vision analysis.
    MAX_IMAGE_SIZE_MB: int = 50
    TILE_SIZE: int = 1024
    TILE_OVERLAP: int = 128

    # ── Confidence Thresholds ────────────────────────────────────────────
    # Vision service uses these to flag uncertain component detections.
    # < LOW  → flagged as "needs review"
    # > HIGH → auto-accepted without human review
    CONFIDENCE_THRESHOLD_LOW: float = 0.65
    CONFIDENCE_THRESHOLD_HIGH: float = 0.85

    # ── Database ───────────────────────────────────────────────────────────
    # Currently unused (jobs stored in-memory). Future: aiosqlite or PostgreSQL.
    DATABASE_PATH: str = "archlens.db"

    # ── RAG (Retrieval-Augmented Generation) Configuration ────────────────
    # ChromaDB stores embeddings of AWS/Azure documentation.
    # EMBEDDING_MODEL converts text → vectors for semantic search.
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── LangChain ────────────────────────────────────────────────────────
    # If True, LangChain prints every LLM call to stdout (very verbose).
    LANGCHAIN_VERBOSE: bool = False

    class Config:
        # Tell Pydantic to load values from backend/.env file
        env_file = ".env"
        # Keys in .env must match case exactly (e.g. GEMINI_API_KEY, not gemini_api_key)
        case_sensitive = True


# ── Singleton export ───────────────────────────────────────────────────────
# Every other module imports this single instance.
settings = Settings()
