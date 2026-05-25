"""
================================================================================
  backend/app/services/drawio_converter.py  —  DRAW.IO XML CONVERTER
================================================================================

PURPOSE:
  Convert canonical infrastructure graph to/from draw.io XML format.
  Produces industry-standard, production-ready architecture diagrams with:
  - Tiered layout (Internet → Edge → Compute → Data)
  - VPC / Subnet grouping containers
  - Official AWS4 / Azure / GCP icon stencils
  - Edge labels with protocol and port
  - Professional color scheme and spacing

CONNECTIONS TO OTHER FILES:
  • models/infra_graph.py → Converts InfraGraph to XML and back
  • api/v1/jobs.py → Uses to send XML to frontend

IMPORTANT:
  XML is ONLY for editor display.
  Canonical graph JSON is the source of truth.
================================================================================
"""
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from app.models.infra_graph import InfraGraph, GraphNode, GraphEdge, CloudProvider

logger = logging.getLogger(__name__)

# ── Tier definitions for layout ───────────────────────────────────────────────
# Each node is classified into one of these tiers for vertical positioning
TIER_ORDER = ["internet", "edge", "compute", "data", "security", "monitoring"]

TIER_CLASSIFICATION = {
    # Internet / Edge tier
    "route53": "internet", "dns": "internet", "cloud dns": "internet",
    "cloudfront": "edge", "cdn": "edge", "front door": "edge", "cloud cdn": "edge",
    "waf": "edge", "shield": "edge", "cloud armor": "edge",
    "api_gateway": "edge", "api gateway": "edge", "apigateway": "edge",
    # Networking tier (treated as containers, not standalone tier)
    "vpc": "network_container", "vnet": "network_container",
    "subnet": "network_container",
    # Load Balancing → edge
    "alb": "edge", "nlb": "edge", "elb": "edge",
    "load balancer": "edge", "application gateway": "edge",
    # Compute tier
    "ec2": "compute", "vm": "compute", "compute engine": "compute",
    "eks": "compute", "ecs": "compute", "gke": "compute", "aks": "compute",
    "lambda": "compute", "function app": "compute", "cloud functions": "compute",
    "cloud run": "compute", "fargate": "compute", "app service": "compute",
    "autoscaling": "compute", "auto scaling": "compute",
    "nat_gateway": "compute", "nat gateway": "compute",
    # Data tier
    "rds": "data", "aurora": "data", "sql database": "data", "cloud sql": "data",
    "dynamodb": "data", "cosmos db": "data", "firestore": "data",
    "s3": "data", "blob storage": "data", "cloud storage": "data",
    "elasticache": "data", "redis": "data", "memcached": "data", "memorystore": "data",
    "efs": "data", "opensearch": "data", "bigquery": "data", "spanner": "data",
    # Messaging → compute adjacent
    "sns": "compute", "sqs": "compute", "event grid": "compute",
    "event hub": "compute", "pub/sub": "compute", "service bus": "compute",
    # Security
    "iam": "security", "kms": "security", "secrets_manager": "security",
    "secrets manager": "security", "key vault": "security", "cognito": "security",
    # Monitoring
    "cloudwatch": "monitoring", "monitoring": "monitoring",
    "x-ray": "monitoring", "log analytics": "monitoring",
}

# ── Layout constants ──────────────────────────────────────────────────────────
PAGE_W, PAGE_H = 1400, 1000
MARGIN_X, MARGIN_Y = 60, 80
NODE_W, NODE_H = 120, 70
H_GAP, V_GAP = 60, 100
VPC_PAD = 30
TITLE_H = 50


