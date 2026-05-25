"""
================================================================================
  backend/app/services/template_service.py  —  INSTRUCTION TEMPLATE SERVICE
================================================================================

PURPOSE:
  Manage instruction templates for multi-tenant architecture.
  Each company has its own isolated set of templates.
  Global templates (is_default=true) are shared across all companies.

CONNECTIONS TO OTHER FILES:
  • api/v1/templates.py → CRUD endpoints
  • company_service.py → Templates are scoped by company_id
  • design_doc_service.py → Uses template instructions in generation
  • terraform_prompt_agent.py → Uses template rules in prompt generation

PRODUCTION NOTES:
  • All sqlite3.connect calls use a context manager so connections close
    even when an exception is raised mid-query.
  • check_same_thread=False is required because FastAPI dispatches handlers
    across the threadpool. Combined with WAL mode it gives us safe concurrent
    reads + serialised writes.
================================================================================
"""
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Database path — resolved against this file so it works regardless of cwd.
DB_PATH = Path(__file__).parent.parent.parent / "data" / "templates.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection, ensure it always closes."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Default Enterprise Standard Template (the MNC template provided by user)
DEFAULT_TEMPLATE_CONTENT = """You are an enterprise cloud architect and Terraform platform engineer.

Analyze the uploaded architecture diagram and generate:

1. Detailed cloud architecture design document
2. Production-ready Terraform generation prompt

Follow ALL enterprise standards and governance policies below.

==================================================
GENERAL CLOUD GOVERNANCE RULES
==================================================

- Use industry-standard cloud architecture patterns
- Follow Well-Architected Framework principles
- Prioritize high availability and fault tolerance
- Use modular and reusable Terraform architecture
- Avoid hardcoded values
- Infrastructure must support scalability
- Follow least privilege principle
- Prefer managed cloud services wherever possible
- Design for observability and monitoring
- Include disaster recovery considerations
- Ensure infrastructure is production-grade

==================================================
ENVIRONMENT RULES
==================================================

Environment Type: Production

Requirements:
- Multi-AZ deployment mandatory
- Auto scaling enabled
- No public exposure for databases
- Use private networking wherever possible
- Enable backup and recovery
- Enable centralized logging
- Enable monitoring and alerting
- Enable encryption at rest and in transit

==================================================
NAMING CONVENTIONS
==================================================

Naming Pattern:
<company>-<environment>-<service>-<resource-type>

Examples:
acme-prod-vpc-main
acme-prod-eks-cluster
acme-prod-rds-primary

Rules:
- Use lowercase only
- Use hyphen-separated naming
- Resource names must be unique
- Tags are mandatory

Mandatory Tags:
- Environment
- Owner
- Project
- CostCenter
- ManagedByTerraform

==================================================
SECURITY RULES
==================================================

- Apply least privilege IAM roles
- Avoid wildcard permissions
- Use IAM roles instead of static credentials
- All S3 buckets must block public access
- Enable encryption for all storage services
- Security groups must avoid 0.0.0.0/0 unless explicitly required
- Enable VPC flow logs
- Use private subnets for internal workloads
- Databases must not have public IPs
- Secrets must use Secrets Manager or Vault
- Enable audit logging

==================================================
NETWORKING RULES
==================================================

- Use dedicated VPC
- Minimum 3 private subnets across AZs
- Separate public and private subnets
- NAT Gateway required
- Internet Gateway only for public workloads
- CIDR ranges must avoid overlap
- Use internal load balancers for private services
- Use bastion host only if absolutely required

==================================================
TERRAFORM BEST PRACTICES
==================================================

- Use Terraform modules
- Separate environments using tfvars
- Store remote state securely
- Enable state locking
- Use reusable variables
- Use outputs cleanly
- Organize folders by:
    - modules/
    - environments/
    - shared/
- Follow DRY principles
- Avoid duplicate resources
- Generate production-grade code only

Folder Structure:
terraform/
 ├── modules/
 ├── environments/
 │    ├── dev/
 │    ├── stage/
 │    └── prod/
 ├── shared/
 ├── main.tf
 ├── variables.tf
 ├── outputs.tf
 └── providers.tf

==================================================
OBSERVABILITY RULES
==================================================

- Enable centralized logging
- Enable metrics collection
- Configure dashboards
- Configure alerts
- Enable tracing if microservices are detected
- Enable audit monitoring
- Include health checks

==================================================
COST OPTIMIZATION RULES
==================================================

- Prefer autoscaling
- Use right-sized instances
- Avoid overprovisioning
- Recommend spot instances for non-critical workloads
- Use lifecycle policies for storage
- Optimize networking costs

==================================================
DESIGN DOCUMENT REQUIREMENTS
==================================================

Generate:
- Executive summary
- Architecture overview
- Component explanation
- Networking design
- Security architecture
- Scalability considerations
- High availability design
- Disaster recovery approach
- Terraform implementation strategy
- Risks and assumptions
- Cost optimization recommendations
- Monitoring strategy
- Deployment workflow

==================================================
TERRAFORM PROMPT REQUIREMENTS
==================================================

Generate Terraform prompt that:
- Produces modular code
- Uses enterprise standards
- Uses reusable modules
- Includes provider configuration
- Includes variables and outputs
- Includes security best practices
- Includes networking setup
- Includes IAM policies
- Includes monitoring resources
- Includes tagging strategy
- Includes comments and documentation

==================================================
OUTPUT REQUIREMENTS
==================================================

Output must contain:

1. Architecture Understanding
2. Enterprise Design Document
3. Terraform Generation Prompt
4. Recommended Folder Structure
5. Security Considerations
6. Production Readiness Checklist
7. Risks and Improvements"""


