"""
================================================================================
  backend/app/agents/nodes/document_parser.py  —  DOCUMENT PARSING AGENT
================================================================================

PURPOSE:
  Parse any uploaded non-image document (PDF, DOCX, TXT, MD, CSV, XLSX)
  into plain text + extracted embedded images. Images are saved to disk
  and their paths returned so the image_analyzer node can process them later.

OUTPUT:
  Updates state with:
    - raw_text: normalized text (tables preserved as Markdown)
    - embedded_images: list of file paths to extracted images
    - file_type: normalized type string
================================================================================
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)


def _log_node_enter(node_name: str, job_id: str, state: PipelineState):
    """Log node entry with a concise state summary."""
    logger.info(
        f"[PIPELINE][{node_name}][{job_id}] ENTER | "
        f"file_type={state.get('file_type', '?')}, "
        f"raw_text_len={len(state.get('raw_text', ''))}, "
        f"images={len(state.get('image_analysis', {}).get('components', []))}, "
        f"requirements_keys={list(state.get('structured_requirements', {}).keys())}, "
        f"stage={state.get('pipeline_stage', '?')}, "
        f"error={state.get('error') is not None}"
    )


def _log_node_exit(node_name: str, job_id: str, state: PipelineState):
    """Log node exit with updated state summary."""
    logger.info(
        f"[PIPELINE][{node_name}][{job_id}] EXIT  | "
        f"file_type={state.get('file_type', '?')}, "
        f"raw_text_len={len(state.get('raw_text', ''))}, "
        f"images={len(state.get('image_analysis', {}).get('components', []))}, "
        f"requirements_keys={list(state.get('structured_requirements', {}).keys())}, "
        f"stage={state.get('pipeline_stage', '?')}, "
        f"error={state.get('error') is not None}"
    )

# ── MIME / extension → category mapping ───────────────────────────────────
FILE_CATEGORIES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
    ".csv": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".svg": "image",
    ".drawio": "image",
}


def detect_file_type(file_path: str) -> str:
    """Return normalized file category from extension."""
    ext = Path(file_path).suffix.lower()
    return FILE_CATEGORIES.get(ext, "unsupported")


def parse_document(state: PipelineState) -> PipelineState:
    """LangGraph node: parse document text and extract embedded images."""
    file_path = state["file_path"]
    file_type = state.get("file_type", detect_file_type(file_path))
    job_id = state["job_id"]

    logger.info(f"🚀 [AGENT:DocumentParser] STARTED  | job_id={job_id} | file={Path(file_path).name} | type={file_type}")
    _log_node_enter("parse_document", job_id, state)
    logger.info(f"[DocumentParser:{job_id}] Parsing {file_type}: {file_path}")

    raw_text = ""
    embedded_images: list[str] = []

    try:
        if file_type == "pdf":
            raw_text, embedded_images = _parse_pdf(file_path, job_id)
        elif file_type == "docx":
            raw_text, embedded_images = _parse_docx(file_path, job_id)
        elif file_type == "text":
            raw_text = _parse_text(file_path)
        elif file_type == "spreadsheet":
            raw_text = _parse_spreadsheet(file_path)
        elif file_type == "image":
            # Images are handled by the image_analyzer node, not here
            raw_text = ""
        else:
            raw_text = f"[Unsupported file type: {file_type}. Only PDF, DOCX, TXT, MD, CSV, XLSX, and images are supported.]"
    except Exception as e:
        logger.error(f"[DocumentParser:{job_id}] Parse error: {e}")
        raw_text = f"[Document parsing failed: {e}]"

    result = {
        **state,
        "raw_text": raw_text,
        "embedded_images": embedded_images,
        "file_type": file_type,
        "pipeline_stage": "DOCUMENT_PARSED" if raw_text else "PARSING_FAILED",
    }
    _log_node_exit("parse_document", job_id, result)
    logger.info(f"✅ [AGENT:DocumentParser] COMPLETED | job_id={job_id} | text_len={len(result.get('raw_text', ''))} | images={len(result.get('embedded_images', []))}")
    return result


def _parse_pdf(file_path: str, job_id: str) -> tuple[str, list[str]]:
    """Extract text + tables + images via the unified Docling-first helper.

    🟢 BEGINNER: Replaces the old code that opened the PDF TWICE (pdfplumber
    for text, pymupdf for images). The shared helper opens it once and uses
    Docling for the heading-aware structured text + a single pymupdf pass
    for embedded images.
    """
    from app.utils.document_extract import extract_document

    logger.info(f"[DocumentParser:{job_id}] Starting PDF parsing: {file_path}")
    image_dir = Path(f"storage/uploads/{job_id}/embedded_images")

    extracted = extract_document(file_path, extract_images=True, image_dir=image_dir)
    if extracted.error and not extracted.text:
        # 🟢 BEGINNER: Hard failure — propagate so the pipeline records it.
        raise RuntimeError(extracted.error)

    # 🟢 BEGINNER: If Docling produced no native tables (e.g. pdfplumber path was
    # used) the table markdown is already inlined into `text` so we don't double-add.
    text = extracted.text
    if extracted.tables and extracted.method == "docling":
        # Append Docling tables — they aren't always inlined into export_to_markdown().
        text = text + "\n\n" + "\n\n".join(extracted.tables)

    logger.info(
        f"[DocumentParser:{job_id}] ✅ method={extracted.method} | "
        f"chars={len(text)} | tables={len(extracted.tables)} | "
        f"images={len(extracted.images)} | pages={extracted.page_count}"
    )
    return text, extracted.images


def _parse_docx(file_path: str, job_id: str) -> tuple[str, list[str]]:
    """Extract text + tables + images via the unified Docling-first helper."""
    from app.utils.document_extract import extract_document

    image_dir = Path(f"storage/uploads/{job_id}/embedded_images")
    extracted = extract_document(file_path, extract_images=True, image_dir=image_dir)
    if extracted.error and not extracted.text:
        raise RuntimeError(extracted.error)

    text = extracted.text
    if extracted.tables and extracted.method == "docling":
        text = text + "\n\n" + "\n\n".join(extracted.tables)

    logger.info(
        f"[DocumentParser:{job_id}] ✅ method={extracted.method} | "
        f"chars={len(text)} | tables={len(extracted.tables)} | "
        f"images={len(extracted.images)}"
    )
    return text, extracted.images


def _parse_text(file_path: str) -> str:
    """Read plain text / markdown file."""
    return Path(file_path).read_text(encoding="utf-8")


def _parse_spreadsheet(file_path: str) -> str:
    """Convert spreadsheet to Markdown tables."""
    import pandas as pd

    ext = Path(file_path).suffix.lower()
    text_parts = []

    if ext == ".csv":
        df = pd.read_csv(file_path)
        text_parts.append(_dataframe_to_markdown(df, "CSV Data"))
    else:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            text_parts.append(_dataframe_to_markdown(df, sheet_name))

    return "\n\n".join(text_parts)


def _table_to_markdown(table: list[list[Any]]) -> str:
    """Convert a pdfplumber table to Markdown."""
    if not table or not table[0]:
        return ""
    lines = []
    lines.append("| " + " | ".join(str(c) if c is not None else "" for c in table[0]) + " |")
    lines.append("|" + "|".join("---" for _ in table[0]) + "|")
    for row in table[1:]:
        lines.append("| " + " | ".join(str(c) if c is not None else "" for c in row) + " |")
    return "\n".join(lines)


def _docx_table_to_markdown(table) -> str:
    """Convert a python-docx table to Markdown."""
    lines = []
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append(cells)
    if not rows:
        return ""
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("|" + "|".join("---" for _ in rows[0]) + "|")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _dataframe_to_markdown(df, title: str) -> str:
    """Convert a pandas DataFrame to a Markdown table with a header."""
    lines = [f"### {title}"]
    lines.append("")
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    separator = "|" + "|".join("---" for _ in df.columns) + "|"
    lines.append(header)
    lines.append(separator)
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) if pd.notna(v) else "" for v in row) + " |")
    return "\n".join(lines)


def _log_node_enter_exit(func):
    """Decorator to auto-log entry and exit for pipeline nodes."""
    def wrapper(state: PipelineState):
        job_id = state["job_id"]
        _log_node_enter(func.__name__, job_id, state)
        result = func(state)
        _log_node_exit(func.__name__, job_id, result)
        return result
    return wrapper