class DrawIOConverter:
    """Converts canonical graph to/from draw.io XML format.
    Produces industry-standard architecture diagrams."""

    # ── Public API ────────────────────────────────────────────────────────────

    def graph_to_xml(self, graph: InfraGraph) -> str:
        """Convert canonical graph to production-ready draw.io XML.

        Design:
        - Flat layout: ALL cells have parent='1' — no child nesting, zero coordinate bugs.
        - Colored tier bands: horizontal rounded-rect backgrounds per tier.
        - AWS4 resourceIcon stencils: coloured square icons matching AWS brand palette.
        - VPC transparent dashed outline drawn FIRST (behind everything).
        - Z-order: VPC bg → tier bands → nodes → edges.
        """
        logger.info(f"[DrawIOConverter] Converting graph to XML: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # ── Layout constants ──────────────────────────────────────────────────
        PW          = 1700          # page width
        MARGIN_X    = 70            # left/right page margin
        NODE_W      = 64            # icon cell width
        NODE_H      = 64            # icon cell height
        COL_STRIDE  = 140           # centre-to-centre horizontal spacing
        MAX_COLS    = 8             # max nodes per row
        BAND_PAD_T  = 36            # space above nodes inside band (for tier label)
        BAND_PAD_B  = 20            # space below nodes inside band
        LABEL_H     = 32            # label height below icon
        ROW_H       = NODE_H + LABEL_H + 14  # height of one node row inside band
        BAND_GAP    = 18            # vertical gap between tier bands
        Y_START     = 76            # y of first tier band (below title)
        BAND_W      = PW - 2 * MARGIN_X

        # ── AWS brand colours per node category ───────────────────────────────
        CATEGORY_COLOR: Dict[str, str] = {
            "compute":       "#ED7100",   # AWS orange
            "storage":       "#3F8624",   # AWS green
            "database":      "#C7131F",   # AWS red
            "network":       "#8C4FFF",   # AWS purple
            "networking":    "#8C4FFF",
            "edge":          "#8C4FFF",
            "cdn":           "#8C4FFF",
            "dns":           "#8C4FFF",
            "load_balancing":"#8C4FFF",
            "api":           "#E7157B",   # AWS pink
            "messaging":     "#E7157B",
            "monitoring":    "#E7157B",
            "management":    "#E7157B",
            "security":      "#DD344C",   # AWS dark-red
            "default":       "#232F3E",   # AWS navy
        }

        # ── Tier band visual config ───────────────────────────────────────────
        TIER_BAND: Dict[str, dict] = {
            "internet":  {"bg": "#EEF2FF", "border": "#818CF8", "fg": "#3730A3", "label": "INTERNET"},
            "edge":      {"bg": "#E0F2FE", "border": "#38BDF8", "fg": "#0369A1", "label": "EDGE / LOAD BALANCING"},
            "compute":   {"bg": "#FFF7ED", "border": "#FB923C", "fg": "#C2410C", "label": "COMPUTE"},
            "data":      {"bg": "#F0FDF4", "border": "#4ADE80", "fg": "#166534", "label": "DATA / STORAGE"},
            "security":  {"bg": "#FFF1F2", "border": "#FB7185", "fg": "#9F1239", "label": "SECURITY / IDENTITY"},
            "monitoring":{"bg": "#F0FDFA", "border": "#2DD4BF", "fg": "#0F766E", "label": "MONITORING / OPERATIONS"},
        }

        provider = (graph.provider.value if graph.provider else "aws").lower()

        # ── Pre-classify nodes ────────────────────────────────────────────────
        tiered: Dict[str, List[GraphNode]] = {t: [] for t in TIER_ORDER}
        vpc_nodes: List[GraphNode] = []

        for node in graph.nodes:
            tier = self._classify_tier(node)
            if tier == "network_container":
                vpc_nodes.append(node)
            elif tier in tiered:
                tiered[tier].append(node)
            else:
                tiered["compute"].append(node)

        # ── Pre-compute band geometries ───────────────────────────────────────
        # Returns (band_x, band_y, band_h) for each non-empty tier
        band_geom: Dict[str, Tuple[int, int, int]] = {}
        y_cursor = Y_START
        for tier_name in TIER_ORDER:
            nodes = tiered[tier_name]
            if not nodes:
                continue
            rows = max(1, (len(nodes) + MAX_COLS - 1) // MAX_COLS)
            band_h = BAND_PAD_T + rows * ROW_H + BAND_PAD_B
            band_geom[tier_name] = (MARGIN_X, y_cursor, band_h)
            y_cursor += band_h + BAND_GAP

        total_h = y_cursor + 40

        # ── Build XML tree ────────────────────────────────────────────────────
        mx = ET.Element("mxGraphModel")
        for k, v in [("dx","1422"),("dy","800"),("grid","1"),("gridSize","10"),
                     ("guides","1"),("tooltips","1"),("connect","1"),("arrows","1"),
                     ("fold","1"),("page","1"),("pageScale","1"),
                     ("pageWidth",str(PW)),("pageHeight",str(max(total_h, 900))),
                     ("background","#F8FAFC")]:
            mx.set(k, v)

        root = ET.SubElement(mx, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")

        nid = [2]
        def _id() -> str:
            nid[0] += 1
            return str(nid[0])

        def _geom(cell, x, y, w, h, relative="0"):
            g = ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y),
                              width=str(w), height=str(h))
            if relative == "1":
                g.set("relative", "1")
            g.set("as", "geometry")

        # ── 1. Title ──────────────────────────────────────────────────────────
        prov_upper = provider.upper()
        tc = ET.SubElement(root, "mxCell", id=_id(), parent="1", vertex="1",
            value=(f'<b style="font-size:15px">Architecture Diagram — {prov_upper}</b>'
                   f'<br/><font style="font-size:11px;color:#6B7280">'
                   f'{len(graph.nodes)} components · {len(graph.edges)} connections</font>'),
            style=("text;html=1;strokeColor=none;fillColor=none;align=left;"
                   "verticalAlign=middle;fontSize=14;fontColor=#111827;"))
        _geom(tc, MARGIN_X, 14, 700, 52)

        # ── 2. VPC outline (transparent, behind everything) ───────────────────
        node_id_map: Dict[str, str] = {}
        vpc_outline_id = None
        if vpc_nodes:
            # Wrap compute + data tiers
            vpc_tiers = [t for t in ("compute", "data") if band_geom.get(t)]
            if vpc_tiers:
                first_t = vpc_tiers[0]
                last_t  = vpc_tiers[-1]
                _, vy, _ = band_geom[first_t]
                _, ly, lh = band_geom[last_t]
                vpc_x = MARGIN_X - 14
                vpc_y = vy - 14
                vpc_w = BAND_W + 28
                vpc_h = (ly + lh) - vy + 28
                vn = vpc_nodes[0]
                cidr = vn.properties.get("configuration", {}).get("cidr", "10.0.0.0/16")
                vpc_outline_id = _id()
                vc = ET.SubElement(root, "mxCell", id=vpc_outline_id, parent="1", vertex="1",
                    value=(f'<b style="font-size:12px;color:#232F3E">{vn.label or "VPC"}</b>'
                           f'<br/><font style="font-size:9px;color:#6B7280">{cidr}</font>'),
                    style=("rounded=1;arcSize=2;whiteSpace=wrap;html=1;"
                           "fillColor=none;strokeColor=#232F3E;strokeWidth=2.5;"
                           "dashed=1;dashPattern=10 6;"
                           "verticalAlign=top;align=left;spacingLeft=14;spacingTop=8;"
                           "fontStyle=0;fontSize=12;pointerEvents=0;"))
                _geom(vc, vpc_x, vpc_y, vpc_w, vpc_h)
            for vn in vpc_nodes:
                node_id_map[vn.id] = vpc_outline_id or _id()

        # ── 3. Tier bands ─────────────────────────────────────────────────────
        for tier_name in TIER_ORDER:
            if tier_name not in band_geom:
                continue
            bx, by, bh = band_geom[tier_name]
            cfg = TIER_BAND.get(tier_name, {"bg":"#F5F5F5","border":"#999","fg":"#444","label":tier_name.upper()})

            # Background band
            bc = ET.SubElement(root, "mxCell", id=_id(), parent="1", vertex="1", value="",
                style=(f"rounded=1;arcSize=3;whiteSpace=wrap;html=1;shadow=0;"
                       f"fillColor={cfg['bg']};strokeColor={cfg['border']};strokeWidth=1.5;"))
            _geom(bc, bx, by, BAND_W, bh)

            # Tier label inside band
            lc = ET.SubElement(root, "mxCell", id=_id(), parent="1", vertex="1",
                value=f'<b style="font-size:10px;color:{cfg["fg"]}">{cfg["label"]}</b>',
                style="text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=top;")
            _geom(lc, bx + 12, by + 8, BAND_W - 24, 20)

        # ── 4. Nodes (flat, all parent='1') ───────────────────────────────────
        for tier_name in TIER_ORDER:
            nodes = tiered[tier_name]
            if not nodes or tier_name not in band_geom:
                continue
            bx, by, _ = band_geom[tier_name]

            for idx, node in enumerate(nodes):
                row = idx // MAX_COLS
                col = idx % MAX_COLS
                nodes_this_row = min(MAX_COLS, len(nodes) - row * MAX_COLS)
                row_total_w = nodes_this_row * COL_STRIDE - (COL_STRIDE - NODE_W)
                row_start_x = bx + (BAND_W - row_total_w) // 2

                nx = row_start_x + col * COL_STRIDE
                ny = by + BAND_PAD_T + row * ROW_H

                svc_type = node.properties.get("type", "").lower()
                icon_color = CATEGORY_COLOR.get(svc_type, CATEGORY_COLOR["default"])
                label = self._build_node_label(node)
                style = self._get_node_style_v2(node, provider, icon_color)

                cid = _id()
                node_id_map[node.id] = cid
                cell = ET.SubElement(root, "mxCell",
                    id=cid, parent="1", vertex="1", value=label, style=style)
                cell.set("infra_service", node.service or "")
                cell.set("infra_provider", node.provider.value if node.provider else "aws")
                cell.set("infra_tier", tier_name)
                cell.set("infra_type", svc_type)
                try:
                    cell.set("infra_config", json.dumps(node.properties.get("configuration", {})))
                except Exception:
                    pass
                _geom(cell, nx, ny, NODE_W, NODE_H)

        # ── 5. Edges ──────────────────────────────────────────────────────────
        for edge in graph.edges:
            src = node_id_map.get(edge.source)
            tgt = node_id_map.get(edge.target)
            if not src or not tgt or src == tgt:
                continue
            eid = _id()
            ec = ET.SubElement(root, "mxCell",
                id=eid, parent="1", edge="1", source=src, target=tgt,
                value=self._build_edge_label(edge),
                style=self._get_edge_style(edge))
            ec.set("infra_relationship", edge.relationship or "connects")
            ec.set("infra_protocol", str(edge.properties.get("protocol", "")))
            ec.set("infra_port", str(edge.properties.get("port", "")))
            g = ET.SubElement(ec, "mxGeometry")
            g.set("relative", "1")
            g.set("as", "geometry")

        xml_string = ET.tostring(mx, encoding="unicode")
        logger.info(f"[DrawIOConverter] XML generated ({len(xml_string)} chars)")
        return xml_string

    def xml_to_graph(self, xml_string: str, provider: CloudProvider = CloudProvider.AWS) -> InfraGraph:
        """Convert draw.io XML back to canonical graph."""
        logger.info(f"[DrawIOConverter] Converting XML to graph")

        try:
            tree_root = ET.fromstring(xml_string)

            nodes = []
            edges = []
            node_id_map = {}

            for cell in tree_root.findall(".//mxCell[@vertex='1']"):
                cell_id = cell.get("id")
                label = cell.get("value", "")
                # Skip tier labels and title
                if not label or "──" in label or "Architecture Diagram" in label:
                    continue

                infra_service = cell.get("infra_service", "")
                infra_provider = cell.get("infra_provider", provider.value)

                node_id = infra_service or f"node-{cell_id}"
                node_id_map[cell_id] = node_id

                geometry = cell.find("mxGeometry")
                x = float(geometry.get("x", 0)) if geometry is not None else 0
                y = float(geometry.get("y", 0)) if geometry is not None else 0

                props = {"source": "drawio_xml"}
                try:
                    config_str = cell.get("infra_config", "")
                    if config_str:
                        props["configuration"] = json.loads(config_str)
                except Exception:
                    pass
                confidence = cell.get("infra_confidence", "0.7")
                try:
                    props["confidence"] = float(confidence)
                except ValueError:
                    props["confidence"] = 0.7
                props["tier"] = cell.get("infra_tier", "production")

                node = GraphNode(
                    id=node_id,
                    provider=CloudProvider(infra_provider) if infra_provider in ("aws", "azure", "gcp") else provider,
                    service=infra_service or label.lower().replace(" ", "_"),
                    label=label.split("<")[0].strip() if "<" in label else label,
                    position={"x": x, "y": y},
                    properties=props,
                )
                nodes.append(node)

            for cell in tree_root.findall(".//mxCell[@edge='1']"):
                source_id = cell.get("source")
                target_id = cell.get("target")

                graph_source = node_id_map.get(source_id)
                graph_target = node_id_map.get(target_id)

                if graph_source and graph_target:
                    edge = GraphEdge(
                        source=graph_source,
                        target=graph_target,
                        relationship=cell.get("infra_relationship", "connects"),
                        properties={
                            "protocol": cell.get("infra_protocol", ""),
                            "port": cell.get("infra_port", ""),
                            "direction": cell.get("infra_direction", "forward"),
                            "inferred": cell.get("infra_inferred", "false") == "true",
                        }
                    )
                    edges.append(edge)

            graph = InfraGraph(
                nodes=nodes, edges=edges, provider=provider,
                extraction_method="drawio_xml",
            )
            logger.info(f"[DrawIOConverter] Extracted {len(nodes)} nodes, {len(edges)} edges from XML")
            return graph

        except Exception as e:
            logger.error(f"[DrawIOConverter] XML parsing failed: {e}")
            return InfraGraph(nodes=[], edges=[], provider=provider)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_node_style_v2(self, node: GraphNode, provider: str, icon_color: str) -> str:
        """Return draw.io style using AWS4 resourceIcon stencil (colored square + white icon).
        Falls back to a styled colored rectangle if no icon match."""
        icon_name = self._get_icon_name(node, provider)

        if icon_name and provider == "aws":
            return (
                f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{icon_name};"
                f"fillColor={icon_color};strokeColor=#ffffff;fontColor=#232F3E;"
                "labelBackgroundColor=none;sketch=0;fontStyle=1;fontSize=10;"
                "verticalLabelPosition=bottom;verticalAlign=top;align=center;spacingTop=6;"
            )

        if icon_name and provider == "azure":
            return (
                f"shape=mxgraph.azure.{icon_name};"
                f"fillColor={icon_color};strokeColor=#ffffff;fontColor=#232F3E;"
                "fontStyle=1;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
            )

        if icon_name and provider == "gcp":
            return (
                f"shape=mxgraph.gcp2.{icon_name};"
                f"fillColor={icon_color};strokeColor=#ffffff;fontColor=#232F3E;"
                "fontStyle=1;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
            )

        # Generic colored box fallback
        return (
            f"rounded=1;whiteSpace=wrap;html=1;arcSize=14;"
            f"fillColor={icon_color};strokeColor=#ffffff;strokeWidth=2;"
            f"fontColor=#ffffff;fontSize=10;fontStyle=1;"
            "verticalAlign=middle;align=center;shadow=1;"
        )

    def _get_icon_name(self, node: GraphNode, provider: str) -> Optional[str]:
        """Map service name to cloud-provider icon name."""
        service = (node.service or "").lower().replace("_", " ")

        if provider == "aws":
            aws_map = [
                (["vpc"],                                    "vpc"),
                (["ec2", "instance", "virtual machine"],     "ec2"),
                (["autoscaling", "auto scaling", "asg"],     "auto_scaling2"),
                (["alb", "application load balancer"],       "application_load_balancer"),
                (["nlb", "network load balancer"],           "network_load_balancer"),
                (["elb", "load balancer"],                   "elastic_load_balancing"),
                (["rds", "aurora"],                          "rds"),
                (["dynamodb"],                               "dynamodb"),
                (["s3", "bucket", "assets bucket"],          "s3"),
                (["lambda", "function"],                     "lambda_function"),
                (["cloudfront", "cdn"],                      "cloudfront"),
                (["route53", "route 53", "hosted zone"],     "route_53"),
                (["iam", "iam role"],                        "role"),
                (["waf"],                                    "waf"),
                (["shield"],                                 "shield"),
                (["kms", "key management", "encryption key"],"kms"),
                (["secrets manager", "secret"],              "secrets_manager"),
                (["cloudwatch", "log group", "monitoring"],  "cloudwatch"),
                (["sns", "simple notification"],             "sns"),
                (["sqs", "simple queue", "queue"],           "sqs"),
                (["api gateway", "apigateway", "rest api"],  "api_gateway"),
                (["eks", "kubernetes", "eks cluster"],       "eks"),
                (["ecs", "fargate", "container"],            "ecs"),
                (["elasticache", "redis", "memcached"],      "elasticache"),
                (["opensearch", "elasticsearch"],            "opensearch_service"),
                (["cognito", "user pool"],                   "cognito"),
                (["efs", "file system"],                     "elastic_file_system"),
                (["nat gateway", "nat"],                     "nat_gateway"),
                (["internet gateway", "igw"],                "internet_gateway"),
                (["subnet", "vpc subnet"],                   "subnet"),
                (["x-ray", "xray"],                          "xray"),
                (["cloudtrail"],                             "cloudtrail"),
                (["security group"],                         "security_group"),
                (["eks node", "node group", "worker node"],  "ec2"),
            ]
            for keys, icon in aws_map:
                if any(k in service for k in keys):
                    return icon

        return None

    def _classify_tier(self, node: GraphNode) -> str:
        """Classify a node into an architecture tier."""
        service = (node.service or "").lower().replace("_", " ")
        # Direct match
        if service in TIER_CLASSIFICATION:
            return TIER_CLASSIFICATION[service]
        # Partial match
        for key, tier in TIER_CLASSIFICATION.items():
            if key in service or service in key:
                return tier
        # From properties
        prop_type = node.properties.get("type", "").lower()
        for key, tier in TIER_CLASSIFICATION.items():
            if key in prop_type:
                return tier
        return "compute"

    def _build_node_label(self, node: GraphNode) -> str:
        """Build a rich HTML label for a node cell."""
        name = node.label or node.service.replace("_", " ").title()
        config = node.properties.get("configuration", {})

        # Pick the most useful config detail
        detail = ""
        for key in ["instance_class", "instance_type", "engine", "cidr", "scheme", "version", "runtime"]:
            val = config.get(key)
            if val:
                detail = f'<br/><font style="font-size:9px" color="#888">{val}</font>'
                break

        return f'<b>{name}</b>{detail}'

    def _get_node_style(self, node: GraphNode, provider: str) -> str:
        """Get draw.io style for a node with correct cloud icon stencils."""
        icon_shape = self._get_cloud_icon_shape(node, provider)
        if icon_shape:
            return (
                f"shape={icon_shape};html=1;outlineConnect=0;dashed=0;"
                "verticalLabelPosition=bottom;verticalAlign=top;align=center;"
                "aspect=fixed;fontSize=11;fontStyle=1;fontColor=#232F3E;"
                "spacingTop=4;"
            )

        # Fallback: colored rounded rectangle
        service = node.service.lower()
        fill, stroke = self._get_service_colors(service, provider)
        return (
            f"rounded=1;whiteSpace=wrap;html=1;arcSize=8;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=2;"
            f"fontSize=11;fontStyle=1;fontColor=#232F3E;spacing=8;"
            f"shadow=1;glass=0;"
        )

    def _get_service_colors(self, service: str, provider: str) -> Tuple[str, str]:
        """Return (fill, stroke) colors based on service category."""
        category_colors = {
            "network":        ("#E8EAF6", "#3949AB"),
            "edge":           ("#E1F5FE", "#0277BD"),
            "compute":        ("#E3F2FD", "#1565C0"),
            "data":           ("#FFF3E0", "#EF6C00"),
            "storage":        ("#E8F5E9", "#2E7D32"),
            "security":       ("#FCE4EC", "#C62828"),
            "monitoring":     ("#E0F2F1", "#00695C"),
            "messaging":      ("#F3E5F5", "#7B1FA2"),
            "cdn":            ("#FFF8E1", "#F9A825"),
            "dns":            ("#E8EAF6", "#283593"),
            "load_balancing": ("#E1F5FE", "#0288D1"),
        }
        type_map = [
            (["vpc", "vnet", "subnet", "network", "nat"], "network"),
            (["ec2", "vm", "compute", "eks", "ecs", "gke", "aks", "lambda", "function", "fargate", "cloud run", "app service", "autoscaling"], "compute"),
            (["rds", "sql", "database", "dynamodb", "cosmos", "firestore", "spanner", "bigquery", "elasticache", "opensearch", "memorystore", "aurora", "redis"], "data"),
            (["s3", "storage", "blob", "bucket", "efs"], "storage"),
            (["iam", "kms", "waf", "shield", "armor", "key vault", "cognito", "secrets"], "security"),
            (["sns", "sqs", "event", "pub/sub", "service bus"], "messaging"),
            (["cloudwatch", "monitoring", "x-ray", "log analytics"], "monitoring"),
            (["cloudfront", "cdn", "front door"], "cdn"),
            (["route53", "dns", "cloud dns"], "dns"),
            (["alb", "nlb", "elb", "load balancer", "application gateway"], "load_balancing"),
        ]
        for keywords, cat in type_map:
            if any(k in service for k in keywords):
                return category_colors.get(cat, ("#FFFFFF", "#333333"))
        return ("#FFFFFF", "#333333")

    def _get_cloud_icon_shape(self, node: GraphNode, provider: str) -> Optional[str]:
        """Map services to correct draw.io AWS4/Azure/GCP stencil shapes."""
        service = (node.service or "").lower().replace("_", " ")

        if provider == "aws":
            aws_shapes = [
                (["vpc"],                                                      "mxgraph.aws4.vpc"),
                (["ec2", "instance", "virtual machine", "vm"],                 "mxgraph.aws4.ec2"),
                (["autoscaling", "auto scaling", "asg"],                       "mxgraph.aws4.auto_scaling2"),
                (["alb", "application load balancer"],                         "mxgraph.aws4.application_load_balancer"),
                (["nlb", "network load balancer"],                             "mxgraph.aws4.network_load_balancer"),
                (["elb", "classic load balancer", "load balancer"],            "mxgraph.aws4.elastic_load_balancing"),
                (["rds", "aurora"],                                            "mxgraph.aws4.rds"),
                (["dynamodb"],                                                 "mxgraph.aws4.dynamodb"),
                (["s3", "bucket", "object storage"],                           "mxgraph.aws4.s3"),
                (["lambda", "function"],                                       "mxgraph.aws4.lambda_function"),
                (["cloudfront", "cdn"],                                        "mxgraph.aws4.cloudfront"),
                (["route53", "route 53", "dns"],                               "mxgraph.aws4.route_53"),
                (["iam", "identity"],                                          "mxgraph.aws4.iam"),
                (["waf"],                                                      "mxgraph.aws4.waf"),
                (["shield"],                                                   "mxgraph.aws4.shield"),
                (["kms", "key management"],                                    "mxgraph.aws4.kms"),
                (["secrets manager"],                                          "mxgraph.aws4.secrets_manager"),
                (["cloudwatch", "monitoring"],                                 "mxgraph.aws4.cloudwatch"),
                (["sns", "simple notification"],                               "mxgraph.aws4.sns"),
                (["sqs", "simple queue"],                                      "mxgraph.aws4.sqs"),
                (["api gateway", "apigateway"],                                "mxgraph.aws4.api_gateway"),
                (["eks", "kubernetes"],                                        "mxgraph.aws4.eks"),
                (["ecs", "fargate"],                                           "mxgraph.aws4.ecs"),
                (["elasticache", "redis", "memcached"],                        "mxgraph.aws4.elasticache"),
                (["opensearch", "elasticsearch"],                              "mxgraph.aws4.opensearch_service"),
                (["cognito"],                                                  "mxgraph.aws4.cognito"),
                (["efs"],                                                      "mxgraph.aws4.elastic_file_system"),
                (["nat gateway", "nat"],                                       "mxgraph.aws4.nat_gateway"),
                (["internet gateway", "igw"],                                  "mxgraph.aws4.internet_gateway"),
                (["subnet"],                                                   "mxgraph.aws4.vpc_subnet"),
                (["x-ray", "xray"],                                            "mxgraph.aws4.x_ray"),
            ]
            for keys, shape in aws_shapes:
                if any(key in service for key in keys):
                    return shape

        if provider == "azure":
            azure_shapes = [
                (["vnet", "virtual network"],              "img/lib/azure2/networking/Virtual_Networks.svg"),
                (["vm", "virtual machine", "compute"],     "img/lib/azure2/compute/Virtual_Machine.svg"),
                (["sql database", "sql server", "sql"],    "img/lib/azure2/databases/SQL_Database.svg"),
                (["cosmos db", "cosmosdb"],                "img/lib/azure2/databases/Azure_Cosmos_DB.svg"),
                (["blob storage", "storage account"],      "img/lib/azure2/storage/Storage_Accounts.svg"),
                (["app service", "web app"],               "img/lib/azure2/app_services/App_Services.svg"),
                (["function app", "functions"],             "img/lib/azure2/compute/Function_Apps.svg"),
                (["aks", "kubernetes"],                     "img/lib/azure2/containers/Kubernetes_Services.svg"),
                (["load balancer"],                         "img/lib/azure2/networking/Load_Balancers.svg"),
                (["application gateway"],                   "img/lib/azure2/networking/Application_Gateways.svg"),
                (["front door", "cdn"],                     "img/lib/azure2/networking/Front_Doors.svg"),
                (["dns"],                                   "img/lib/azure2/networking/DNS_Zones.svg"),
                (["key vault"],                             "img/lib/azure2/security/Key_Vaults.svg"),
                (["active directory", "entra"],             "img/lib/azure2/identity/Azure_AD.svg"),
                (["monitor", "log analytics"],              "img/lib/azure2/management_governance/Monitor.svg"),
                (["nsg", "network security group"],         "img/lib/azure2/networking/Network_Security_Groups.svg"),
                (["service bus"],                           "img/lib/azure2/integration/Service_Bus.svg"),
                (["event grid"],                            "img/lib/azure2/integration/Event_Grid_Domains.svg"),
                (["event hub"],                             "img/lib/azure2/analytics/Event_Hubs.svg"),
            ]
            for keys, shape in azure_shapes:
                if any(key in service for key in keys):
                    return f"image;image={shape}"

        if provider == "gcp":
            gcp_shapes = [
                (["vpc", "network"],               "img/lib/gcp2/networking/Virtual_Private_Cloud.svg"),
                (["compute engine", "gce", "vm"],  "img/lib/gcp2/compute/Compute_Engine.svg"),
                (["cloud sql", "sql"],             "img/lib/gcp2/databases/Cloud_SQL.svg"),
                (["cloud storage", "gcs", "bucket"], "img/lib/gcp2/storage/Cloud_Storage.svg"),
                (["bigquery"],                     "img/lib/gcp2/data_analytics/BigQuery.svg"),
                (["cloud functions"],              "img/lib/gcp2/compute/Cloud_Functions.svg"),
                (["cloud run"],                    "img/lib/gcp2/compute/Cloud_Run.svg"),
                (["gke", "kubernetes"],            "img/lib/gcp2/compute/Google_Kubernetes_Engine.svg"),
                (["load balancer", "load balancing"], "img/lib/gcp2/networking/Cloud_Load_Balancing.svg"),
                (["cloud cdn"],                    "img/lib/gcp2/networking/Cloud_CDN.svg"),
                (["cloud dns"],                    "img/lib/gcp2/networking/Cloud_DNS.svg"),
                (["cloud armor"],                  "img/lib/gcp2/security/Cloud_Armor.svg"),
                (["cloud kms", "kms"],             "img/lib/gcp2/security/Key_Management_Service.svg"),
                (["cloud monitoring", "monitoring"], "img/lib/gcp2/management_tools/Cloud_Monitoring.svg"),
                (["pub/sub", "pubsub"],            "img/lib/gcp2/data_analytics/Cloud_PubSub.svg"),
                (["firestore"],                    "img/lib/gcp2/databases/Cloud_Firestore.svg"),
                (["spanner"],                      "img/lib/gcp2/databases/Cloud_Spanner.svg"),
                (["memorystore", "redis"],         "img/lib/gcp2/databases/Cloud_Memorystore.svg"),
            ]
            for keys, shape in gcp_shapes:
                if any(key in service for key in keys):
                    return f"image;image={shape}"

        return None

    def _build_edge_label(self, edge: GraphEdge) -> str:
        """Build a compact label for an edge showing protocol/port."""
        protocol = edge.properties.get("protocol", "")
        port = edge.properties.get("port", "")
        relationship = edge.relationship or ""

        parts = []
        if protocol and str(protocol).upper() not in ("0", "TCP", ""):
            parts.append(str(protocol).upper())
        elif protocol:
            parts.append(str(protocol).upper())

        if port and str(port) not in ("0", ""):
            parts.append(f":{port}")

        if parts:
            return f'<font style="font-size:9px" color="#666">{"".join(parts)}</font>'

        # Fallback to relationship
        if relationship and relationship != "connects":
            short = relationship.replace("_", " ")
            return f'<font style="font-size:9px" color="#888">{short}</font>'

        return ""

    def _get_edge_style(self, edge: GraphEdge) -> str:
        """Get draw.io style for an edge with relationship-based differentiation."""
        rel = (edge.relationship or "").lower()
        direction = (edge.properties.get("direction", "") or "").lower()

        # Base style
        base = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"

        # Bidirectional
        if "bidirectional" in direction:
            return f"{base}strokeWidth=2;strokeColor=#1565C0;startArrow=classic;startFill=1;endArrow=classic;endFill=1;"

        # Data flow (reads/writes)
        if any(k in rel for k in ["reads", "writes", "queries"]):
            return f"{base}strokeWidth=2;strokeColor=#EF6C00;dashed=1;dashPattern=8 4;endArrow=classic;endFill=1;"

        # Deployment / containment
        if any(k in rel for k in ["deployed", "contains", "hosted"]):
            return f"{base}strokeWidth=1;strokeColor=#999999;dashed=1;dashPattern=3 3;endArrow=open;endFill=0;"

        # Invocation / traffic
        if any(k in rel for k in ["invokes", "serves", "forwards", "routes", "publishes", "triggers"]):
            return f"{base}strokeWidth=2;strokeColor=#1565C0;endArrow=classic;endFill=1;"

        # Caching
        if "caches" in rel:
            return f"{base}strokeWidth=2;strokeColor=#F9A825;endArrow=classic;endFill=1;"

        # Default
        return f"{base}strokeWidth=2;strokeColor=#666666;endArrow=classic;endFill=1;"
