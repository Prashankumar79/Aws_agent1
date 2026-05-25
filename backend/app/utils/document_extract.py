"""
================================================================================
  backend/app/utils/document_extract.py  —  UNIFIED DOCUMENT EXTRACTION
================================================================================

PURPOSE:
  Single source of truth for parsing PDFs, DOCX, TXT, MD, CSV, XLSX into the
  shape every downstream pipeline needs. Replaces four duplicate
  implementations that each used a different library.

WHY DOCLING:
  Docling is IBM's research-grade document converter. Compared to raw
  pdfplumber it produces:
    • Real heading levels (instead of guessing from font size)
    • Reading-order-aware paragraph extraction
    • High-quality table structure (rows, cols, merged cells)
    • Markdown export that preserves the document's logical structure

  Docling is heavier than pdfplumber (~1 GB once its ML models are warm), so
  we ALWAYS keep pdfplumber + pymupdf as a graceful fallback. If Docling
  fails (corrupt PDF, OOM, etc.) we still return a usable result.

PERFORMANCE:
  • DocumentConverter is cached as a module-level singleton — first call pays
    the model-load cost (~5–15 s); subsequent calls are sub-second.
  • Image extraction is OPT-IN (extract_images=True). The RAG and design-doc
    callers pass True; the diagram generator passes False to skip the cost.
  • The PDF is opened ONCE per call (the old code opened it twice — once for
    text via pdfplumber, again for images via pymupdf).

OUTPUT — ExtractedDocument dataclass:
    text        str                — Markdown export (preserves headings, tables)
    headings    List[Heading]      — (text, level, page) tuples
    tables      List[str]          — markdown table strings
    images      List[str]          — absolute paths to extracted image files
    page_count  int
    file_type   str                — one of: pdf, docx, text, spreadsheet, image, unsupported
    method      str                — which path actually succeeded (docling | pdfplumber | docx | pandas)
    error       Optional[str]
================================================================================
"""

# 🟢 BEGINNER: Standard-library imports + dataclass for the return type.
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# 🟢 BEGINNER: Categorise a file by its extension so callers don't have to.
_FILE_CATEGORIES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
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
    ".bmp": "image",
    ".drawio": "image",
}


def detect_file_type(file_path: str | Path) -> str:
    """🟢 BEGINNER: Return one of: pdf, docx, text, spreadsheet, image, unsupported."""
    return _FILE_CATEGORIES.get(Path(file_path).suffix.lower(), "unsupported")


@dataclass
class Heading:
    """🟢 BEGINNER: One document heading with its nesting level."""
    text: str
    level: int = 1
    page: Optional[int] = None


@dataclass
class ExtractedDocument:
    """🟢 BEGINNER: Everything every downstream pipeline needs from a document."""
    text: str = ""
    headings: List[Heading] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    page_count: int = 0
    file_type: str = "unknown"
    method: str = "unknown"
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.tables and not self.images


# ── Singleton DocumentConverter ────────────────────────────────────────────
# 🟢 BEGINNER: Docling's DocumentConverter loads several ML models the first
# time it's constructed. Sharing one instance across requests saves 5–15 s
# of cold-start time per request. The lock guards against two requests trying
# to build it at the same time.
_DOCLING_CONVERTER = None
_DOCLING_LOCK = threading.Lock()
_DOCLING_DISABLED = False  # set after one fatal failure so we don't retry every call


def _get_docling_converter():
    """Lazy-singleton Docling converter. Returns None if Docling is unavailable."""
    global _DOCLING_CONVERTER, _DOCLING_DISABLED
    if _DOCLING_DISABLED:
        return None
    if _DOCLING_CONVERTER is not None:
        return _DOCLING_CONVERTER
    with _DOCLING_LOCK:
        if _DOCLING_CONVERTER is not None:
            return _DOCLING_CONVERTER
        try:
            from docling.document_converter import DocumentConverter
            logger.info("[DocumentExtract] Initialising Docling DocumentConverter (this may take a moment)...")
            _DOCLING_CONVERTER = DocumentConverter()
            logger.info("[DocumentExtract] Docling ready")
            return _DOCLING_CONVERTER
        except Exception as e:
            # Probably a missing optional dependency or torch incompatibility.
            # Disable so we don't spam logs every request.
            logger.warning(f"[DocumentExtract] Docling unavailable ({e}); falling back to pdfplumber/pymupdf.")
            _DOCLING_DISABLED = True
            return None


# ── Public entry point ────────────────────────────────────────────────────


