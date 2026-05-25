"""
================================================================================
  backend/app/agents/nodes/context_fusion.py  —  CONTEXT FUSION AGENT
================================================================================

PURPOSE:
  Merge all inputs into a single authoritative context pack:
    - Document text (from parse_document)
    - Image analysis (from analyze_image)
    - User prompt requirements (from analyze_prompt)

  Deduplicates components, resolves naming conventions, and produces
  the fused_context dict that downstream agents consume.

OUTPUT:
  Updates state with:
    - fused_context: {cloud_provider, components, connections, requirements, raw_text, ...}
    - graph_json: canonical graph for design doc streaming (always present)
================================================================================
"""
import json
import logging
from typing import Any

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)


def fuse_context(state: PipelineState) -> PipelineState:
    """LangGraph node: merge document text, image analysis, and user requirements."""
    job_id = state["job_id"]
    raw_text = state.get("raw_text", "")
    image_analysis = state.get("image_analysis", {})
    requirements = state.get("structured_requirements", {})
    user_prompt = state.get("user_prompt", "")  # Raw user prompt

    logger.info(f"🚀 [AGENT:ContextFusion] STARTED  | job_id={job_id} | text={len(raw_text)}c | img_comps={len(image_analysis.get('components', []))} | reqs={len(requirements)} | prompt_len={len(user_prompt)}")
    logger.info(f"[PIPELINE][fuse_context][{job_id}] ENTER | text={len(raw_text)}c, img_comps={len(image_analysis.get('components', []))}, req_keys={list(requirements.keys())}, prompt_len={len(user_prompt)}")
    logger.info(f"[ContextFusion:{job_id}] Fusing inputs: text={len(raw_text)} chars, images={len(image_analysis.get('components', []))} comps, reqs={len(requirements)} keys, user_prompt={len(user_prompt)} chars")

    # Determine cloud provider — frontend selection takes highest priority
    target_clouds = state.get("target_clouds", [])
    cloud_provider = _resolve_cloud_provider(image_analysis, requirements, raw_text, target_clouds)

    # Merge components (image vision takes priority for structure, text for naming)
    components = _merge_components(image_analysis.get("components", []), raw_text, cloud_provider)

    # Merge connections
    connections = image_analysis.get("connections", [])

    # Build boundaries from image analysis + text
    boundaries = image_analysis.get("boundaries", [])

    # Extract metadata
    metadata = image_analysis.get("metadata", {})

    # Apply naming convention from requirements
    naming_pattern = requirements.get("naming_convention", {}).get("pattern", "{env}-{app}-{resource}")
    naming_separator = requirements.get("naming_convention", {}).get("separator", "-")

    # Extract governance / compliance / security signals
    compliance_frameworks = metadata.get("compliance_frameworks", [])
    if not compliance_frameworks and raw_text:
        # Keyword-based compliance detection
        text_lower = raw_text.lower()
        if any(k in text_lower for k in ["pci-dss", "pci dss", "payment card"]):
            compliance_frameworks.append("PCI-DSS")
        if any(k in text_lower for k in ["hipaa", "phi", "health insurance"]):
            compliance_frameworks.append("HIPAA")
        if any(k in text_lower for k in ["gdpr", "general data protection"]):
            compliance_frameworks.append("GDPR")
        if any(k in text_lower for k in ["soc2", "soc 2", "service organization"]):
            compliance_frameworks.append("SOC2")
        if any(k in text_lower for k in ["fedramp", "federal risk"]):
            compliance_frameworks.append("FedRAMP")
        if any(k in text_lower for k in ["iso27001", "iso 27001"]):
            compliance_frameworks.append("ISO27001")

    data_flows = image_analysis.get("data_flows", [])
    security_groups = image_analysis.get("security_groups", [])
    unresolved = image_analysis.get("unresolved", [])

    # Build governance block
    governance = {
        "rules": [],
        "security_requirements": [],
        "compliance_frameworks": compliance_frameworks,
    }
    if compliance_frameworks:
        governance["security_requirements"].append(f"Must satisfy {', '.join(compliance_frameworks)} controls")
    if security_groups:
        governance["rules"].append(f"Network segmentation enforced via {len(security_groups)} security groups")
    if data_flows:
        high_crit = [f for f in data_flows if f.get("criticality") == "high"]
        if high_crit:
            governance["security_requirements"].append(f"{len(high_crit)} high-criticality data paths require encryption-in-transit + encryption-at-rest")

    fused_context = {
        "cloud_provider": cloud_provider,
        "components": components,
        "connections": connections,
        "boundaries": boundaries,
        "data_flows": data_flows,
        "security_groups": security_groups,
        "unresolved": unresolved,
        "metadata": metadata,
        "requirements": requirements,
        "governance": governance,
        "raw_document_text": raw_text,
        "user_prompt": user_prompt,
        "naming_convention": {
            "pattern": naming_pattern,
            "separator": naming_separator,
        },
        "component_count": len(components),
        "connection_count": len(connections),
        "data_flow_count": len(data_flows),
        "security_group_count": len(security_groups),
    }

    logger.info(f"[ContextFusion:{job_id}] Fused context: cloud={cloud_provider}, {len(components)} components, {len(connections)} connections, user_prompt_len={len(user_prompt)}")

    # Build graph_json from fused context if image analysis didn't produce one
    # (e.g., text-only documents with no images to analyze)
    graph_json = state.get("graph_json")
    if not graph_json and components:
        graph = _fused_context_to_graph(fused_context)
        graph_json = json.dumps(graph)
        logger.info(f"[ContextFusion:{job_id}] Generated graph_json from fused context: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    result = {
        **state,
        "fused_context": fused_context,
        "graph_json": graph_json,
        "pipeline_stage": "CONTEXT_FUSED",
    }
    logger.info(f"[PIPELINE][fuse_context][{job_id}] EXIT  | cloud={cloud_provider}, comps={len(components)}, conns={len(connections)}")
    logger.info(f"✅ [AGENT:ContextFusion] COMPLETED | job_id={job_id} | cloud={cloud_provider} | comps={len(components)} | conns={len(connections)}")
    return result


