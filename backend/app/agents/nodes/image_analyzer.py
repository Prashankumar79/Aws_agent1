"""
================================================================================
  backend/app/agents/nodes/image_analyzer.py  —  IMAGE ANALYSIS AGENT
================================================================================

PURPOSE:
  Wraps the existing VisionService to analyze architecture diagrams / images.
  Processes the main uploaded file (if it's an image) PLUS any embedded images
  extracted from PDF/DOCX documents.

OUTPUT:
  Updates state with:
    - image_analysis: {components, connections, boundaries, metadata, raw_response}
    - file_type: "image" (if the main file is an image)
================================================================================
"""
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".drawio", ".pdf"}


def analyze_image(state: PipelineState) -> PipelineState:
    """LangGraph node: analyze the uploaded image or embedded images."""
    file_path = state["file_path"]
    job_id = state["job_id"]
    file_type = state.get("file_type", "")
    embedded_images = state.get("embedded_images", [])

    logger.info(f"🚀 [AGENT:ImageAnalyzer] STARTED  | job_id={job_id} | file_type={file_type} | images_to_check={len(embedded_images)+1}")
    logger.info(f"[PIPELINE][analyze_image][{job_id}] ENTER | file_type={file_type}, main_image={file_path}, embedded={len(embedded_images)}")
    logger.info(f"[ImageAnalyzer:{job_id}] Starting image analysis")

    # Determine which images to analyze
    images_to_analyze = []

    # If the main file is an image, add it
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS or file_type == "image":
        images_to_analyze.append(file_path)

    # Add any embedded images from PDF/DOCX
    for img_path in embedded_images:
        if Path(img_path).suffix.lower() in IMAGE_EXTENSIONS:
            images_to_analyze.append(img_path)

    if not images_to_analyze:
        logger.info(f"[ImageAnalyzer:{job_id}] No images to analyze")
        return {
            **state,
            "image_analysis": {},
            "pipeline_stage": "NO_IMAGES",
        }

    # Use the existing VisionService
    from app.services.vision_service import VisionService
    vision = VisionService()

    all_components = []
    all_connections = []
    all_boundaries = []
    all_metadata = {"regions": [], "environments": [], "cidrs": []}
    all_data_flows = []
    all_security_groups = []
    all_unresolved = []

    for img_path in images_to_analyze:
        try:
            result = vision.analyze_diagram(img_path)
            if result.get("success"):
                analysis = result.get("analysis", {})
                all_components.extend(analysis.get("components", []))
                all_connections.extend(analysis.get("connections", []))
                all_boundaries.extend(analysis.get("boundaries", []))
                all_data_flows.extend(analysis.get("data_flows", []))
                all_security_groups.extend(analysis.get("security_groups", []))
                all_unresolved.extend(analysis.get("unresolved", []))
                meta = analysis.get("metadata", {})
                all_metadata["regions"].extend(meta.get("regions", []))
                all_metadata["environments"].extend(meta.get("environments", []))
                all_metadata["cidrs"].extend(meta.get("cidrs", []))
            else:
                logger.warning(f"[ImageAnalyzer:{job_id}] Vision failed for {img_path}: {result.get('error')}")
        except Exception as e:
            logger.error(f"[ImageAnalyzer:{job_id}] Error analyzing {img_path}: {e}")

    # Smart deduplication: merge properties from duplicate components
    merged_components = _merge_component_properties(all_components)

    # Smart deduplication: merge properties from duplicate connections
    merged_connections = _merge_connection_properties(all_connections)

    # Deduplicate data_flows by path
    seen_flows = set()
    deduped_flows = []
    for flow in all_data_flows:
        path = flow.get("path", "")
        if path and path not in seen_flows:
            seen_flows.add(path)
            deduped_flows.append(flow)

    image_analysis = {
        "components": merged_components,
        "connections": merged_connections,
        "boundaries": all_boundaries,
        "data_flows": deduped_flows,
        "security_groups": all_security_groups,
        "unresolved": all_unresolved,
        "metadata": {
            "regions": list(dict.fromkeys(all_metadata["regions"])),
            "environments": list(dict.fromkeys(all_metadata["environments"])),
            "cidrs": list(dict.fromkeys(all_metadata["cidrs"])),
        },
        "image_count": len(images_to_analyze),
    }

    # Convert to graph format for downstream compatibility
    graph = _analysis_to_graph(image_analysis)

    logger.info(f"[ImageAnalyzer:{job_id}] Found {len(merged_components)} components, {len(merged_connections)} connections, {len(deduped_flows)} data flows, {len(all_security_groups)} security groups")

    result = {
        **state,
        "image_analysis": image_analysis,
        "graph_json": json.dumps(graph),
        "pipeline_stage": "IMAGE_ANALYZED",
    }
    logger.info(f"[PIPELINE][analyze_image][{job_id}] EXIT  | components={len(merged_components)}, connections={len(merged_connections)}")
    logger.info(f"✅ [AGENT:ImageAnalyzer] COMPLETED | job_id={job_id} | components={len(merged_components)} | connections={len(merged_connections)} | graph_nodes={len(graph.get('nodes', []))}")
    return result