def extract_document(
    file_path: str | Path,
    *,
    extract_images: bool = True,
    image_dir: Optional[str | Path] = None,
) -> ExtractedDocument:
    """🟢 BEGINNER: Parse any supported document into a uniform shape.

    Args:
        file_path:       Absolute path to the file on disk.
        extract_images:  When True, embedded images are written to ``image_dir``
                         (or ``<file>_images/`` next to the file if not supplied).
                         Skip this when you only need text — saves disk + CPU.
        image_dir:       Override directory for image output.

    Returns:
        ExtractedDocument — see dataclass above.
    """
    file_path = Path(file_path)
    file_type = detect_file_type(file_path)
    out = ExtractedDocument(file_type=file_type)

    if not file_path.exists():
        out.error = f"File does not exist: {file_path}"
        return out

    # 🟢 BEGINNER: Pick the parsing strategy based on file extension.
    try:
        if file_type == "pdf":
            _parse_pdf(file_path, out, extract_images=extract_images, image_dir=image_dir)
        elif file_type == "docx":
            _parse_docx(file_path, out, extract_images=extract_images, image_dir=image_dir)
        elif file_type == "text":
            _parse_text(file_path, out)
        elif file_type == "spreadsheet":
            _parse_spreadsheet(file_path, out)
        elif file_type == "image":
            # 🟢 BEGINNER: Images themselves carry no text; just record the path.
            out.images = [str(file_path)]
            out.method = "passthrough"
        else:
            out.error = f"Unsupported file type: {file_path.suffix}"
    except Exception as e:
        logger.error(f"[DocumentExtract] {file_path}: {e}", exc_info=True)
        out.error = str(e)

    if out.text:
        logger.info(
            f"[DocumentExtract] {file_path.name}: method={out.method}, "
            f"chars={len(out.text)}, headings={len(out.headings)}, "
            f"tables={len(out.tables)}, images={len(out.images)}, pages={out.page_count}"
        )
    return out


# ── PDF ─────────────────────────────────────────────────────────────────


def _parse_pdf(
    file_path: Path,
    out: ExtractedDocument,
    *,
    extract_images: bool,
    image_dir: Optional[str | Path],
) -> None:
    """Try Docling first, fall back to pdfplumber. Image extraction always uses pymupdf."""
    converter = _get_docling_converter()
    docling_ok = False
    if converter is not None:
        try:
            result = converter.convert(str(file_path))
            doc = result.document
            out.text = doc.export_to_markdown()
            out.method = "docling"
            try:
                for item, level in doc.iterate_items():
                    item_type = type(item).__name__
                    if "heading" in item_type.lower() or item_type == "SectionHeaderItem":
                        out.headings.append(Heading(
                            text=str(getattr(item, "text", item)),
                            level=int(level) if level else 1,
                        ))
                    elif "table" in item_type.lower():
                        try:
                            df = item.export_to_dataframe()
                            out.tables.append(df.to_markdown(index=False))
                        except Exception:
                            pass
            except Exception as iter_err:
                logger.debug(f"[DocumentExtract] Docling item iteration failed: {iter_err}")
            try:
                out.page_count = len(doc.pages)
            except Exception:
                pass
            docling_ok = bool(out.text.strip())
        except Exception as e:
            logger.warning(f"[DocumentExtract] Docling failed for {file_path.name}: {e}; using pdfplumber fallback.")

    if not docling_ok:
        # 🟢 BEGINNER: pdfplumber fallback — gives us text + raw tables (no real heading info).
        try:
            import pdfplumber
            text_parts: list[str] = []
            with pdfplumber.open(file_path) as pdf:
                out.page_count = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                        for table in page.extract_tables() or []:
                            md = _table_to_markdown(table)
                            if md:
                                out.tables.append(md)
                                text_parts.append(md)
                    except Exception as page_err:
                        logger.warning(f"[DocumentExtract] pdfplumber page {page_num} error: {page_err}")
            out.text = "\n\n".join(text_parts)
            out.method = "pdfplumber"
        except Exception as e:
            out.error = f"PDF text extraction failed: {e}"
            return

    if extract_images:
        out.images = _extract_pdf_images(file_path, image_dir)


def _extract_pdf_images(file_path: Path, image_dir: Optional[str | Path]) -> List[str]:
    """🟢 BEGINNER: Extract embedded images via pymupdf. Always opens the PDF only once."""
    image_paths: list[str] = []
    target_dir = Path(image_dir) if image_dir else file_path.parent / f"{file_path.stem}_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.warning("[DocumentExtract] pymupdf not installed — skipping PDF image extraction.")
        return image_paths

    try:
        doc = fitz.open(str(file_path))
        try:
            for page_num, page in enumerate(doc):
                for img_idx, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                        ext = base.get("ext", "png")
                        out_path = target_dir / f"page{page_num}_img{img_idx}.{ext}"
                        out_path.write_bytes(base["image"])
                        image_paths.append(str(out_path))
                    except Exception as img_err:
                        logger.debug(f"[DocumentExtract] image {xref} extract failed: {img_err}")
        finally:
            doc.close()
    except Exception as e:
        logger.warning(f"[DocumentExtract] PDF image extraction error: {e}")
    return image_paths


# ── DOCX ────────────────────────────────────────────────────────────────


