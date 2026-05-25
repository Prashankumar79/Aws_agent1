"""Tests for the unified document extraction helper.

🟢 BEGINNER: We avoid spinning up Docling here — these tests cover the
language-agnostic logic (file-type detection, txt/csv parsing, helper
formatters). Heavy Docling-backed PDF parsing is exercised manually by the
RAG and design-doc flows during integration testing.
"""
import csv
from pathlib import Path

import pytest

from app.utils.document_extract import (
    ExtractedDocument,
    Heading,
    detect_file_type,
    extract_document,
    headings_to_outline,
    tables_to_block,
)


def test_detect_file_type():
    assert detect_file_type("foo.PDF") == "pdf"
    assert detect_file_type("/abs/path/foo.docx") == "docx"
    assert detect_file_type("notes.md") == "text"
    assert detect_file_type("data.CSV") == "spreadsheet"
    assert detect_file_type("diagram.png") == "image"
    assert detect_file_type("weird.xyz") == "unsupported"


def test_extract_text_file(tmp_path):
    p = tmp_path / "notes.md"
    p.write_text("# Heading\n\nHello world", encoding="utf-8")
    out = extract_document(p)
    assert out.method == "text"
    assert out.file_type == "text"
    assert "Hello world" in out.text
    assert out.error is None
    assert out.images == []


def test_extract_missing_file(tmp_path):
    out = extract_document(tmp_path / "does-not-exist.txt")
    assert out.error is not None
    assert "does not exist" in out.error.lower()


def test_extract_csv(tmp_path):
    p = tmp_path / "tiny.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["service", "tier"])
        w.writerow(["alb", "edge"])
        w.writerow(["rds", "data"])
    out = extract_document(p)
    assert out.method == "pandas"
    assert out.file_type == "spreadsheet"
    assert "service" in out.text
    assert "alb" in out.text
    assert len(out.tables) == 1


def test_extract_image_passthrough(tmp_path):
    # 🟢 BEGINNER: Real PNG content isn't required — we only assert that the
    # extractor records the path and short-circuits without attempting to read.
    p = tmp_path / "diagram.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = extract_document(p)
    assert out.method == "passthrough"
    assert out.file_type == "image"
    assert out.images == [str(p)]
    assert out.text == ""


def test_unsupported_file_returns_error(tmp_path):
    p = tmp_path / "weird.xyz"
    p.write_bytes(b"junk")
    out = extract_document(p)
    assert out.file_type == "unsupported"
    assert out.error is not None


def test_headings_to_outline_indents_by_level():
    headings = [
        Heading("Architecture", 1),
        Heading("Network", 2),
        Heading("VPC", 3),
        Heading("Compute", 2),
    ]
    outline = headings_to_outline(headings)
    assert "- Architecture" in outline
    assert "  - Network" in outline
    assert "    - VPC" in outline
    assert "  - Compute" in outline


def test_tables_to_block_caps_per_table():
    long_table = "x" * 5000
    out = tables_to_block([long_table, "small"], char_cap=100)
    assert "### Table 1" in out
    assert "### Table 2" in out
    # First table should be truncated to char_cap chars
    assert out.count("x") == 100
    assert "small" in out


def test_extracted_document_is_empty_helper():
    assert ExtractedDocument().is_empty is True
    assert ExtractedDocument(text="hi").is_empty is False
