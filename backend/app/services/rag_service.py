"""
================================================================================
  backend/app/services/rag_service.py  —  RAG CHAT SERVICE (HYBRID SEARCH)
================================================================================

PURPOSE:
  Implements the RAG (Retrieval-Augmented Generation) pipeline using LangGraph.

PIPELINE (indexing):
  1. parse_document      — unified Docling-first extractor (see app.utils.document_extract)
  2. extract_metadata
  3. generate_embeddings — BGE-M3 (dense) + BM25 (sparse, via fastembed)
  4. index_qdrant        — single collection with TWO vectors per point (dense + sparse)

PIPELINE (retrieval):
  5. hybrid_retrieve     — server-side RRF fusion: Qdrant runs dense and sparse
                           prefetches IN PARALLEL and fuses with Reciprocal Rank
                           Fusion in one round-trip. Falls back to dense-only if
                           the BM25 model isn't available.
  6. rerank              — BGE cross-encoder reranks top-N → top-K (optional)
  7. generate_response   — Claude (Bedrock) streamed answer over fused context

WHY HYBRID:
  Dense vectors capture semantic meaning ("show me network design" matches
  "VPC architecture overview"). Sparse BM25 catches exact-term hits the LLM
  embedding might miss ("AS123 routing" or specific service codes). RRF
  combines them without needing tuned alpha weights.

PERFORMANCE:
  • Dense + sparse prefetches are dispatched IN PARALLEL by Qdrant — one HTTP
    round-trip, ~50–80 ms total on a local container.
  • The cross-encoder reranker only sees the top RAG_PREFETCH_LIMIT candidates
    (default 25), keeping CPU rerank under ~200 ms.
  • Reranker is gated by ``settings.RAG_USE_RERANKER`` — disable for sub-second
    end-to-end if RRF is enough for your corpus.
================================================================================
"""

# 🟢 BEGINNER: Standard library + pipeline imports.
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Generator, List, Tuple

from langgraph.graph import StateGraph, END

from app.agents.rag_state import RAGState
from app.core.config import settings

logger = logging.getLogger(__name__)


# 🟢 BEGINNER: Named-vector keys for the hybrid collection. Qdrant stores TWO
# vectors per point — one dense, one sparse — and we reference them by name
# during search. Keep these constant; changing them requires re-indexing.
DENSE_NAME = "dense"
SPARSE_NAME = "sparse"


