"""
================================================================================
  backend/app/models/infra_graph.py  —  CANONICAL INFRASTRUCTURE GRAPH MODEL
================================================================================

PURPOSE:
  Canonical graph format for infrastructure architecture.
  This is the SOURCE OF TRUTH for all conversions (to draw.io XML, Terraform, etc.).

WHY CANONICAL GRAPH:
  - AI-friendly: Easy for LLMs to understand and manipulate
  - Terraform-friendly: Direct mapping to resources
  - Queryable: Easy to find components, connections
  - Scalable: Can represent complex architectures
  - Version-controllable: JSON format

CONNECTIONS TO OTHER FILES:
  • services/architecture_extractor.py → Outputs this format
  • services/drawio_converter.py → Converts to/from XML
  • services/terraform_generator.py → Generates code from this

IMPORTANT:
  This JSON graph is the source of truth.
  draw.io XML is ONLY for editor representation.
================================================================================
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class CloudProvider(str, Enum):
    """Supported cloud providers."""
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class GraphNode(BaseModel):
    """Represents a single infrastructure component (node) in the graph."""
    
    id: str = Field(..., description="Unique node identifier")
    provider: CloudProvider = Field(..., description="Cloud provider")
    service: str = Field(..., description="Service type (e.g., eks, rds, vpc)")
    label: str = Field(..., description="Display label for the node")
    
    # Optional properties
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional service properties")
    position: Optional[Dict[str, float]] = Field(default=None, description="Position in diagram {x, y}")
    icon: Optional[str] = Field(default=None, description="Icon identifier for draw.io")


class GraphEdge(BaseModel):
    """Represents a connection between two infrastructure components."""
    
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relationship: str = Field(default="connects", description="Type of relationship")
    
    # Optional properties
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional edge properties")


class InfraGraph(BaseModel):
    """Canonical infrastructure graph - the source of truth for all conversions."""
    
    nodes: List[GraphNode] = Field(default_factory=list, description="All infrastructure components")
    edges: List[GraphEdge] = Field(default_factory=list, description="All connections between components")
    
    # Metadata
    provider: CloudProvider = Field(..., description="Primary cloud provider")
    source_file: Optional[str] = Field(default=None, description="Original uploaded file")
    extraction_method: Optional[str] = Field(default=None, description="How graph was extracted (docling, vision, etc.)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {
                        "id": "vpc-main",
                        "provider": "aws",
                        "service": "vpc",
                        "label": "Main VPC",
                        "properties": {
                            "cidr": "10.0.0.0/16"
                        }
                    },
                    {
                        "id": "eks-cluster",
                        "provider": "aws",
                        "service": "eks",
                        "label": "EKS Cluster",
                        "properties": {
                            "version": "1.27",
                            "node_count": 3
                        }
                    }
                ],
                "edges": [
                    {
                        "source": "eks-cluster",
                        "target": "vpc-main",
                        "relationship": "deployed_in"
                    }
                ],
                "provider": "aws",
                "extraction_method": "docling+vision"
            }
        }
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes.append(node)
    
    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
    
    def remove_node(self, node_id: str) -> None:
        """Remove a node and its edges."""
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()