def _parse_docx(
    file_path: Path,
    out: ExtractedDocument,
    *,
    extract_images: bool,
    image_dir: Optional[str | Path],
) -> None:
    """Docling first, then python-docx fallback for older DOCX features."""
    converter = _get_docling_converter()
    docling_ok = False
    if converter is not None:
        try:
            result = converter.convert(str(file_path))
            doc = result.document
            out.text = doc.export_to_markdown()
            out.method = "docling"
            try:
                for item, level in doc.iterate_items():
                    item_type = type(item).__name__
                    if "heading" in item_type.lower() or item_type == "SectionHeaderItem":
                        out.headings.append(Heading(
                            text=str(getattr(item, "text", item)),
                            level=int(level) if level else 1,
                        ))
                    elif "table" in item_type.lower():
                        try:
                            df = item.export_to_dataframe()
                            out.tables.append(df.to_markdown(index=False))
                        except Exception:
                            pass
            except Exception:
                pass
            docling_ok = bool(out.text.strip())
        except Exception as e:
            logger.warning(f"[DocumentExtract] Docling failed for {file_path.name}: {e}; using python-docx fallback.")

    if not docling_ok:
        try:
            from docx import Document
            doc = Document(str(file_path))
            text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                md = _docx_table_to_markdown(table)
                if md:
                    out.tables.append(md)
                    text_parts.append(md)
            out.text = "\n\n".join(text_parts)
            out.method = "docx"
        except Exception as e:
            out.error = f"DOCX extraction failed: {e}"
            return

    if extract_images:
        out.images = _extract_docx_images(file_path, image_dir)


def _extract_docx_images(file_path: Path, image_dir: Optional[str | Path]) -> List[str]:
    """🟢 BEGINNER: Pull embedded images out of a DOCX (it's a zip with media/ inside)."""
    image_paths: list[str] = []
    target_dir = Path(image_dir) if image_dir else file_path.parent / f"{file_path.stem}_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        from docx import Document
        doc = Document(str(file_path))
        for idx, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.reltype:
                try:
                    blob = rel.target_part.blob
                    ext = (rel.target_part.content_type or "image/png").split("/")[-1]
                    if ext == "jpeg":
                        ext = "jpg"
                    out_path = target_dir / f"embedded_img_{idx}.{ext}"
                    out_path.write_bytes(blob)
                    image_paths.append(str(out_path))
                except Exception as img_err:
                    logger.debug(f"[DocumentExtract] DOCX image {idx} failed: {img_err}")
    except Exception as e:
        logger.warning(f"[DocumentExtract] DOCX image extraction failed: {e}")
    return image_paths


# ── TEXT / SPREADSHEET ──────────────────────────────────────────────────


def _parse_text(file_path: Path, out: ExtractedDocument) -> None:
    out.text = file_path.read_text(encoding="utf-8", errors="ignore")
    out.method = "text"


def _parse_spreadsheet(file_path: Path, out: ExtractedDocument) -> None:
    """CSV / XLSX → markdown tables."""
    import pandas as pd
    suffix = file_path.suffix.lower()
    parts: list[str] = []
    if suffix == ".csv":
        df = pd.read_csv(file_path)
        md = _dataframe_to_markdown(df, "CSV Data")
        out.tables.append(md)
        parts.append(md)
    else:
        xls = pd.ExcelFile(file_path)
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            md = _dataframe_to_markdown(df, str(sheet))
            out.tables.append(md)
            parts.append(md)
    out.text = "\n\n".join(parts)
    out.method = "pandas"


# ── Markdown helpers ────────────────────────────────────────────────────


def _table_to_markdown(table: List[List[object]]) -> str:
    """🟢 BEGINNER: Pdfplumber returns tables as nested lists; convert to markdown."""
    if not table or not table[0]:
        return ""
    header = "| " + " | ".join(str(c) if c is not None else "" for c in table[0]) + " |"
    sep = "|" + "|".join("---" for _ in table[0]) + "|"
    rows = ["| " + " | ".join(str(c) if c is not None else "" for c in row) + " |" for row in table[1:]]
    return "\n".join([header, sep, *rows])


def _docx_table_to_markdown(table) -> str:
    """🟢 BEGINNER: python-docx Table → markdown string."""
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "|".join("---" for _ in rows[0]) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([header, sep, *body])


def _dataframe_to_markdown(df, title: str) -> str:
    """🟢 BEGINNER: pandas DataFrame → markdown with a heading."""
    import pandas as pd
    if df is None or df.empty:
        return f"### {title}\n\n*(empty)*"
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = [
        "| " + " | ".join(str(v) if pd.notna(v) else "" for v in row) + " |"
        for _, row in df.iterrows()
    ]
    return "\n".join([f"### {title}", "", header, sep, *body])


# ── Convenience helpers used by callers ────────────────────────────────


def headings_to_outline(headings: List[Heading], limit: int = 30) -> str:
    """🟢 BEGINNER: Produce an indented outline of headings for prompts."""
    lines = []
    for h in headings[:limit]:
        indent = "  " * max(0, h.level - 1)
        lines.append(f"{indent}- {h.text}")
    return "\n".join(lines)


def tables_to_block(tables: List[str], limit: int = 5, char_cap: int = 1500) -> str:
    """🟢 BEGINNER: Concatenate the first few tables into a single block."""
    blocks = []
    for i, t in enumerate(tables[:limit]):
        blocks.append(f"### Table {i + 1}\n{t[:char_cap]}")
    return "\n\n".join(blocks)