class RAGService:
    """RAG service with LangGraph pipeline + hybrid search."""

    def __init__(self):
        self.graph = self._build_graph()
        self._qdrant_client = None
        self._embedding_model = None  # BGE-M3 dense
        self._bm25_model = None       # fastembed sparse
        self._reranker = None         # BGE cross-encoder
        self._llm = None
        # 🟢 BEGINNER: Cached collection metadata so we don't re-check Qdrant
        # on every request after the first indexing call.
        self._collection_ready: bool = False
        self._embedding_dim: Optional[int] = None

    # ── LangGraph wiring ────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        """🟢 BEGINNER: Build the indexing-only LangGraph.
        The retrieval path doesn't go through LangGraph — it runs as a small
        in-process pipeline inside ``chat()``."""
        graph = StateGraph(RAGState)

        graph.add_node("parse_document", self._parse_document)
        graph.add_node("extract_metadata", self._extract_metadata)
        graph.add_node("generate_embeddings", self._generate_embeddings)
        graph.add_node("index_qdrant", self._index_qdrant)

        graph.set_entry_point("parse_document")
        graph.add_edge("parse_document", "extract_metadata")
        graph.add_edge("extract_metadata", "generate_embeddings")
        graph.add_edge("generate_embeddings", "index_qdrant")
        graph.add_edge("index_qdrant", END)

        return graph.compile()

    # ── Lazy singletons for heavy resources ─────────────────────────────

    def _get_qdrant_client(self):
        """🟢 BEGINNER: One Qdrant client per process. Reuses the underlying
        HTTP keep-alive connection so search latency stays low."""
        if self._qdrant_client is None:
            from qdrant_client import QdrantClient
            self._qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=30)
        return self._qdrant_client

    def _get_embedding_model(self):
        """🟢 BEGINNER: BGE-M3 dense embedder. ~2.3 GB once loaded — singleton."""
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[RAG] Loading dense embedding model: {settings.EMBEDDING_MODEL}")
            self._embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device="cpu",
            )
        return self._embedding_model

    def _get_bm25_model(self):
        """🟢 BEGINNER: BM25 sparse encoder via fastembed. ~5 MB, CPU-only,
        ~1 ms to encode a query. Returns None if fastembed isn't installed
        so the rest of the pipeline degrades gracefully to dense-only."""
        if self._bm25_model is False:
            return None
        if self._bm25_model is None:
            try:
                from fastembed import SparseTextEmbedding
                logger.info(f"[RAG] Loading BM25 sparse model: {settings.RAG_BM25_MODEL}")
                self._bm25_model = SparseTextEmbedding(model_name=settings.RAG_BM25_MODEL)
            except Exception as e:
                logger.warning(f"[RAG] BM25 unavailable ({e}); hybrid search will run dense-only.")
                self._bm25_model = False
                return None
        return self._bm25_model

    def _get_reranker(self):
        """🟢 BEGINNER: BGE cross-encoder reranker. Slowest stage (~150–300 ms
        on CPU); only loaded when ``settings.RAG_USE_RERANKER`` is True."""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"[RAG] Loading reranker: {settings.RERANKER_MODEL}")
            self._reranker = CrossEncoder(settings.RERANKER_MODEL, device="cpu")
        return self._reranker

    def _get_llm(self):
        """Deprecated: pure retrieval RAG doesn't use an LLM. Kept for compatibility."""
        return None

    # ── Indexing nodes ───────────────────────────────────────────────────

    def _parse_document(self, state: RAGState) -> RAGState:
        """Parse document via the unified Docling-first extractor."""
        try:
            from app.utils.document_extract import extract_document

            logger.info(f"[RAG] Parsing document: {state['file_path']}")
            extracted = extract_document(state["file_path"], extract_images=False)
            if extracted.error and not extracted.text:
                raise RuntimeError(extracted.error)

            return {
                **state,
                "raw_text": extracted.text,
                "stage": f"parsed:{extracted.method}",
            }
        except Exception as e:
            logger.error(f"[RAG] Parse failed: {e}", exc_info=True)
            return {**state, "error": str(e), "stage": "failed"}

    def _extract_metadata(self, state: RAGState) -> RAGState:
        """Pull file-level metadata for citation/filtering."""
        try:
            file_path = Path(state["file_path"])
            existing = state.get("metadata") or {}
            # Prefer the original filename passed in by the API layer; fall back to disk filename
            display_name = existing.get("original_filename") or file_path.name
            metadata = {
                "filename": display_name,
                "file_size": file_path.stat().st_size,
                "indexed_at": time.time(),
            }
            return {**state, "metadata": metadata, "stage": "metadata_extracted"}
        except Exception as e:
            logger.error(f"[RAG] Metadata extraction failed: {e}")
            return {**state, "error": str(e), "stage": "failed"}

    def _generate_embeddings(self, state: RAGState) -> RAGState:
        """Generate dense (BGE-M3) embeddings + chunked text.

        🟢 BEGINNER: Sparse BM25 vectors are produced lazily inside
        ``_index_qdrant`` so we don't store them in the state dict (they're
        big and wouldn't survive JSON serialisation).
        """
        try:
            model = self._get_embedding_model()
            text = state["raw_text"]
            chunks = self._chunk_text(text)
            logger.info(f"[RAG] Generated {len(chunks)} chunks")

            embeddings = model.encode(chunks, batch_size=32, show_progress_bar=False)
            embeddings_list = embeddings.tolist() if hasattr(embeddings, "tolist") else list(embeddings)

            return {
                **state,
                "chunks": chunks,
                "embeddings": embeddings_list,
                "stage": "embeddings_generated",
            }
        except Exception as e:
            logger.error(f"[RAG] Embedding generation failed: {e}", exc_info=True)
            return {**state, "error": str(e), "stage": "failed"}

    def _chunk_text(self, text: str) -> List[str]:
        """Sentence-aware chunking: split on paragraph/sentence boundaries.

        Strategy:
        1. Split on double-newlines (paragraph breaks) first — preserves document structure
        2. If a paragraph is too long, split further on sentence endings
        3. Merge short paragraphs together up to RAG_CHUNK_SIZE
        4. Apply overlap by prepending the last sentence of the previous chunk

        This keeps tables, bullet lists, and sentences intact — critical for
        Docling-parsed PDFs that preserve markdown structure.
        """
        import re as _re

        chunk_size = settings.RAG_CHUNK_SIZE
        overlap = settings.RAG_CHUNK_OVERLAP

        # Step 1: Split on paragraph boundaries (double newlines)
        paragraphs = [p.strip() for p in _re.split(r'\n\s*\n', text) if p.strip()]

        # Step 2: Further split very long paragraphs on sentence endings
        sentences: List[str] = []
        for para in paragraphs:
            if len(para) <= chunk_size:
                sentences.append(para)
            else:
                # Split on sentence endings, keeping the delimiter
                parts = _re.split(r'(?<=[.!?])\s+', para)
                sentences.extend(p.strip() for p in parts if p.strip())

        # Step 3: Merge sentences into chunks up to chunk_size
        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if current_len + sent_len + 1 > chunk_size and current_parts:
                chunk_text = '\n'.join(current_parts)
                chunks.append(chunk_text)
                # Step 4: Overlap — keep last sentence(s) for context continuity
                overlap_parts: List[str] = []
                overlap_len = 0
                for part in reversed(current_parts):
                    if overlap_len + len(part) > overlap:
                        break
                    overlap_parts.insert(0, part)
                    overlap_len += len(part)
                current_parts = overlap_parts
                current_len = overlap_len
            current_parts.append(sent)
            current_len += sent_len + 1

        if current_parts:
            chunks.append('\n'.join(current_parts))

        logger.info(f"[RAG] Chunked into {len(chunks)} sentence-aware chunks (avg {sum(len(c) for c in chunks)//max(len(chunks),1)} chars)")
        return chunks

    def _ensure_hybrid_collection(self, dim: int) -> None:
        """🟢 BEGINNER: Create or migrate the Qdrant collection so it has BOTH
        a dense and sparse vector slot. If a legacy dense-only collection
        exists from earlier indexing, recreate it (data is re-indexed below)."""
        from qdrant_client.models import (
            Distance, VectorParams, SparseVectorParams, SparseIndexParams
        )

        client = self._get_qdrant_client()
        name = settings.RAG_COLLECTION_NAME

        existing = {c.name for c in client.get_collections().collections}
        if name in existing:
            # Detect whether this collection is the legacy unnamed-vector layout.
            try:
                info = client.get_collection(name)
                vec_cfg = info.config.params.vectors
                # `vec_cfg` is a single VectorParams (legacy) or a dict of named ones.
                is_named = isinstance(vec_cfg, dict)
                has_sparse = bool(getattr(info.config.params, "sparse_vectors", None))
                if is_named and DENSE_NAME in (vec_cfg or {}) and has_sparse:
                    self._collection_ready = True
                    self._embedding_dim = dim
                    return
                # Legacy / mismatched → recreate.
                logger.warning(
                    f"[RAG] Recreating collection '{name}' to add hybrid vectors "
                    f"(was named={is_named}, sparse={has_sparse})."
                )
                client.delete_collection(name)
            except Exception as inspect_err:
                logger.warning(f"[RAG] Could not inspect collection: {inspect_err}; recreating.")
                try:
                    client.delete_collection(name)
                except Exception:
                    pass

        client.create_collection(
            collection_name=name,
            vectors_config={
                DENSE_NAME: VectorParams(size=dim, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                SPARSE_NAME: SparseVectorParams(index=SparseIndexParams()),
            },
        )
        logger.info(f"[RAG] Created hybrid collection '{name}' (dense dim={dim} + sparse BM25)")
        self._collection_ready = True
        self._embedding_dim = dim

    def _encode_sparse(self, texts: List[str]) -> Optional[List[Tuple[List[int], List[float]]]]:
        """🟢 BEGINNER: Encode a batch of strings with BM25. Returns a list of
        (indices, values) tuples — the wire format Qdrant wants. Returns None
        if BM25 isn't available so callers can skip sparse indexing."""
        bm25 = self._get_bm25_model()
        if bm25 is None:
            return None
        sparse = list(bm25.embed(texts))
        out: list[tuple[list[int], list[float]]] = []
        for s in sparse:
            # fastembed exposes .indices / .values attributes (numpy arrays).
            idx = list(getattr(s, "indices", []))
            vals = list(getattr(s, "values", []))
            out.append(([int(i) for i in idx], [float(v) for v in vals]))
        return out

    def _index_qdrant(self, state: RAGState) -> RAGState:
        """Index dense + sparse vectors as named vectors on a hybrid collection."""
        try:
            from qdrant_client.models import PointStruct, SparseVector

            if not state.get("embeddings") or not state.get("chunks"):
                raise RuntimeError("No chunks/embeddings to index")

            dim = len(state["embeddings"][0])
            self._ensure_hybrid_collection(dim)

            # Clear existing data so only the latest indexed document is searchable.
            # This prevents stale content from a previous document leaking into results.
            client = self._get_qdrant_client()
            try:
                client.delete_collection(settings.RAG_COLLECTION_NAME)
                logger.info(f"[RAG] Cleared existing collection before re-indexing")
            except Exception:
                pass
            self._collection_ready = False
            self._ensure_hybrid_collection(dim)

            sparse_vectors = self._encode_sparse(state["chunks"])  # may be None
            if sparse_vectors is None:
                logger.info("[RAG] Indexing dense-only (BM25 unavailable)")
            else:
                logger.info("[RAG] Indexing with dense + sparse vectors")

            points = []
            metadata = state["metadata"]
            for i, (chunk, dense) in enumerate(zip(state["chunks"], state["embeddings"])):
                vector_payload: dict = {DENSE_NAME: dense}
                if sparse_vectors is not None:
                    idx, vals = sparse_vectors[i]
                    if idx:  # skip empty sparse vectors (Qdrant rejects them)
                        vector_payload[SPARSE_NAME] = SparseVector(indices=idx, values=vals)
                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector_payload,
                    payload={
                        "text": chunk,
                        "chunk_index": i,
                        "metadata": metadata,
                    },
                ))

            # Batch upsert keeps memory bounded for large documents.
            client = self._get_qdrant_client()
            BATCH = 256
            for start in range(0, len(points), BATCH):
                client.upsert(
                    collection_name=settings.RAG_COLLECTION_NAME,
                    points=points[start:start + BATCH],
                    wait=True,
                )
            logger.info(f"[RAG] Indexed {len(points)} points into '{settings.RAG_COLLECTION_NAME}'")

            return {
                **state,
                "indexed": True,
                "collection_name": settings.RAG_COLLECTION_NAME,
                "stage": "indexed",
            }
        except Exception as e:
            logger.error(f"[RAG] Qdrant indexing failed: {e}", exc_info=True)
            return {**state, "error": str(e), "stage": "failed"}

    def index_document(self, file_path: str) -> Dict[str, Any]:
        """🟢 BEGINNER: Run the full indexing LangGraph end-to-end."""
        initial_state: RAGState = {
            "file_path": file_path,
            "query": None,
            "raw_text": "",
            "chunks": [],
            "metadata": {},
            "embeddings": [],
            "indexed": False,
            "collection_name": settings.RAG_COLLECTION_NAME,
            "retrieved_nodes": [],
            "reranked_nodes": [],
            "context_str": "",
            "response": "",
            "sources": [],
            "error": None,
            "stage": "starting",
        }
        return self.graph.invoke(initial_state)

    # ── Hybrid retrieval ─────────────────────────────────────────────────

    def _hybrid_retrieve(self, state: RAGState) -> RAGState:
        """Hybrid search via Qdrant's server-side Reciprocal Rank Fusion.

        🟢 BEGINNER: We send ONE request with two ``Prefetch`` blocks (dense +
        sparse). Qdrant runs them in parallel internally, then fuses the
        ranked lists with RRF and returns the top ``RAG_PREFETCH_LIMIT``
        candidates.

        If sparse encoding isn't available (e.g. fastembed missing), we
        gracefully fall back to dense-only search using ``query_points``.
        """
        try:
            from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector

            client = self._get_qdrant_client()
            collection = settings.RAG_COLLECTION_NAME
            query = state["query"] or ""

            # Defensive: confirm the collection exists AND has the hybrid layout.
            existing = {c.name for c in client.get_collections().collections}
            if collection not in existing:
                return {
                    **state,
                    "retrieved_nodes": [],
                    "error": "No documents indexed yet. Please initialise RAG on the Upload page first.",
                    "stage": "failed",
                }
            try:
                info = client.get_collection(collection)
                vec_cfg = info.config.params.vectors
                is_named_dense = isinstance(vec_cfg, dict) and DENSE_NAME in vec_cfg
                if not is_named_dense:
                    # 🟢 BEGINNER: Legacy schema from before the hybrid rewrite.
                    # We don't auto-recreate during a query (that would delete
                    # the user's index!) — just ask them to re-initialise.
                    return {
                        **state,
                        "retrieved_nodes": [],
                        "error": (
                            "Your indexed document was created before hybrid search was enabled. "
                            "Please go back to the Upload page and click 'Initialize RAG' again to re-index."
                        ),
                        "stage": "failed",
                    }
            except Exception as inspect_err:
                logger.warning(f"[RAG] Collection inspect failed: {inspect_err}")

            # 1. Dense query embedding (BGE-M3)
            dense_model = self._get_embedding_model()
            dense_vec = dense_model.encode([query])[0]
            dense_list = dense_vec.tolist() if hasattr(dense_vec, "tolist") else list(dense_vec)

            # 2. Sparse query encoding (BM25). May be None if fastembed missing.
            sparse_pair = None
            sparse_pairs = self._encode_sparse([query])
            if sparse_pairs:
                indices, values = sparse_pairs[0]
                if indices:
                    sparse_pair = SparseVector(indices=indices, values=values)

            prefetch_limit = settings.RAG_PREFETCH_LIMIT
            top_n = max(prefetch_limit, settings.RAG_TOP_K * 5)

            # 3. Run hybrid (or dense-only) search in a single round-trip.
            if sparse_pair is not None:
                results = client.query_points(
                    collection_name=collection,
                    prefetch=[
                        Prefetch(query=dense_list, using=DENSE_NAME, limit=prefetch_limit),
                        Prefetch(query=sparse_pair, using=SPARSE_NAME, limit=prefetch_limit),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=top_n,
                    with_payload=True,
                ).points
                fusion_kind = "hybrid_rrf"
            else:
                results = client.query_points(
                    collection_name=collection,
                    query=dense_list,
                    using=DENSE_NAME,
                    limit=top_n,
                    with_payload=True,
                ).points
                fusion_kind = "dense_only"

            retrieved = [
                {
                    "text": (hit.payload or {}).get("text", ""),
                    "score": float(hit.score) if hit.score is not None else 0.0,
                    "metadata": (hit.payload or {}).get("metadata", {}),
                }
                for hit in results
            ]
            logger.info(f"[RAG] Retrieved {len(retrieved)} candidates ({fusion_kind})")

            return {**state, "retrieved_nodes": retrieved, "stage": "retrieved"}
        except Exception as e:
            logger.error(f"[RAG] Retrieval failed: {e}", exc_info=True)
            return {**state, "error": str(e), "stage": "failed"}

    def _rerank_nodes(self, state: RAGState) -> RAGState:
        """Optional cross-encoder rerank to top-K.
        Auto-skipped when corpus is small (<500 chunks) — RRF fusion is accurate enough.
        Skipped if reranker disabled in config or no candidates."""
        retrieved = state.get("retrieved_nodes", [])
        if not retrieved:
            return {**state, "reranked_nodes": [], "stage": "reranked"}

        # Auto-disable reranker for small corpora — saves 200ms per query
        corpus_small = len(retrieved) <= settings.RAG_TOP_K * 3
        if not settings.RAG_USE_RERANKER or corpus_small:
            logger.info(f"[RAG] Skipping reranker (corpus_small={corpus_small}, use_reranker={settings.RAG_USE_RERANKER})")
            return {
                **state,
                "reranked_nodes": retrieved[:settings.RAG_TOP_K],
                "stage": "reranked",
            }
        try:
            reranker = self._get_reranker()
            pairs = [[state["query"], n["text"]] for n in retrieved]
            scores = reranker.predict(pairs)
            scored = sorted(zip(retrieved, scores), key=lambda x: float(x[1]), reverse=True)
            top_k = settings.RAG_TOP_K
            reranked = [n for n, _ in scored[:top_k]]
            logger.info(f"[RAG] Reranked {len(retrieved)} → {len(reranked)} candidates")
            return {**state, "reranked_nodes": reranked, "stage": "reranked"}
        except Exception as e:
            logger.error(f"[RAG] Reranking failed: {e}", exc_info=True)
            return {
                **state,
                "reranked_nodes": retrieved[:settings.RAG_TOP_K],
                "stage": "reranked",
            }

    # ── Generation ──────────────────────────────────────────────────────

    def _build_prompt(self, state: RAGState) -> Tuple[str, str]:
        """🟢 BEGINNER: Build the prompt and the citation context block."""
        context_str = "\n\n".join(
            f"[{i + 1}] {n['text']}" for i, n in enumerate(state["reranked_nodes"])
        )
        prompt = f"""You are a helpful assistant answering questions based on the provided document context.

CONTEXT:
{context_str}

QUESTION: {state["query"]}

Answer the question using only the provided context. If the answer is not in the context, say "I don't have enough information to answer this question." Cite sources inline like [1], [2] when possible.
"""
        return prompt, context_str

    def _generate_response(self, state: RAGState) -> RAGState:
        """Deprecated: kept for compatibility. Returns retrieval-only response."""
        try:
            chunks = state.get("reranked_nodes", [])
            if not chunks:
                return {**state, "response": "No relevant content found.", "stage": "completed"}
            response = "\n\n".join(
                f"[{i+1}] {n['text']}" for i, n in enumerate(chunks)
            )
            return {
                **state,
                "context_str": response,
                "response": response,
                "sources": chunks,
                "stage": "completed",
            }
        except Exception as e:
            logger.error(f"[RAG] Response failed: {e}", exc_info=True)
            return {**state, "error": str(e), "stage": "failed"}

    def chat(self, query: str, stream: bool = True) -> Generator[str, None, None]:
        """Backwards-compatible streaming wrapper around query()."""
        result = self.query(query)
        if "error" in result:
            yield result["error"]
            return
        # Stream a JSON event so the frontend can parse it as structured data
        import json as _json
        yield _json.dumps(result)

    def query(self, query: str) -> Dict[str, Any]:
        """Pure retrieval RAG — returns structured response with smart snippets,
        highlighted terms, and section hints. No LLM = instant + zero cost."""
        initial_state: RAGState = {
            "file_path": "",
            "query": query,
            "raw_text": "",
            "chunks": [],
            "metadata": {},
            "embeddings": [],
            "indexed": True,
            "collection_name": settings.RAG_COLLECTION_NAME,
            "retrieved_nodes": [],
            "reranked_nodes": [],
            "context_str": "",
            "response": "",
            "sources": [],
            "error": None,
            "stage": "starting",
        }

        state = self._hybrid_retrieve(initial_state)
        if state.get("error"):
            return {"error": state["error"], "sources": []}

        if not state.get("retrieved_nodes"):
            return {
                "error": None,
                "filename": "",
                "total": 0,
                "sources": [],
                "summary": "No relevant content found in the indexed document for that question. Try rephrasing or asking about a different topic.",
            }

        state = self._rerank_nodes(state)
        chunks = state.get("reranked_nodes", [])

        filename = ""
        if chunks and chunks[0].get("metadata"):
            filename = chunks[0]["metadata"].get("filename", "Document")

        # Extract meaningful query terms (filter out stop words)
        query_terms = self._extract_query_terms(query)

        sources = []
        all_snippets = []
        for i, chunk in enumerate(chunks, 1):
            text = (chunk.get("text") or "").strip()
            if not text:
                continue

            # Smart snippet: extract the sentence(s) most relevant to the query
            snippet = self._extract_smart_snippet(text, query_terms, max_chars=350)
            section = self._detect_section_hint(text)
            score = chunk.get("score", 0.0)
            # Normalize score to a sensible percentage
            if score >= 1:
                score_pct = min(99, int(score))
            elif score > 0:
                score_pct = min(99, max(5, int(score * 100)))
            else:
                score_pct = 0

            matched_terms = [t for t in query_terms if t.lower() in text.lower()]

            sources.append({
                "id": i,
                "text": text[:2500],
                "snippet": snippet,
                "section": section,
                "score": float(score),
                "score_pct": score_pct,
                "chunk_index": chunk.get("metadata", {}).get("chunk_index"),
                "matched_terms": matched_terms,
                "match_count": len(matched_terms),
            })
            all_snippets.append(snippet)

        # Build a synthesized direct answer from the top chunks using Haiku
        haiku_answer = self._synthesize_with_haiku(query, sources[:5])

        return {
            "error": None,
            "query": query,
            "query_terms": query_terms,
            "filename": filename,
            "total": len(sources),
            "sources": sources,
            "summary": haiku_answer or self._build_summary(query, sources[:3]),
            "haiku_used": bool(haiku_answer),
        }

    @staticmethod
    def _extract_query_terms(query: str) -> List[str]:
        """Extract meaningful terms from a query, filtering out common stop words."""
        import re as _re
        STOP = {
            "what","is","are","was","were","the","a","an","of","in","on","at","to",
            "for","with","by","from","this","that","these","those","my","your","his",
            "her","i","you","we","they","it","be","been","being","have","has","had",
            "do","does","did","will","would","should","could","can","may","might",
            "and","or","but","if","then","so","as","not","no","yes","tell","me",
            "about","which","who","whom","when","where","why","how","explain",
            "list","all","any","some","section","sections","there","here","mentioned",
            "show","find","give","please",
        }
        # Tokenize: keep words and meaningful punctuation
        words = _re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", query.lower())
        seen = set()
        terms = []
        for w in words:
            if len(w) < 2 or w in STOP:
                continue
            if w not in seen:
                seen.add(w)
                terms.append(w)
        return terms[:10]

    @staticmethod
    def _extract_smart_snippet(text: str, query_terms: List[str], max_chars: int = 350) -> str:
        """Return the most query-relevant snippet from a chunk.
        Splits text into sentences, scores each by query-term hits, returns the best window."""
        import re as _re
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+|\n\n+", text) if s.strip()]
        if not sentences:
            return text[:max_chars]
        if not query_terms:
            return (text[:max_chars] + "...") if len(text) > max_chars else text

        # Score each sentence by number of query-term hits
        best_idx = 0
        best_score = -1
        for i, sent in enumerate(sentences):
            sent_lower = sent.lower()
            score = sum(1 for t in query_terms if t in sent_lower)
            if score > best_score:
                best_score = score
                best_idx = i

        # Build snippet around the best sentence (include neighbors for context)
        snippet_parts = []
        if best_idx > 0:
            snippet_parts.append(sentences[best_idx - 1])
        snippet_parts.append(sentences[best_idx])
        if best_idx + 1 < len(sentences):
            snippet_parts.append(sentences[best_idx + 1])

        snippet = " ".join(snippet_parts)
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "..."
        return snippet

    @staticmethod
    def _detect_section_hint(text: str) -> Optional[str]:
        """Try to detect which section/header the chunk belongs to by looking for
        markdown headers, numbered sections, or all-caps lines at the start."""
        import re as _re
        lines = text.split("\n")
        for line in lines[:8]:
            line = line.strip()
            if not line:
                continue
            # Markdown header
            md_match = _re.match(r"^#{1,4}\s+(.+)", line)
            if md_match:
                return md_match.group(1).strip()[:80]
            # Numbered section: "1. Executive Summary", "4.2 IAM Security"
            num_match = _re.match(r"^(\d+\.[\d.]*)\s+([A-Z][^\n]{2,80})", line)
            if num_match:
                return f"§ {num_match.group(1)} {num_match.group(2).strip()}"[:80]
            # All-caps short line (likely a header)
            if 3 <= len(line) <= 60 and line.isupper() and any(c.isalpha() for c in line):
                return line[:80]
        return None

    @staticmethod
    def _build_summary(query: str, top_sources: List[dict]) -> str:
        """Synthesize a direct answer by stitching together the most relevant snippets.
        Pure rule-based — no LLM call. Used as fallback when Haiku is unavailable."""
        if not top_sources:
            return ""
        # Collect unique snippets, deduplicated
        seen = set()
        parts = []
        for src in top_sources:
            snip = src.get("snippet", "").strip()
            if not snip:
                continue
            # Dedup near-duplicates by first 60 chars
            key = snip[:60].lower()
            if key in seen:
                continue
            seen.add(key)
            parts.append(snip)
            if len(parts) >= 3:
                break
        # Cap total summary length
        summary = " ".join(parts)
        if len(summary) > 800:
            summary = summary[:800].rsplit(" ", 1)[0] + "..."
        return summary

    def _synthesize_with_haiku(self, query: str, sources: List[dict]) -> Optional[str]:
        """Use Haiku to synthesize a grounded, accurate answer from the top retrieved chunks.

        Strategy:
        - Only sends top-5 chunks (~4000 chars) to Haiku — minimal token cost
        - Strict grounding prompt: answer ONLY from the provided context
        - Asks Haiku to cite sources inline [1], [2], etc.
        - Routes through LLM Gateway for semantic caching (similar questions = instant)
        - Falls back to None if Haiku fails (caller uses rule-based summary)
        """
        if not sources:
            return None

        # Build numbered context block from top sources
        context_parts = []
        for src in sources[:5]:
            text = (src.get("text") or "").strip()
            if not text:
                continue
            # Truncate each chunk to keep total context under 4000 chars
            if len(text) > 800:
                text = text[:800].rsplit(" ", 1)[0] + "..."
            section = src.get("section") or f"Section {src.get('id', '?')}"
            context_parts.append(f"[{src['id']}] {section}:\n{text}")

        if not context_parts:
            return None

        context_block = "\n\n".join(context_parts)
        total_chars = len(context_block)

        prompt = f"""You are a precise document assistant. Answer the user's question using ONLY the provided document excerpts below.

RULES:
- Answer directly and concisely (2-5 sentences max)
- Cite sources inline using [1], [2], etc. when referencing specific content
- If the answer is not in the excerpts, say "This information is not found in the provided document sections."
- Do NOT add information from outside the excerpts
- Do NOT repeat the question

DOCUMENT EXCERPTS:
{context_block}

QUESTION: {query}

ANSWER:"""

        try:
            # Route through LLM Gateway for caching + circuit breaking.
            # Similar questions hitting the same chunks will get a cache hit (0ms, $0).
            from app.core.llm_gateway import get_gateway
            response = get_gateway().call(
                messages=[{"role": "user", "content": prompt}],
                task_type="rag_synthesis",
                max_tokens=400,
                context=context_block[:500],  # Cache key includes chunk content
            )
            answer = response.strip()
            logger.info(f"[RAG] Haiku synthesized answer | chars={len(answer)} | context_chars={total_chars}")
            return answer
        except Exception as e:
            logger.warning(f"[RAG] Haiku synthesis failed, using rule-based fallback: {e}")
            return None