def _fused_context_to_graph(fused_context: dict) -> dict:
    """Convert fused context components/connections into canonical graph format.

    Now produces rich graph dicts with governance, security, and data flow metadata
    for downstream DrawIO conversion and design doc generation.
    """
    nodes = []
    edges = []

    for comp in fused_context.get("components", []):
        node = {
            "id": comp.get("name", "unnamed"),
            "label": comp.get("display_name", comp.get("name", "unnamed")),
            "service_type": comp.get("type", "Other"),
            "type": comp.get("type", "Other"),
            "cloud_provider": fused_context.get("cloud_provider", "aws"),
            "confidence": comp.get("confidence", 0.7),
            "confidence_rationale": comp.get("confidence_rationale", ""),
            "tier": comp.get("tier", "production"),
            "configuration": comp.get("configuration", {}),
            "labels": comp.get("labels", []),
            "ports": comp.get("ports", []),
            "security_group_refs": comp.get("security_group_refs", []),
            "iam_role_refs": comp.get("iam_role_refs", []),
            "source": comp.get("source", "fused"),
        }
        nodes.append(node)

    for conn in fused_context.get("connections", []):
        edge = {
            "source": conn.get("source", ""),
            "target": conn.get("target", ""),
            "connection_type": conn.get("type", "CONNECTS_TO"),
            "protocol": conn.get("protocol", "TCP"),
            "port": conn.get("port", 0),
            "direction": conn.get("direction", "forward"),
            "confidence": conn.get("confidence", 0.7),
            "rationale": conn.get("rationale", ""),
            "inferred": conn.get("inferred", False),
        }
        edges.append(edge)

    return {
        "nodes": nodes,
        "edges": edges,
        "data_flows": fused_context.get("data_flows", []),
        "security_groups": fused_context.get("security_groups", []),
        "governance": fused_context.get("governance", {}),
        "unresolved": fused_context.get("unresolved", []),
        "metadata": {
            "cloud_provider": fused_context.get("cloud_provider", "aws"),
            "compliance_frameworks": fused_context.get("governance", {}).get("compliance_frameworks", []),
            "component_count": fused_context.get("component_count", 0),
            "connection_count": fused_context.get("connection_count", 0),
        },
    }


def _resolve_cloud_provider(image_analysis: dict, requirements: dict, raw_text: str, target_clouds: list[str] | None = None) -> str:
    """Determine cloud provider from frontend selection > requirements > image analysis > text > default."""
    # Priority 0: frontend UI selection (highest — user explicitly clicked a provider card)
    if target_clouds and len(target_clouds) > 0:
        cloud = target_clouds[0].strip().lower()
        if cloud:
            logger.info(f"[ContextFusion] Using frontend-selected cloud: {cloud}")
            return cloud

    # Priority 1: user prompt explicitly specified
    req_cloud = requirements.get("cloud_provider", "auto-detect")
    if req_cloud and req_cloud != "auto-detect":
        return req_cloud.lower()

    # Priority 2: image analysis detected providers
    providers = image_analysis.get("cloud_providers", [])
    if providers:
        # Pick the one with highest confidence
        best = max(providers, key=lambda p: p.get("confidence", 0))
        return best.get("provider", "aws").lower()

    # Priority 3: keyword search in raw text
    text_lower = raw_text.lower()
    if "azure" in text_lower or "microsoft" in text_lower:
        return "azure"
    if "gcp" in text_lower or "google cloud" in text_lower:
        return "gcp"
    if "aws" in text_lower or "amazon" in text_lower:
        return "aws"

    # Default
    return "aws"


