"""
================================================================================
  backend/app/services/context_storage.py  —  RAW CONTEXT STORAGE SERVICE
================================================================================

PURPOSE:
  Store raw_context for debugging, observability, audit, and tracing.
  Raw context is the uncompressed version before Haiku compression.

WHY SEPARATE STORAGE:
  - Raw context can be very large (thousands of tokens)
  - Not needed for production generation (only master_context is used)
  - Useful for debugging compression quality
  - Useful for audit trails and compliance
  - Should be stored separately from generation pipeline

CONNECTIONS TO OTHER FILES:
  • nodes/haiku_compression.py → Calls save_raw_context after compression
  • jobs.py → Can load raw_context for debugging endpoints

IMPORTANT:
  This service is OPTIONAL and should only be enabled in development/debug mode.
  Production systems may disable this to save storage costs.
================================================================================
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ContextStorageService:
    """Service for storing and retrieving raw_context for debugging/audit."""

    def __init__(self):
        """Initialize the context storage service."""
        self.storage_dir = os.path.join(settings.STORAGE_BASE_PATH, "raw_context")
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info(f"[ContextStorage] Initialized with storage_dir: {self.storage_dir}")

    def save_raw_context(self, job_id: str, raw_context: Dict) -> bool:
        """
        Save raw_context to disk for debugging/audit.

        Args:
            job_id: Unique job identifier
            raw_context: Original uncompressed context before Haiku compression

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            filename = f"{job_id}_{timestamp.replace(':', '-')}.json"
            filepath = os.path.join(self.storage_dir, filename)

            # Add metadata
            storage_data = {
                "job_id": job_id,
                "timestamp": timestamp,
                "raw_context": raw_context,
                "metadata": {
                    "template_content_length": len(raw_context.get("template_content", "")),
                    "image_analysis_components": len(raw_context.get("image_analysis", {}).get("components", [])),
                    "user_prompt_length": len(raw_context.get("user_prompt", "")),
                    "fused_context_keys": list(raw_context.get("fused_context", {}).keys()),
                }
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, default=str)

            logger.info(f"[ContextStorage] Saved raw_context for job_id={job_id} to {filepath}")
            return True

        except Exception as e:
            logger.error(f"[ContextStorage] Failed to save raw_context for job_id={job_id}: {e}")
            return False

    def load_raw_context(self, job_id: str) -> Optional[Dict]:
        """
        Load raw_context from disk for debugging.

        Args:
            job_id: Unique job identifier

        Returns:
            Raw context dict if found, None otherwise
        """
        try:
            # Find the most recent file for this job_id
            files = [f for f in os.listdir(self.storage_dir) if f.startswith(job_id)]
            if not files:
                logger.warning(f"[ContextStorage] No raw_context found for job_id={job_id}")
                return None

            # Sort by timestamp (newest first)
            files.sort(reverse=True)
            filepath = os.path.join(self.storage_dir, files[0])

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"[ContextStorage] Loaded raw_context for job_id={job_id} from {filepath}")
            return data.get("raw_context")

        except Exception as e:
            logger.error(f"[ContextStorage] Failed to load raw_context for job_id={job_id}: {e}")
            return None

    def cleanup_old_contexts(self, days: int = 7) -> int:
        """
        Delete raw_context files older than specified days.

        Args:
            days: Delete files older than this many days

        Returns:
            Number of files deleted
        """
        try:
            import time
            cutoff_time = time.time() - (days * 86400)  # days to seconds
            deleted_count = 0

            for filename in os.listdir(self.storage_dir):
                filepath = os.path.join(self.storage_dir, filename)
                if os.path.getmtime(filepath) < cutoff_time:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info(f"[ContextStorage] Deleted old raw_context: {filename}")

            logger.info(f"[ContextStorage] Cleanup complete: deleted {deleted_count} files older than {days} days")
            return deleted_count

        except Exception as e:
            logger.error(f"[ContextStorage] Failed to cleanup old contexts: {e}")
            return 0


# Global instance
_context_storage_service = None


def get_context_storage() -> ContextStorageService:
    """Get or create the global context storage service instance."""
    global _context_storage_service
    if _context_storage_service is None:
        _context_storage_service = ContextStorageService()
    return _context_storage_service