def _merge_component_properties(components: list) -> list:
    """Merge duplicate components, combining their properties."""
    merged = {}
    for comp in components:
        name = comp.get("name", "").strip().lower()
        if not name:
            continue
        if name not in merged:
            merged[name] = dict(comp)
            continue
        # Merge: higher confidence wins; combine labels and refs
        existing = merged[name]
        if comp.get("confidence", 0) > existing.get("confidence", 0):
            # Keep the higher-confidence version but merge lists
            new_comp = dict(comp)
            for key in ["labels", "ports", "security_group_refs", "iam_role_refs"]:
                old_vals = set(existing.get(key, []))
                new_vals = set(comp.get(key, []))
                new_comp[key] = list(old_vals | new_vals)
            merged[name] = new_comp
        else:
            # Keep existing, but merge lists from new comp
            for key in ["labels", "ports", "security_group_refs", "iam_role_refs"]:
                old_vals = set(existing.get(key, []))
                new_vals = set(comp.get(key, []))
                existing[key] = list(old_vals | new_vals)
    return list(merged.values())


def _merge_connection_properties(connections: list) -> list:
    """Merge duplicate connections, keeping the one with highest confidence."""
    merged = {}
    for conn in connections:
        key = (
            conn.get("source", "").lower(),
            conn.get("target", "").lower(),
            conn.get("protocol", "TCP"),
            str(conn.get("port", 0)),
        )
        if key not in merged:
            merged[key] = dict(conn)
        elif conn.get("confidence", 0) > merged[key].get("confidence", 0):
            merged[key] = dict(conn)
    return list(merged.values())


def _analysis_to_graph(analysis: dict) -> dict:
    """Convert vision analysis into the graph format expected by downstream services.

    Now produces rich GraphNode-compatible dicts with configuration, security,
    tier, and metadata properties for the DrawIO converter and design doc pipeline.
    """
    nodes = []
    edges = []

    for comp in analysis.get("components", []):
        node = {
            "id": comp.get("name", "unnamed"),
            "label": comp.get("display_name", comp.get("name", "unnamed")),
            "service_type": comp.get("type", "Other"),
            "type": comp.get("type", "Other"),
            "cloud_provider": comp.get("provider", "aws"),
            "confidence": comp.get("confidence", 0.7),
            "confidence_rationale": comp.get("confidence_rationale", ""),
            "tier": comp.get("tier", "production"),
            "configuration": comp.get("configuration", {}),
            "labels": comp.get("labels", []),
            "ports": comp.get("ports", []),
            "security_group_refs": comp.get("security_group_refs", []),
            "iam_role_refs": comp.get("iam_role_refs", []),
            "source": "vision_analysis",
        }
        nodes.append(node)

    for conn in analysis.get("connections", []):
        edge = {
            "source": conn.get("source", ""),
            "target": conn.get("target", ""),
            "connection_type": conn.get("type", "CONNECTS_TO"),
            "protocol": conn.get("protocol", "TCP"),
            "port": conn.get("port", 0),
            "direction": conn.get("direction", "forward"),
            "confidence": conn.get("confidence", 0.7),
            "rationale": conn.get("rationale", ""),
            "inferred": False,
        }
        edges.append(edge)

    # Add data_flows as metadata for downstream use
    graph = {
        "nodes": nodes,
        "edges": edges,
        "data_flows": analysis.get("data_flows", []),
        "security_groups": analysis.get("security_groups", []),
        "unresolved": analysis.get("unresolved", []),
    }
    return graph