def _merge_components(vision_components: list[dict], raw_text: str, cloud_provider: str = "aws") -> list[dict]:
    """Merge vision-extracted components with any mentioned in the text."""
    merged = {}
    for comp in vision_components:
        name = comp.get("name", "").strip()
        if name:
            merged[name.lower()] = comp

    # Multi-cloud keyword matching
    aws_services = [
        ("ec2", "EC2", "compute"),
        ("s3", "S3", "storage"),
        ("rds", "RDS", "database"),
        ("lambda", "Lambda", "compute"),
        ("dynamodb", "DynamoDB", "database"),
        ("vpc", "VPC", "networking"),
        ("elb", "ELB", "load_balancing"),
        ("alb", "ALB", "load_balancing"),
        ("cloudfront", "CloudFront", "cdn"),
        ("route 53", "Route53", "dns"),
        ("sns", "SNS", "messaging"),
        ("sqs", "SQS", "messaging"),
        ("ecs", "ECS", "compute"),
        ("eks", "EKS", "compute"),
        ("fargate", "Fargate", "compute"),
        ("api gateway", "APIGateway", "networking"),
        ("cognito", "Cognito", "security"),
        ("secrets manager", "SecretsManager", "security"),
        ("kms", "KMS", "security"),
        ("cloudwatch", "CloudWatch", "monitoring"),
        ("elasticache", "ElastiCache", "database"),
        ("opensearch", "OpenSearch", "database"),
    ]

    azure_services = [
        ("virtual machine", "AzureVM", "compute"),
        ("azure vm", "AzureVM", "compute"),
        ("blob storage", "BlobStorage", "storage"),
        ("azure sql", "AzureSQL", "database"),
        ("cosmos db", "CosmosDB", "database"),
        ("azure functions", "AzureFunctions", "compute"),
        ("app service", "AppService", "compute"),
        ("vnet", "VNet", "networking"),
        ("virtual network", "VNet", "networking"),
        ("azure load balancer", "AzureLB", "load_balancing"),
        ("application gateway", "AppGateway", "load_balancing"),
        ("front door", "FrontDoor", "cdn"),
        ("azure dns", "AzureDNS", "dns"),
        ("service bus", "ServiceBus", "messaging"),
        ("event grid", "EventGrid", "messaging"),
        ("event hub", "EventHub", "messaging"),
        ("aks", "AKS", "compute"),
        ("key vault", "KeyVault", "security"),
        ("azure monitor", "AzureMonitor", "monitoring"),
        ("azure cache", "AzureCache", "database"),
        ("nsg", "NSG", "networking"),
    ]

    gcp_services = [
        ("compute engine", "ComputeEngine", "compute"),
        ("cloud storage", "CloudStorage", "storage"),
        ("cloud sql", "CloudSQL", "database"),
        ("bigquery", "BigQuery", "database"),
        ("cloud functions", "CloudFunctions", "compute"),
        ("cloud run", "CloudRun", "compute"),
        ("gke", "GKE", "compute"),
        ("vpc network", "VPCNetwork", "networking"),
        ("cloud load balancing", "CloudLB", "load_balancing"),
        ("cloud cdn", "CloudCDN", "cdn"),
        ("cloud dns", "CloudDNS", "dns"),
        ("pub/sub", "PubSub", "messaging"),
        ("cloud tasks", "CloudTasks", "messaging"),
        ("cloud kms", "CloudKMS", "security"),
        ("cloud monitoring", "CloudMonitoring", "monitoring"),
        ("memorystore", "Memorystore", "database"),
        ("firestore", "Firestore", "database"),
        ("spanner", "Spanner", "database"),
        ("cloud armor", "CloudArmor", "security"),
    ]

    # Select keyword list based on cloud provider, but always also scan AWS (most common)
    service_lists = [("aws", aws_services)]
    if cloud_provider == "azure":
        service_lists.insert(0, ("azure", azure_services))
    elif cloud_provider == "gcp":
        service_lists.insert(0, ("gcp", gcp_services))

    text_lower = raw_text.lower()
    for provider, services in service_lists:
        for keyword, service_name, service_type in services:
            if keyword in text_lower and service_name.lower() not in merged:
                merged[service_name.lower()] = {
                    "name": service_name,
                    "type": service_type,
                    "provider": provider,
                    "confidence": 0.5,
                    "source": "text_extraction"
                }

    return list(merged.values())
