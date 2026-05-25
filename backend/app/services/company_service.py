"""
================================================================================
  backend/app/services/company_service.py  —  COMPANY MANAGEMENT SERVICE
================================================================================

PURPOSE:
  Manage company/organization data for multi-tenant architecture.
  Each company has its own isolated set of instruction templates.

CONNECTIONS TO OTHER FILES:
  • api/v1/companies.py → CRUD endpoints
  • template_service.py → Templates are scoped by company_id

PRODUCTION NOTES:
  • All sqlite3.connect calls use a context manager so connections close
    even when an exception is raised mid-query.
  • check_same_thread=False is required because FastAPI dispatches handlers
    across the threadpool. Combined with WAL mode it gives us safe concurrent
    reads + serialised writes.
================================================================================
"""
# 🟢 BEGINNER: Standard-library imports for logging, SQLite, UUIDs, timestamps and typing.
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional, List, Dict
from pathlib import Path

# 🟢 BEGINNER: Logger for this module. Messages appear with [CompanyService] prefix.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Database path — resolved against THIS file so it works regardless of cwd.
DB_PATH = Path(__file__).parent.parent.parent / "data" / "companies.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """🟢 BEGINNER: Open a SQLite connection and ALWAYS close it.

    Using `with _connect() as conn:` guarantees the connection is closed even
    if an exception fires mid-query — fixes the file-handle leak bug.
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15.0)
    try:
        # 🟢 BEGINNER: WAL mode = "Write-Ahead Logging". Lets readers and writers run concurrently.
        conn.execute("PRAGMA journal_mode=WAL")
        # 🟢 BEGINNER: Enforce foreign-key constraints (off by default in SQLite).
        conn.execute("PRAGMA foreign_keys=ON")
        # 🟢 BEGINNER: Wait up to 10s if another writer is holding the lock instead of erroring out.
        conn.execute("PRAGMA busy_timeout=10000")
        yield conn
    finally:
        conn.close()


def _now() -> str:
    """🟢 BEGINNER: Current time as a timezone-aware ISO-8601 string (UTC)."""
    return datetime.now(timezone.utc).isoformat()


# 🟢 BEGINNER: Wraps all CRUD (Create / Read / Update / Delete) operations on the companies table.
class CompanyService:
    """Service for managing companies in a multi-tenant system."""

    def __init__(self):
        # 🟢 BEGINNER: Create the table on startup if it doesn't exist yet.
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database with companies table."""
        try:
            with _connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
            logger.info(f"[CompanyService] Database initialized at {DB_PATH}")
        except Exception as e:
            logger.error(f"[CompanyService] Database initialization failed: {e}", exc_info=True)
            raise

    def create_company(self, name: str) -> Dict:
        """🟢 BEGINNER: Insert a new company row and return its data."""
        if not name or not name.strip():
            raise ValueError("Company name is required")
        company_id = str(uuid.uuid4())
        now = _now()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO companies (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (company_id, name.strip(), now, now),
            )
            conn.commit()
        logger.info(f"[CompanyService] Created company: {company_id} - {name}")
        return {"id": company_id, "name": name.strip(), "created_at": now, "updated_at": now}

    def get_company(self, company_id: str) -> Optional[Dict]:
        """🟢 BEGINNER: Look up a single company by ID. Returns None if not found."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, name, created_at, updated_at FROM companies WHERE id = ?",
                (company_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "created_at": row[2], "updated_at": row[3]}

    def list_companies(self) -> List[Dict]:
        """🟢 BEGINNER: Return every company row as a list of dicts, sorted by name."""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at, updated_at FROM companies ORDER BY name"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows
        ]

    def update_company(self, company_id: str, name: str) -> Optional[Dict]:
        """🟢 BEGINNER: Rename a company. Returns the updated row or None if not found."""
        if not name or not name.strip():
            raise ValueError("Company name is required")
        now = _now()
        with _connect() as conn:
            cur = conn.execute(
                "UPDATE companies SET name = ?, updated_at = ? WHERE id = ?",
                (name.strip(), now, company_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        logger.info(f"[CompanyService] Updated company: {company_id}")
        return self.get_company(company_id)

    def delete_company(self, company_id: str) -> bool:
        """🟢 BEGINNER: Delete a company. Returns True if a row was actually removed."""
        with _connect() as conn:
            cur = conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
            conn.commit()
            deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"[CompanyService] Deleted company: {company_id}")
        return deleted
