"""
================================================================================
  backend/app/agents/rag_state.py  —  RAG PIPELINE STATE
================================================================================

PURPOSE:
  TypedDict for the RAG LangGraph pipeline state.

STATE FLOW:
  file_path → raw_text → chunks → embeddings → indexed → retrieved → reranked → response
================================================================================
"""

from typing import TypedDict, Optional, List, Dict, Any


class RAGState(TypedDict):
    """State for the RAG LangGraph pipeline."""

    # Input
    file_path: str                    # Path to uploaded document
    query: Optional[str]              # User query (for chat phase)

    # Document Processing
    raw_text: str                     # Extracted text from document
    chunks: List[str]                 # Text chunks for embedding
    metadata: Dict[str, Any]          # Document metadata (title, author, etc.)

    # Embedding & Indexing
    embeddings: List[List[float]]     # Vector embeddings
    indexed: bool                     # Whether document is indexed in Qdrant
    collection_name: str              # Qdrant collection name

    # Retrieval
    retrieved_nodes: List[Dict]       # Retrieved nodes from Qdrant
    reranked_nodes: List[Dict]        # Reranked nodes (top-k)
    context_str: str                  # Concatenated context for LLM

    # Generation
    response: str                     # LLM-generated response
    sources: List[Dict]               # Source references

    # Status
    error: Optional[str]              # Error message if any
    stage: str                        # Current pipeline stage
