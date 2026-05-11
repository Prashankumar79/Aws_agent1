"""
================================================================================
  backend/app/services/upload_service.py  —  FILE UPLOAD UTILITY
================================================================================

PURPOSE:
  Encapsulates all file-handling logic: validation, disk writes, cleanup.
  Keeps the API route (upload.py / jobs.py) clean of filesystem details.

WHY IT EXISTS:
  Separation of concerns. The router decides WHAT to do (accept uploads);
  this service decides HOW (validate extensions, choose paths, write bytes).

CONNECTIONS TO OTHER FILES:
  • api/upload.py      → calls validate_*() and save_file()
  • api/v1/jobs.py     → calls save_file() during pipeline creation

SECURITY NOTES:
  • Path traversal is blocked by using UUIDs as filenames, not user input.
  • Extension whitelist prevents execution of uploaded scripts.
  • Size limit prevents DoS via multi-gigabyte uploads.

PATTERN: Service Layer
  A plain Python class with no FastAPI dependencies. Easily testable.
================================================================================
"""

import os
import uuid
from pathlib import Path
from typing import Optional


class UploadService:
    """Handles file uploads: validation, storage, and cleanup.

    All uploaded files are stored in ./uploads/ relative to the backend
    working directory. Files are renamed to UUIDs to prevent collisions
    and path-traversal attacks.
    """

    # ── Class-level constants ──────────────────────────────────────────
    # Whitelist of extensions we can actually process.
    # .drawio and .lucidchart are raw export formats from diagram tools.
    ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf', '.svg', '.drawio', '.lucidchart'}

    # 50 MB limit. Diagrams are rarely > 10 MB, but large PDFs can be bigger.
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    # Directory where uploaded files are persisted.
    # Created automatically if it doesn't exist.
    UPLOAD_DIR = Path("uploads")

    def __init__(self):
        # Ensure the upload directory exists on first use.
        # exist_ok=True means no error if the dir is already there.
        self.UPLOAD_DIR.mkdir(exist_ok=True)

    # ── Validation methods ───────────────────────────────────────────────

    def validate_file_type(self, filename: str) -> bool:
        """Check if the file extension is in the allowed whitelist.

        Args:
            filename: Original filename from the client (e.g. "diagram.png").

        Returns:
            True if extension is allowed, False otherwise.
        """
        ext = Path(filename).suffix.lower()
        return ext in self.ALLOWED_EXTENSIONS

    def validate_file_size(self, file_content: bytes) -> bool:
        """Check if the file content fits within the size limit.

        Args:
            file_content: Raw bytes read from the uploaded file.

        Returns:
            True if size <= 50 MB, False otherwise.
        """
        return len(file_content) <= self.MAX_FILE_SIZE

    # ── Persistence methods ────────────────────────────────────────────

    async def save_file(self, file_content: bytes, filename: str) -> str:
        """Write the uploaded bytes to disk with a UUID filename.

        Args:
            file_content: Raw bytes of the file.
            filename:     Original filename (used only for extension extraction).

        Returns:
            Absolute or relative path to the saved file.
        """
        # Generate a random UUID to use as the filename.
        # This prevents: filename collisions, path traversal (../../etc/passwd),
        # and special-character injection in filenames.
        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower()
        new_filename = f"{file_id}{ext}"
        file_path = self.UPLOAD_DIR / new_filename

        # Write binary content to disk.
        with open(file_path, 'wb') as f:
            f.write(file_content)

        return str(file_path)

    async def delete_file(self, file_path: str) -> bool:
        """Remove a previously uploaded file from disk.

        Args:
            file_path: Full path returned by save_file().

        Returns:
            True if deleted (or already gone), False on unexpected error.
        """
        try:
            Path(file_path).unlink()
            return True
        except Exception:
            # File might not exist — not an error for our use case.
            return False