class TemplateService:
    """Service for managing instruction templates in a multi-tenant system."""

    # 🟢 BEGINNER: Whitelist of columns that may appear in dynamic UPDATE statements.
    # Anything not in this set is rejected — defence-in-depth against SQL injection.
    _UPDATE_COLUMNS = {"name", "description", "content", "is_company_default"}

    def __init__(self):
        # 🟢 BEGINNER: Create the table on startup, then seed the Enterprise Standard default.
        self._init_db()
        self._seed_default_template()

    def _init_db(self) -> None:
        """Initialize the SQLite database with templates table."""
        try:
            with _connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS templates (
                        id TEXT PRIMARY KEY,
                        company_id TEXT,
                        name TEXT NOT NULL,
                        description TEXT,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        is_default BOOLEAN DEFAULT 0,
                        is_company_default BOOLEAN DEFAULT 0
                    )
                """)
                # 🟢 BEGINNER: Index makes "list templates for company X" fast even with millions of rows.
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_templates_company ON templates(company_id)"
                )
                conn.commit()
            logger.info(f"[TemplateService] Database initialized at {DB_PATH}")
        except Exception as e:
            logger.error(f"[TemplateService] Database initialization failed: {e}", exc_info=True)
            raise

    def _seed_default_template(self) -> None:
        """🟢 BEGINNER: Insert the global Enterprise Standard template once, at startup."""
        try:
            existing = self.get_template("enterprise-standard", None)
            if existing:
                return
            now = _now()
            with _connect() as conn:
                conn.execute(
                    """INSERT INTO templates (id, company_id, name, description, content, created_at, updated_at, is_default, is_company_default)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("enterprise-standard", None, "Enterprise Standard", "MNC Enterprise Governance Standards",
                     DEFAULT_TEMPLATE_CONTENT, now, now, True, False),
                )
                conn.commit()
            logger.info("[TemplateService] Seeded default Enterprise Standard template")
        except Exception as e:
            logger.error(f"[TemplateService] Failed to seed default template: {e}", exc_info=True)

    def create_template(self, company_id: Optional[str], name: str, description: str, content: str,
                        is_company_default: bool = False) -> Dict:
        """🟢 BEGINNER: Insert a new template for a specific company."""
        if not name or not name.strip():
            raise ValueError("Template name is required")
        if not content or not content.strip():
            raise ValueError("Template content is required")
        template_id = str(uuid.uuid4())
        now = _now()
        with _connect() as conn:
            conn.execute(
                """INSERT INTO templates (id, company_id, name, description, content, created_at, updated_at, is_default, is_company_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (template_id, company_id, name.strip(), description or "", content,
                 now, now, False, bool(is_company_default)),
            )
            conn.commit()
        logger.info(f"[TemplateService] Created template: {template_id} for company {company_id}")
        return {
            "id": template_id,
            "company_id": company_id,
            "name": name.strip(),
            "description": description or "",
            "content": content,
            "created_at": now,
            "updated_at": now,
            "is_default": False,
            "is_company_default": bool(is_company_default),
        }

    def get_template(self, template_id: str, company_id: Optional[str]) -> Optional[Dict]:
        """🟢 BEGINNER: Look up one template by ID. Returns either the company's own
        template OR a global default (company_id IS NULL). Returns None if neither."""
        with _connect() as conn:
            row = conn.execute(
                """SELECT id, company_id, name, description, content, created_at, updated_at, is_default, is_company_default
                   FROM templates WHERE id = ? AND (company_id = ? OR company_id IS NULL)""",
                (template_id, company_id),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "company_id": row[1],
            "name": row[2],
            "description": row[3],
            "content": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "is_default": bool(row[7]),
            "is_company_default": bool(row[8]),
        }

    def list_templates(self, company_id: Optional[str]) -> List[Dict]:
        """🟢 BEGINNER: Return every template visible to a company (its own + global defaults)."""
        with _connect() as conn:
            rows = conn.execute(
                """SELECT id, company_id, name, description, content, created_at, updated_at, is_default, is_company_default
                   FROM templates WHERE company_id = ? OR company_id IS NULL
                   ORDER BY is_default DESC, is_company_default DESC, name""",
                (company_id,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "company_id": r[1],
                "name": r[2],
                "description": r[3],
                "content": r[4],
                "created_at": r[5],
                "updated_at": r[6],
                "is_default": bool(r[7]),
                "is_company_default": bool(r[8]),
            }
            for r in rows
        ]

    def update_template(self, template_id: str, company_id: Optional[str],
                        name: Optional[str] = None, description: Optional[str] = None,
                        content: Optional[str] = None, is_company_default: Optional[bool] = None) -> Optional[Dict]:
        """🟢 BEGINNER: Partial update — only the columns you pass are modified.

        Builds the UPDATE dynamically but ONLY with columns from the whitelist
        ``_UPDATE_COLUMNS``. Untrusted column names can never appear in the SQL.
        """
        updates: list[str] = []
        params: list = []
        candidates = {
            "name": name,
            "description": description,
            "content": content,
            "is_company_default": is_company_default,
        }
        for col, val in candidates.items():
            if val is None:
                continue
            if col not in self._UPDATE_COLUMNS:
                # 🟢 BEGINNER: Defence-in-depth — should be impossible since we control the keys above.
                raise ValueError(f"Unknown column: {col}")
            updates.append(f"{col} = ?")
            params.append(val)
        if not updates:
            # 🟢 BEGINNER: No fields to update → return the row as-is.
            return self.get_template(template_id, company_id)

        now = _now()
        updates.append("updated_at = ?")
        params.append(now)
        params.extend([template_id, company_id])

        with _connect() as conn:
            cur = conn.execute(
                f"UPDATE templates SET {', '.join(updates)} "
                f"WHERE id = ? AND (company_id = ? OR company_id IS NULL)",
                params,
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        logger.info(f"[TemplateService] Updated template: {template_id}")
        return self.get_template(template_id, company_id)

    def delete_template(self, template_id: str, company_id: Optional[str]) -> bool:
        """🟢 BEGINNER: Delete a template. Global defaults (is_default=1) are protected."""
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM templates WHERE id = ? AND company_id = ? AND is_default = 0",
                (template_id, company_id),
            )
            conn.commit()
            deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"[TemplateService] Deleted template: {template_id}")
        return deleted
