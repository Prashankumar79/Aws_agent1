"""
================================================================================
  backend/app/services/diagram_generator.py  —  LANGGRAPH DIAGRAM GENERATOR
================================================================================

Simple 3-node LangGraph pipeline:
  extract_text → generate_xml → extract_components

  Node 1 (extract_text)     : Docling pulls markdown text from the uploaded file.
  Node 2 (generate_xml)     : Claude generates draw.io mxGraphModel XML directly
                               using provider-specific icon/colour guide.
  Node 3 (extract_components): Claude extracts a structured component list used
                               downstream for master_context / Terraform.

Why this approach:
  - Claude already knows draw.io XML format perfectly — no stencil-mapping code.
  - Provider (AWS/Azure/GCP) is passed in; each gets its own icon guide.
  - Output is pure XML that the draw.io editor renders immediately.
================================================================================
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── LangGraph state ───────────────────────────────────────────────────────────
class DiagramState(TypedDict):
    file_path: str
    provider: str           # "aws" | "azure" | "gcp"
    diagram_type: str       # "hld" | "lld" | "network" | "security" | "dr" | "cicd" | etc.
    custom_instruction: str # For "custom" type — user's free-form instruction
    raw_text: str
    drawio_xml: str
    components: list
    error: Optional[str]


# ── Per-provider icon / colour guide injected into the XML-generation prompt ──
PROVIDER_GUIDE: dict = {
    "aws": """
ICON FORMAT (all nodes must use this style):
  shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{ICON_NAME};
  fillColor={COLOR};strokeColor=#ffffff;fontColor=#232F3E;
  labelBackgroundColor=none;sketch=0;fontStyle=1;fontSize=11;
  verticalLabelPosition=bottom;verticalAlign=top;align=center;

AWS BRAND COLOURS:
  Compute  (EC2/EKS/ECS/Lambda/Fargate/AutoScaling): #ED7100
  Storage  (S3/EFS/EBS):                             #3F8624
  Database (RDS/Aurora/DynamoDB/ElastiCache):        #C7131F
  Network  (VPC/ALB/NLB/CloudFront/Route53/APIGW):   #8C4FFF
  Security (IAM/KMS/WAF/Cognito/SecretsManager):     #DD344C
  Messaging/Integration (SNS/SQS/EventBridge):       #E7157B
  Operations (CloudWatch/X-Ray/CloudTrail):           #E7157B

ICON NAMES (resIcon value after mxgraph.aws4.):
  ec2  eks  ecs  lambda_function  auto_scaling2  fargate
  rds  dynamodb  elasticache  s3  elastic_file_system
  application_load_balancer  network_load_balancer  elastic_load_balancing
  cloudfront  route_53  api_gateway  vpc  nat_gateway  internet_gateway
  sns  sqs  eventbridge  cloudwatch  iam  role  kms  waf  cognito  secrets_manager

NODE SIZE: width="64" height="64"
""",

    "azure": """
ICON FORMAT (all nodes must use this style):
  shape=mxgraph.azure.{ICON_NAME};
  fillColor={COLOR};strokeColor=#ffffff;fontColor=#232F3E;
  fontStyle=1;fontSize=11;verticalLabelPosition=bottom;verticalAlign=top;align=center;

AZURE BRAND COLOURS:
  Compute  (VM/AKS/Functions/AppService/ContainerApps): #0078D4
  Storage  (BlobStorage/FileShare/Queue):               #0F9D58
  Database (SQLDatabase/CosmosDB/CacheForRedis):        #E8373B
  Network  (VNet/AppGateway/LoadBalancer/FrontDoor):    #7C4DFF
  Security (KeyVault/ActiveDirectory/Defender/Firewall): #DD344C
  Integration (ServiceBus/EventGrid/EventHubs/APIM):    #E7157B
  Monitoring (Monitor/ApplicationInsights/LogAnalytics): #0078D4

ICON NAMES (shape value after mxgraph.azure.):
  virtual_machine  virtual_machine_scale_set  kubernetes_service  function_apps  app_services  container_apps
  sql_database  cosmos_db  redis_cache  storage_accounts  blob_storage
  virtual_networks  application_gateway  load_balancers  front_door  traffic_manager  dns_zones
  vpn_gateway  expressroute  firewall  nat_gateway  private_endpoint  private_link
  api_management  service_bus  event_grid  event_hubs  logic_apps
  key_vault  active_directory  defender  managed_identity  policy
  monitor  application_insights  log_analytics  alerts  action_groups
  iot_hub  notification_hubs  cdn_profiles

IMPORTANT: For Azure Firewall use shape=mxgraph.azure.firewall
For VNet use shape=mxgraph.azure.virtual_networks
For Application Gateway use shape=mxgraph.azure.application_gateway
For Key Vault use shape=mxgraph.azure.key_vault
For IoT Hub use shape=mxgraph.azure.iot_hub

NODE SIZE: width="64" height="64"
""",

    "gcp": """
ICON FORMAT (all nodes must use this style):
  shape=mxgraph.gcp2.{ICON_NAME};
  fillColor={COLOR};strokeColor=#ffffff;fontColor=#232F3E;
  fontStyle=1;fontSize=11;verticalLabelPosition=bottom;verticalAlign=top;align=center;

GCP BRAND COLOURS:
  Compute  (GCE/GKE/CloudRun/CloudFunctions/AppEngine): #4285F4
  Storage  (GCS/Filestore/PersistentDisk):              #0F9D58
  Database (CloudSQL/Spanner/Firestore/Bigtable):       #DB4437
  Network  (CloudLB/CloudCDN/CloudDNS/VPC):             #7C4DFF
  Security (CloudArmor/CloudKMS/IAM):                   #DD344C
  Analytics (BigQuery/CloudPubSub/Dataflow):            #F4B400
  Operations (CloudMonitoring/CloudLogging):            #E7157B

ICON NAMES (shape value after mxgraph.gcp2.):
  compute_engine  kubernetes_engine  cloud_run  cloud_functions  app_engine
  cloud_sql  cloud_spanner  cloud_storage  bigquery  firestore  bigtable  memorystore
  cloud_load_balancing  cloud_cdn  cloud_dns  virtual_private_cloud  cloud_nat
  cloud_interconnect  cloud_vpn  cloud_router
  cloud_armor  cloud_kms  cloud_iam  identity_platform
  cloud_monitoring  cloud_logging  cloud_trace  error_reporting
  cloud_pub_sub  dataflow  cloud_tasks  cloud_scheduler
  cloud_iot_core  artifact_registry  container_registry  secret_manager

IMPORTANT: For VPC use shape=mxgraph.gcp2.virtual_private_cloud
For Cloud NAT use shape=mxgraph.gcp2.cloud_nat
For Cloud Armor use shape=mxgraph.gcp2.cloud_armor
For Secret Manager use shape=mxgraph.gcp2.secret_manager
For Cloud SQL use shape=mxgraph.gcp2.cloud_sql

NODE SIZE: width="64" height="64"
""",
}

# ── Enterprise nested-container layout guide ─────────────────────────────────
TIER_BAND_STYLES = """
LAYOUT STYLE: Enterprise Nested Container Architecture (like IBM/AWS enterprise diagrams)

CONTAINER HIERARCHY:
  Level 0 — Page background (#F0F4F8)
  Level 1 — Major zones (e.g., "CLOUD PRIVATE", "ENTERPRISE", "ON-PREMISES")
             Style: rounded=1;arcSize=2;fillColor=#E8EDF2;strokeColor=#4A6FA5;strokeWidth=2;
                    fontStyle=1;fontSize=13;fontColor=#1A3A5C;verticalAlign=top;align=left;
                    spacingLeft=12;spacingTop=8;
  Level 2 — Sub-zones inside Level 1 (e.g., "WORKLOADS", "DEVELOPER AUTOMATION", "MANAGEMENT")
             Style: rounded=1;arcSize=3;fillColor=#FFFFFF;strokeColor=#7B9EC4;strokeWidth=1.5;
                    fontStyle=1;fontSize=11;fontColor=#2C5282;verticalAlign=top;align=left;
                    spacingLeft=10;spacingTop=6;
  Level 3 — Category groups inside sub-zones (e.g., "CLOUD NATIVE", "CONTAINERIZED MIDDLEWARE")
             Style: rounded=1;arcSize=4;fillColor=#EBF4FF;strokeColor=#90B8D8;strokeWidth=1;
                    fontStyle=1;fontSize=10;fontColor=#2B6CB0;verticalAlign=top;align=center;
  Level 4 — Individual service icons (children of Level 3 containers)
             Use cloud provider stencil icons. Size: 48×48px.
             Label below icon: fontSize=9;fontStyle=0;

CONTAINER RULES:
  - ALL containers use vertex="1" with style containing "container=1;collapsible=0;"
  - Child cells reference their parent container via parent="PARENT_CELL_ID"
  - Containers auto-size to fit children — set width/height explicitly
  - Use swimlane style for sub-zones: "swimlane;startSize=24;fillColor=..."

ICON STYLE IN CONTAINERS:
  - Icons are children of their category container
  - Use circular background: shape=mxgraph.{provider}.{icon};fillColor={COLOR};
    strokeColor=#FFFFFF;strokeWidth=2;
  - Label: verticalLabelPosition=bottom;verticalAlign=top;fontSize=9;

ARROWS:
  - Use curved arrows between zones: edgeStyle=orthogonalEdgeStyle;curved=1;
  - Arrow color matches source zone color
  - Add protocol labels on arrows

LEGEND:
  - Bottom-left corner, outside all containers
  - Show zone colors with labels
  - Style: rounded=1;fillColor=#FFFFFF;strokeColor=#CCCCCC;fontSize=10;

PAGE: pageWidth="2200" pageHeight="1600" background="#F0F4F8"
"""

# ── Diagram-type specific focus instructions ──────────────────────────────────
# Each type tells Claude WHAT to emphasize and HOW to structure the diagram.
DIAGRAM_TYPE_GUIDES: dict = {
    "hld": """
DIAGRAM TYPE: High-Level Design (HLD)
FOCUS: Architecture overview for leadership, architects, and stakeholders.
SHOW:
  - All major cloud services and their relationships
  - Security zones (public/private/data tiers)
  - HA/DR overview (multi-AZ, failover paths)
  - Integration points between services
  - Data flow direction (arrows with protocol labels)
STYLE: Clean, high-level — no subnet CIDRs or port numbers. Use tier bands.
TITLE: "High-Level Architecture — {CLOUD} {APP_NAME}"
""",

    "lld": """
DIAGRAM TYPE: Low-Level Design (LLD)
FOCUS: Implementation details for engineers and DevOps.
SHOW:
  - Exact subnet CIDRs (e.g., 10.0.1.0/24)
  - Route tables and NAT Gateway paths
  - IAM roles and their attached services
  - Port mappings on security groups (e.g., 443, 5432, 6379)
  - Storage configurations (volume types, sizes)
  - Specific instance types / SKUs
STYLE: Dense, technical — include config labels on nodes. Use a grid layout.
TITLE: "Low-Level Design — {CLOUD} {APP_NAME}"
""",

    "network": """
DIAGRAM TYPE: Network Architecture Design
FOCUS: All networking components and connectivity.
SHOW:
  - VPC/VNet with all subnets (public, private, data, management)
  - Peering connections and Transit Gateway
  - Firewall rules and Security Groups
  - DNS zones and Route53/Azure DNS
  - VPN/Direct Connect/ExpressRoute to on-premises
  - Load balancers (ALB/NLB/Application Gateway)
  - NAT Gateways and Internet Gateways
  - CIDR blocks on every subnet
STYLE: Network-focused — use network topology layout. Show IP ranges prominently.
TITLE: "Network Architecture — {CLOUD}"
""",

    "security": """
DIAGRAM TYPE: Security Architecture
FOCUS: All security controls, IAM, encryption, and compliance boundaries.
SHOW:
  - IAM roles, policies, and trust relationships
  - Encryption at rest (KMS keys, CMKs) and in transit (TLS)
  - Secrets Manager / Key Vault / Parameter Store
  - WAF, Shield, Firewall rules
  - Security Groups and NACLs as boundaries
  - SIEM/logging (CloudTrail, Security Hub, Sentinel)
  - Compliance zones (PCI-DSS scope, HIPAA boundary)
  - Zero-trust boundaries
STYLE: Use red/pink security zone bands. Show trust boundaries as dashed boxes.
TITLE: "Security Architecture — {CLOUD}"
""",

    "dr": """
DIAGRAM TYPE: Disaster Recovery (DR) Design
FOCUS: Multi-region failover, backup, and recovery architecture.
SHOW:
  - Primary region and DR region side by side
  - Replication paths (RDS cross-region, S3 CRR, DynamoDB Global Tables)
  - RTO/RPO labels on critical services
  - Failover triggers (Route53 health checks, Traffic Manager)
  - Backup retention policies
  - Pilot light / warm standby / active-active pattern
STYLE: Two-column layout (Primary | DR). Use arrows showing replication direction.
TITLE: "Disaster Recovery Architecture — {CLOUD}"
""",

    "cicd": """
DIAGRAM TYPE: CI/CD Architecture
FOCUS: Deployment pipeline from code to production.
SHOW:
  - Source control (GitHub/GitLab/CodeCommit)
  - Build stages (CodeBuild/Jenkins/GitHub Actions)
  - Artifact registry (ECR/ACR/Artifact Registry)
  - Deployment targets (EKS/ECS/App Service/GKE)
  - GitOps tools (ArgoCD/Flux)
  - Rollback mechanisms
  - Environment progression (dev → staging → prod)
  - Approval gates
STYLE: Left-to-right pipeline flow. Use sequence/flow layout.
TITLE: "CI/CD Architecture — {CLOUD}"
""",

    "kubernetes": """
DIAGRAM TYPE: Kubernetes / Container Architecture
FOCUS: Cluster topology, workloads, and service mesh.
SHOW:
  - Cluster control plane and worker node pools
  - Namespaces and their workloads (Deployments, StatefulSets)
  - Ingress controller and external load balancer
  - Horizontal Pod Autoscaler and Cluster Autoscaler
  - Service mesh (Istio/Linkerd) if applicable
  - Persistent volumes and storage classes
  - ConfigMaps, Secrets, and RBAC
STYLE: Cluster boundary as outer box. Namespace boxes inside. Pod icons inside namespaces.
TITLE: "Kubernetes Architecture — {CLOUD}"
""",

    "migration_wave": """
DIAGRAM TYPE: Migration Wave Design
FOCUS: Application grouping, migration batches, and timeline.
SHOW:
  - Wave 1: Non-critical / low-risk applications
  - Wave 2: Internal APIs and middleware
  - Wave 3: Customer-facing systems
  - Dependencies between applications (arrows)
  - Migration strategy per app (Rehost/Replatform/Refactor)
  - Timeline estimates per wave
  - Source (on-prem) → Target (cloud) mapping
STYLE: Swimlane layout with waves as horizontal bands. Color-code by risk level.
TITLE: "Migration Wave Plan — {CLOUD}"
""",

    "data_flow": """
DIAGRAM TYPE: Data Flow Design
FOCUS: How data moves through the system.
SHOW:
  - Data sources (databases, APIs, files, streams)
  - ETL/ELT pipelines (Glue, Data Factory, Dataflow)
  - Message queues and event streams (Kafka, SQS, Event Hubs)
  - Data warehouses and analytics (Redshift, Synapse, BigQuery)
  - Replication paths and CDC (Change Data Capture)
  - Data classification labels (PII, confidential, public)
STYLE: Flow-oriented — left to right. Use thick arrows for high-volume flows.
TITLE: "Data Flow Architecture — {CLOUD}"
""",

    "observability": """
DIAGRAM TYPE: Observability Architecture
FOCUS: Monitoring, logging, tracing, and alerting.
SHOW:
  - Metrics collection (CloudWatch, Prometheus, Azure Monitor)
  - Log aggregation (CloudWatch Logs, Log Analytics, Cloud Logging)
  - Distributed tracing (X-Ray, Jaeger, Cloud Trace)
  - Dashboards (Grafana, CloudWatch Dashboards)
  - Alerting and notification (SNS, PagerDuty, OpsGenie)
  - APM tools (Datadog, New Relic)
  - Log retention and archival
STYLE: Hub-and-spoke — observability tools in center, monitored services around them.
TITLE: "Observability Architecture — {CLOUD}"
""",

    "landing_zone": """
DIAGRAM TYPE: Landing Zone Design
FOCUS: Enterprise cloud foundation — multi-account strategy and governance.
SHOW:
  - Management/Root account and organizational units (OUs)
  - Security account (GuardDuty, Security Hub, CloudTrail)
  - Log archive account
  - Shared services account (DNS, AD, Transit Gateway)
  - Workload accounts (dev, staging, prod)
  - SCPs and guardrails
  - Identity federation (SSO, Azure AD, Okta)
  - Centralized logging and monitoring baseline
STYLE: Org hierarchy tree at top. Account boxes below with their services.
TITLE: "Landing Zone Design — {CLOUD}"
""",

    "as_is": """
DIAGRAM TYPE: Current State Architecture (As-Is)
FOCUS: Existing on-premises or legacy infrastructure before migration.
SHOW:
  - Physical/virtual servers and their roles
  - Existing databases and storage systems
  - Network topology (firewalls, switches, load balancers)
  - Application dependencies and integrations
  - Current pain points (single points of failure, bottlenecks)
  - Data center zones
STYLE: Use generic server/database icons. Show on-prem data center boundary.
TITLE: "Current State Architecture (As-Is)"
""",

    "to_be": """
DIAGRAM TYPE: Future State Architecture (To-Be) — Cloud Migration Target
FOCUS: CONVERT the current architecture to the TARGET CLOUD. Do NOT use the source cloud services.

CRITICAL RULE: The source document describes the CURRENT state (which may be on a DIFFERENT cloud or on-premises).
Your job is to MAP every component to its EQUIVALENT on the TARGET CLOUD PROVIDER specified in the icon guide above.
Use ONLY icons from the TARGET cloud provider. NEVER render source cloud icons.

COMPREHENSIVE MIGRATION MAPPING:

AWS → Azure:
  EC2 → Virtual Machine / VMSS
  EKS → AKS (Azure Kubernetes Service)
  ECS/Fargate → Azure Container Apps / ACI
  Lambda → Azure Functions
  ALB → Application Gateway
  NLB → Azure Load Balancer
  CloudFront → Azure Front Door / CDN
  Route53 → Azure DNS
  API Gateway → Azure API Management (APIM)
  VPC → Virtual Network (VNet)
  Subnets → Subnets
  NAT Gateway → Azure NAT Gateway
  Internet Gateway → (implicit in VNet)
  Transit Gateway → Azure Virtual WAN
  Direct Connect → ExpressRoute
  VPN → Azure VPN Gateway
  Security Groups → NSG (Network Security Groups)
  NACLs → Azure Firewall / NSG
  WAF → Azure WAF
  Shield → Azure DDoS Protection
  RDS → Azure SQL Database / Azure Database for PostgreSQL/MySQL
  Aurora → Azure SQL Hyperscale
  DynamoDB → Cosmos DB
  ElastiCache → Azure Cache for Redis
  OpenSearch → Azure Cognitive Search
  S3 → Azure Blob Storage
  EFS → Azure Files
  EBS → Azure Managed Disks
  Glacier → Azure Archive Storage
  IAM → Azure Active Directory / Entra ID
  IAM Roles → Managed Identities
  KMS → Azure Key Vault
  Secrets Manager → Azure Key Vault (Secrets)
  Cognito → Azure AD B2C
  CloudWatch → Azure Monitor
  CloudWatch Logs → Azure Log Analytics
  X-Ray → Application Insights
  CloudTrail → Azure Activity Log
  SNS → Azure Notification Hubs / Event Grid
  SQS → Azure Queue Storage / Service Bus
  EventBridge → Azure Event Grid
  Step Functions → Azure Logic Apps / Durable Functions
  Kinesis → Azure Event Hubs
  MSK (Kafka) → Azure Event Hubs for Kafka
  Glue → Azure Data Factory
  Redshift → Azure Synapse Analytics
  Athena → Azure Synapse Serverless
  ECR → Azure Container Registry (ACR)
  CodePipeline → Azure DevOps Pipelines
  CodeBuild → Azure DevOps Build
  Config → Azure Policy
  GuardDuty → Microsoft Defender for Cloud
  Security Hub → Microsoft Defender for Cloud
  Backup → Azure Backup
  Auto Scaling → Azure VMSS Autoscale / AKS HPA

AWS → GCP:
  EC2 → Compute Engine (GCE)
  EKS → Google Kubernetes Engine (GKE)
  ECS/Fargate → Cloud Run
  Lambda → Cloud Functions
  ALB → Cloud Load Balancing (HTTP/S LB)
  NLB → Cloud Load Balancing (TCP/UDP LB)
  CloudFront → Cloud CDN
  Route53 → Cloud DNS
  API Gateway → Apigee / Cloud Endpoints
  VPC → VPC Network
  Subnets → Subnets
  NAT Gateway → Cloud NAT
  Internet Gateway → (implicit)
  Transit Gateway → Cloud Interconnect / Cloud Router
  Direct Connect → Cloud Interconnect
  VPN → Cloud VPN
  Security Groups → Firewall Rules
  WAF → Cloud Armor
  RDS → Cloud SQL
  Aurora → Cloud SQL / AlloyDB
  DynamoDB → Firestore / Bigtable
  ElastiCache → Memorystore
  OpenSearch → Elasticsearch on GCE
  S3 → Cloud Storage (GCS)
  EFS → Filestore
  EBS → Persistent Disk
  Glacier → Cloud Storage Archive
  IAM → Cloud IAM
  KMS → Cloud KMS
  Secrets Manager → Secret Manager
  Cognito → Identity Platform
  CloudWatch → Cloud Monitoring
  CloudWatch Logs → Cloud Logging
  X-Ray → Cloud Trace
  CloudTrail → Cloud Audit Logs
  SNS → Pub/Sub
  SQS → Pub/Sub (pull subscription)
  EventBridge → Eventarc
  Step Functions → Workflows
  Kinesis → Pub/Sub / Dataflow
  MSK (Kafka) → Pub/Sub
  Glue → Dataflow / Dataproc
  Redshift → BigQuery
  Athena → BigQuery
  ECR → Artifact Registry
  CodePipeline → Cloud Build
  Config → Organization Policy
  GuardDuty → Security Command Center
  Security Hub → Security Command Center
  Backup → Cloud Backup and DR
  Auto Scaling → Managed Instance Groups / GKE HPA

Azure → AWS:
  Virtual Machine / VMSS → EC2 / Auto Scaling Group
  AKS → EKS
  Container Apps / ACI → ECS Fargate
  Azure Functions → Lambda
  Application Gateway → ALB
  Azure Load Balancer → NLB
  Front Door → CloudFront
  Azure DNS → Route53
  APIM → API Gateway
  VNet → VPC
  NSG → Security Groups
  Azure Firewall → Network Firewall
  Azure WAF → AWS WAF
  DDoS Protection → AWS Shield
  ExpressRoute → Direct Connect
  VPN Gateway → Site-to-Site VPN
  Virtual WAN → Transit Gateway
  Azure SQL → RDS (PostgreSQL/MySQL/SQL Server)
  Cosmos DB → DynamoDB
  Azure Cache for Redis → ElastiCache
  Blob Storage → S3
  Azure Files → EFS
  Managed Disks → EBS
  Azure AD / Entra ID → IAM + Cognito
  Managed Identity → IAM Roles
  Key Vault → KMS + Secrets Manager
  Azure Monitor → CloudWatch
  Log Analytics → CloudWatch Logs
  Application Insights → X-Ray
  Activity Log → CloudTrail
  Service Bus → SQS + SNS
  Event Grid → EventBridge
  Event Hubs → Kinesis
  Logic Apps → Step Functions
  Data Factory → Glue
  Synapse → Redshift
  ACR → ECR
  Azure DevOps → CodePipeline + CodeBuild
  Azure Policy → AWS Config
  Defender for Cloud → GuardDuty + Security Hub
  Azure Backup → AWS Backup

Azure → GCP:
  Virtual Machine → Compute Engine
  AKS → GKE
  Container Apps → Cloud Run
  Azure Functions → Cloud Functions
  Application Gateway → Cloud Load Balancing
  Front Door → Cloud CDN
  Azure DNS → Cloud DNS
  APIM → Apigee
  VNet → VPC Network
  NSG → Firewall Rules
  Azure Firewall → Cloud Armor
  Azure SQL → Cloud SQL
  Cosmos DB → Firestore
  Azure Cache for Redis → Memorystore
  Blob Storage → Cloud Storage
  Key Vault → Cloud KMS + Secret Manager
  Azure Monitor → Cloud Monitoring
  Log Analytics → Cloud Logging
  Application Insights → Cloud Trace
  Service Bus → Pub/Sub
  Event Hubs → Pub/Sub
  Data Factory → Dataflow
  Synapse → BigQuery
  ACR → Artifact Registry
  Azure DevOps → Cloud Build
  Defender for Cloud → Security Command Center

GCP → AWS:
  Compute Engine → EC2
  GKE → EKS
  Cloud Run → ECS Fargate
  Cloud Functions → Lambda
  Cloud Load Balancing → ALB/NLB
  Cloud CDN → CloudFront
  Cloud DNS → Route53
  Apigee → API Gateway
  VPC Network → VPC
  Firewall Rules → Security Groups
  Cloud Armor → WAF + Shield
  Cloud SQL → RDS
  Firestore → DynamoDB
  Bigtable → DynamoDB
  Memorystore → ElastiCache
  Cloud Storage → S3
  Filestore → EFS
  Cloud IAM → IAM
  Cloud KMS → KMS
  Secret Manager → Secrets Manager
  Cloud Monitoring → CloudWatch
  Cloud Logging → CloudWatch Logs
  Cloud Trace → X-Ray
  Pub/Sub → SNS + SQS
  Dataflow → Kinesis + Glue
  BigQuery → Redshift
  Artifact Registry → ECR
  Cloud Build → CodePipeline
  Security Command Center → GuardDuty + Security Hub

GCP → Azure:
  Compute Engine → Virtual Machine
  GKE → AKS
  Cloud Run → Container Apps
  Cloud Functions → Azure Functions
  Cloud Load Balancing → Application Gateway
  Cloud CDN → Front Door
  Cloud DNS → Azure DNS
  Apigee → APIM
  VPC Network → VNet
  Firewall Rules → NSG
  Cloud Armor → Azure WAF + DDoS Protection
  Cloud SQL → Azure SQL
  Firestore → Cosmos DB
  Memorystore → Azure Cache for Redis
  Cloud Storage → Blob Storage
  Cloud KMS → Key Vault
  Secret Manager → Key Vault
  Cloud Monitoring → Azure Monitor
  Cloud Logging → Log Analytics
  Cloud Trace → Application Insights
  Pub/Sub → Service Bus + Event Grid
  BigQuery → Synapse Analytics
  Artifact Registry → ACR
  Cloud Build → Azure DevOps
  Security Command Center → Defender for Cloud

On-Premises → Any Cloud:
  Physical Servers → VMs or Containers
  VMware vSphere → Cloud VMs or Kubernetes
  Oracle Database → Managed Database (RDS/Azure SQL/Cloud SQL)
  SQL Server → Managed SQL (RDS SQL/Azure SQL/Cloud SQL)
  MySQL/PostgreSQL → Managed DB service
  MongoDB → DocumentDB/Cosmos DB/Firestore
  F5 Load Balancer → Cloud Load Balancer
  Cisco ASA Firewall → Cloud Firewall/WAF
  NetApp Storage → Cloud File Storage
  NFS → Managed File Storage (EFS/Azure Files/Filestore)
  Active Directory → Cloud IAM + Identity Federation
  Nagios/Zabbix → Cloud Monitoring
  Jenkins → Cloud CI/CD (CodePipeline/Azure DevOps/Cloud Build)
  RabbitMQ → Managed Message Queue
  Kafka → Managed Kafka/Event Streaming
  HAProxy/Nginx → Cloud Load Balancer
  Backup Tapes → Cloud Backup + Archive Storage

SHOW:
  - Target cloud services (NOT the source cloud services)
  - Use ONLY icons from the TARGET cloud provider specified in the icon guide
  - Network topology in the target cloud (VPC/VNet, subnets, security groups)
  - HA/DR improvements over the current state
  - A "Migration Mapping" legend showing key source → target conversions
STYLE: Use ONLY the target cloud provider icons. Show migration benefits in a legend.
TITLE: "Future State Architecture (To-Be) — {CLOUD} Migration Target"
""",

    "custom": """
DIAGRAM TYPE: Custom Architecture (User-Defined)
FOCUS: Generate exactly what the user describes in their instruction.
SHOW: Follow the user's instruction precisely. Include all mentioned services and components.
STYLE: Use appropriate cloud provider icons. Apply standard tier bands.
TITLE: Based on the user's instruction.
""",
}

# Default to HLD if type not recognized
DIAGRAM_TYPE_GUIDES["default"] = DIAGRAM_TYPE_GUIDES["hld"]


class DiagramGenerator:
    """
    LangGraph-based diagram generator.
    Produces draw.io XML directly via LLM — no manual stencil mapping.
    """

    def __init__(self):
        # Aligned with the shared bedrock_client factory: 180s read covers P99
        # of 16K-token diagram generations, and we set retries=0 because the
        # LLMGateway fallback chain (sonnet→haiku→gemini) owns retry policy.
        # Without this, a stuck stream would silently retry up to 3 times.
        from botocore.config import Config as BotoConfig
        self._llm = ChatBedrock(
            model_id=settings.AWS_BEDROCK_MODEL,
            region_name=settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            model_kwargs={"max_tokens": 16000},
            config=BotoConfig(
                read_timeout=180,
                connect_timeout=10,
                retries={'max_attempts': 0, 'mode': 'standard'},
            ),
        )
        self._graph = self._build_graph()

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, file_path: str, provider: str = "aws", diagram_type: str = "hld", custom_instruction: str = "") -> dict:
        """Run the full pipeline for a given file, cloud provider, and diagram type."""
        result = self._graph.invoke({
            "file_path": file_path,
            "provider": provider.lower(),
            "diagram_type": diagram_type.lower(),
            "custom_instruction": custom_instruction,
            "raw_text": "",
            "drawio_xml": "",
            "components": [],
            "error": None,
        })
        return {
            "drawio_xml": result["drawio_xml"],
            "components": result["components"],
            "error": result.get("error"),
        }

    # ── Node 1: extract text ──────────────────────────────────────────────────

    def _extract_text(self, state: DiagramState) -> DiagramState:
        """Use the unified helper to extract markdown text (Docling-first).

        For image files (PNG/JPG/SVG), skip text extraction since Docling
        can't parse them — the diagram will be generated from the filename
        and any metadata available.
        """
        file_path = state["file_path"]
        ext = Path(file_path).suffix.lower()

        # Image files can't be text-extracted — use filename as context
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
            filename = Path(file_path).stem.replace('_', ' ').replace('-', ' ')
            text = f"Architecture diagram image: {filename}\nFile type: {ext}\nGenerate a comprehensive architecture diagram based on the filename and common cloud patterns."
            logger.info(f"[DiagramGenerator] Image file detected ({ext}), using filename as context")
            return {**state, "raw_text": text}

        try:
            from app.utils.document_extract import extract_document
            extracted = extract_document(file_path, extract_images=False)
            if extracted.text:
                logger.info(
                    f"[DiagramGenerator] method={extracted.method} | chars={len(extracted.text)}"
                )
                return {**state, "raw_text": extracted.text}
            # Empty extraction: try a final raw read so we still have something to show.
            text = Path(file_path).read_text(errors="ignore")[:12000]
            return {**state, "raw_text": text}
        except Exception as e:
            logger.warning(f"[DiagramGenerator] Extraction failed ({e}), falling back to raw read")
            try:
                text = Path(file_path).read_text(errors="ignore")[:12000]
                return {**state, "raw_text": text}
            except Exception as e2:
                return {**state, "error": f"Text extraction failed: {e2}"}

    # ── Node 2: generate draw.io XML ──────────────────────────────────────────

    def _generate_xml(self, state: DiagramState) -> DiagramState:
        """Ask Claude to generate a complete draw.io mxGraphModel XML."""
        if state.get("error"):
            return state

        provider     = state["provider"]
        diagram_type = state.get("diagram_type", "hld")
        custom_instruction = state.get("custom_instruction", "")
        icon_guide   = PROVIDER_GUIDE.get(provider, PROVIDER_GUIDE["aws"])
        type_guide   = DIAGRAM_TYPE_GUIDES.get(diagram_type, DIAGRAM_TYPE_GUIDES["hld"])
        prov_upper   = provider.upper()

        # For custom diagrams, use the instruction as the document
        if diagram_type == "custom" and custom_instruction:
            text = f"USER INSTRUCTION:\n{custom_instruction}"
        else:
            text = state["raw_text"][:9000]

        prompt = f"""You are a senior cloud architect generating a PRODUCTION-STANDARD draw.io architecture diagram.
The output must match the quality of AWS Well-Architected diagrams, Azure reference architectures, and GCP solution diagrams.

━━━ DIAGRAM TYPE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{type_guide}

━━━ SOURCE DOCUMENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━
{text}

━━━ {prov_upper} ICON REFERENCE ━━━━━━━━━━━━━━━━━━━━━━━
{icon_guide}

━━━ PRODUCTION DIAGRAM STANDARDS ━━━━━━━━━━━━━━
Follow these EXACT standards used in enterprise architecture diagrams:

1. PAGE SETUP
   pageWidth="2400" pageHeight="1800" background="#F8FAFC"
   grid="1" gridSize="10"

2. ZONE CONTAINERS (parent="1", absolute coordinates)
   Each major zone is a large rounded rectangle:
   style="rounded=1;arcSize=2;whiteSpace=wrap;html=1;
          fillColor=#EFF6FF;strokeColor=#3B82F6;strokeWidth=2;
          fontStyle=1;fontSize=14;fontColor=#1E40AF;
          verticalAlign=top;align=left;spacingLeft=16;spacingTop=10;
          container=1;collapsible=0;"
   
   Zone color scheme:
   - Internet/Public:    fillColor=#FFF7ED; strokeColor=#F97316; fontColor=#C2410C
   - Edge/Perimeter:     fillColor=#FDF4FF; strokeColor=#A855F7; fontColor=#7E22CE
   - Application/Compute: fillColor=#EFF6FF; strokeColor=#3B82F6; fontColor=#1E40AF
   - Data/Storage:       fillColor=#F0FDF4; strokeColor=#22C55E; fontColor=#15803D
   - Security/Identity:  fillColor=#FFF1F2; strokeColor=#F43F5E; fontColor=#BE123C
   - Management/Ops:     fillColor=#F0FDFA; strokeColor=#14B8A6; fontColor=#0F766E
   - On-Premises:        fillColor=#F9FAFB; strokeColor=#6B7280; fontColor=#374151

3. SUB-ZONE CONTAINERS (parent=ZONE_ID, coordinates RELATIVE to parent)
   style="swimlane;startSize=30;fillColor=#FFFFFF;strokeColor=#CBD5E1;
          strokeWidth=1.5;fontStyle=1;fontSize=11;fontColor=#334155;
          rounded=1;arcSize=4;container=1;collapsible=0;"
   IMPORTANT: x,y coordinates are RELATIVE to the parent container

4. SERVICE ICONS (parent=SUBZONE_ID or ZONE_ID, coordinates RELATIVE to parent)
   AWS:   shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{{ICON}};
          fillColor={{COLOR}};strokeColor=#ffffff;
          fontStyle=1;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;
          width="56" height="56"
   Azure: shape=mxgraph.azure.{{ICON}};fillColor={{COLOR}};strokeColor=#ffffff;
          fontStyle=1;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;
          width="56" height="56"
   GCP:   shape=mxgraph.gcp2.{{ICON}};fillColor={{COLOR}};strokeColor=#ffffff;
          fontStyle=1;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;
          width="56" height="56"

5. CONNECTIONS (parent="1", absolute coordinates)
   style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;
          jettySize=auto;exitX=1;exitY=0.5;entryX=0;entryY=0.5;
          strokeColor=#64748B;strokeWidth=2;endArrow=block;endFill=1;"
   Add value="HTTPS:443" or "TCP:5432" labels on connections

6. TITLE (parent="1")
   style="text;html=1;strokeColor=none;fillColor=none;
          align=left;verticalAlign=middle;whiteSpace=wrap;
          fontSize=20;fontStyle=1;fontColor=#0F172A;"
   Place at x="60" y="20" width="800" height="40"

7. LEGEND (parent="1", bottom-left)
   style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;
          strokeColor=#E2E8F0;fontSize=11;align=left;
          verticalAlign=top;spacingLeft=10;spacingTop=8;"
   Show: zone colors + service categories + compliance frameworks

━━━ CONCRETE XML EXAMPLE (follow this pattern exactly) ━━━━━━━━━━━━━━━━━━━━━━━
<mxCell id="10" value="APPLICATION ZONE" vertex="1" parent="1"
  style="rounded=1;arcSize=2;fillColor=#EFF6FF;strokeColor=#3B82F6;strokeWidth=2;
         fontStyle=1;fontSize=14;fontColor=#1E40AF;verticalAlign=top;align=left;
         spacingLeft=16;spacingTop=10;container=1;collapsible=0;"
  <mxGeometry x="60" y="300" width="900" height="400" as="geometry" />
</mxCell>

<mxCell id="11" value="COMPUTE TIER" vertex="1" parent="10"
  style="swimlane;startSize=30;fillColor=#FFFFFF;strokeColor=#CBD5E1;
         strokeWidth=1.5;fontStyle=1;fontSize=11;fontColor=#334155;
         rounded=1;arcSize=4;container=1;collapsible=0;"
  <mxGeometry x="20" y="50" width="400" height="300" as="geometry" />
</mxCell>

<mxCell id="12" value="EKS Cluster" vertex="1" parent="11"
  style="shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.eks;
         fillColor=#ED7100;strokeColor=#ffffff;fontStyle=1;fontSize=10;
         verticalLabelPosition=bottom;verticalAlign=top;align=center;"
  <mxGeometry x="30" y="50" width="56" height="56" as="geometry" />
</mxCell>

<mxCell id="20" edge="1" source="12" target="30" parent="1"
  style="edgeStyle=orthogonalEdgeStyle;rounded=1;strokeColor=#64748B;
         strokeWidth=2;endArrow=block;endFill=1;"
  value="HTTPS:443"
  <mxGeometry relative="1" as="geometry" />
</mxCell>

━━━ WHAT TO GENERATE ━━━━━━━━━━━━━━━━━━━━━━━━━━
Based on the source document, create a COMPLETE diagram with:
- ALL services mentioned in the document
- Proper zone grouping (Internet → Edge → App → Data → Security → Ops)
- Connections between services with protocol labels
- Compliance/governance annotations if mentioned
- Naming conventions from the document
- HA/DR indicators (Multi-AZ, replication arrows)
- A professional title and legend

━━━ OUTPUT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY the XML, wrapped in tags. No explanation, no markdown:

<DRAWIO_XML>
<mxGraphModel dx="1422" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2400" pageHeight="1800" background="#F8FAFC">
  <root>
    <mxCell id="0" />
    <mxCell id="1" parent="0" />
    <!-- Generate ALL cells here. Zone containers first (parent="1"), then sub-zones (parent=zone_id), then icons (parent=subzone_id), then edges (parent="1"). Use integer IDs from 2. -->
  </root>
</mxGraphModel>
</DRAWIO_XML>"""

        try:
            # Route through LLM Gateway for caching, circuit breaking, and budget tracking.
            # Architecture diagrams are expensive (16K tokens) — caching saves significant cost.
            try:
                from app.core.llm_gateway import get_gateway
                raw = get_gateway().call(
                    messages=[{"role": "user", "content": prompt}],
                    task_type="architecture_diagram",
                    max_tokens=16000,
                    context=f"{provider}:{diagram_type}:{state['raw_text'][:200]}",
                )
            except Exception as gw_err:
                logger.warning(f"[DiagramGenerator] Gateway failed, falling back to ChatBedrock: {gw_err}")
                response = self._llm.invoke([HumanMessage(content=prompt)])
                raw = response.content

            # Parse XML between tags — try multiple patterns since LLMs sometimes
            # wrap the XML in markdown fences or use slightly different tag names.
            m = re.search(r'<DRAWIO_XML>([\s\S]*?)</DRAWIO_XML>', raw, re.IGNORECASE)
            if not m:
                m = re.search(r'(<mxGraphModel[\s\S]*?</mxGraphModel>)', raw)
            if not m:
                # Try markdown code fence: ```xml ... ``` or ``` ... ```
                m = re.search(r'```(?:xml)?\s*\n([\s\S]*?)\n```', raw)
                if m and '<mxGraphModel' in m.group(1):
                    m = re.search(r'(<mxGraphModel[\s\S]*?</mxGraphModel>)', m.group(1))
            if not m:
                # Last resort: find anything that looks like mxGraphModel XML
                m = re.search(r'(<mxGraphModel[^>]*>[\s\S]{100,}?</mxGraphModel>)', raw)

            if m:
                xml = m.group(1).strip()
                # Sanitize: remove duplicate attributes on mxCell elements
                xml = self._sanitize_xml(xml)
                logger.info(f"[DiagramGenerator] XML generated: {len(xml)} chars | type={diagram_type}")
                return {**state, "drawio_xml": xml}

            # Log a snippet of what the LLM actually returned for debugging
            logger.error(f"[DiagramGenerator] No XML found in LLM response. First 500 chars: {raw[:500]}")
            return {**state, "error": "LLM did not return valid draw.io XML"}

        except Exception as e:
            logger.error(f"[DiagramGenerator] XML generation failed: {e}")
            return {**state, "error": str(e)}

    # ── Node 3: extract components for Terraform ──────────────────────────────

    def _extract_components(self, state: DiagramState) -> DiagramState:
        """Extract structured component list for master_context / Terraform pipeline."""
        if not state.get("raw_text") or state.get("error") or not state.get("drawio_xml"):
            return state

        provider = state["provider"]
        text     = state["raw_text"][:6000]

        prompt = f"""Extract all {provider.upper()} infrastructure components from this document.
Return ONLY a valid JSON array — no markdown fences, no explanation.

Schema per item:
  id, service, label, type, configuration (object with cidr/instance_type/engine etc.), confidence (0-1)

Example:
[
  {{"id": "vpc-main", "service": "vpc", "label": "Main VPC", "type": "network",
    "configuration": {{"cidr": "10.0.0.0/16"}}, "confidence": 0.95}},
  {{"id": "eks-cluster", "service": "eks", "label": "EKS Cluster", "type": "compute",
    "configuration": {{"version": "1.29", "node_count": 3}}, "confidence": 0.92}}
]

DOCUMENT:
{text}"""

        try:
            try:
                from app.core.llm_gateway import get_gateway
                raw = get_gateway().call(
                    messages=[{"role": "user", "content": prompt}],
                    task_type="component_extraction",
                    max_tokens=2000,
                    context=f"{provider}:{text[:200]}",
                )
            except Exception as gw_err:
                logger.warning(f"[DiagramGenerator] Gateway failed for component extraction: {gw_err}")
                response = self._llm.invoke([HumanMessage(content=prompt)])
                raw = response.content

            cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r'```\s*$', '', cleaned.strip()).strip()
            m = re.search(r'\[[\s\S]*\]', cleaned)
            components = json.loads(m.group()) if m else []
            logger.info(f"[DiagramGenerator] Extracted {len(components)} components for master_context")
            return {**state, "components": components}
        except Exception as e:
            logger.warning(f"[DiagramGenerator] Component extraction failed (non-fatal): {e}")
            return state

    @staticmethod
    def _sanitize_xml(xml: str) -> str:
        """Fix common XML issues that cause draw.io to reject the file.

        Problems Claude sometimes generates:
        1. Duplicate attributes on the same element (e.g., two style= attributes)
        2. Unescaped & characters in attribute values
        3. Invalid XML characters
        4. Missing root mxCell elements (id=0 and id=1)
        """
        import re as _re
        import xml.etree.ElementTree as ET

        # Try to parse as valid XML first — if it works, it's already clean
        try:
            ET.fromstring(xml)
            return xml
        except ET.ParseError:
            pass

        # Fix 1: Remove duplicate attributes using regex
        def dedup_attrs(tag_match):
            tag = tag_match.group(0)
            attr_pattern = _re.compile(r'([\w:.-]+)\s*=\s*"([^"]*?)"')
            seen = {}
            for m in attr_pattern.finditer(tag):
                name = m.group(1)
                value = m.group(2)
                seen[name] = value

            tag_name_match = _re.match(r'<([\w:.-]+)', tag)
            if not tag_name_match:
                return tag
            tag_name = tag_name_match.group(1)
            attrs_str = ' '.join(f'{k}="{v}"' for k, v in seen.items())
            self_close = '/>' if tag.rstrip().endswith('/>') else '>'
            return f'<{tag_name} {attrs_str}{self_close}'

        xml = _re.sub(r'<[\w:.-]+(?:\s+[\w:.-]+\s*=\s*"[^"]*?")+\s*/?>', dedup_attrs, xml)

        # Fix 2: Escape bare & in text content (not in attributes, not already escaped)
        xml = _re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)', '&amp;', xml)

        # Fix 3: Ensure root mxCell elements exist
        if '<mxCell id="0"' not in xml and '<root>' in xml:
            xml = xml.replace('<root>', '<root>\n    <mxCell id="0" />\n    <mxCell id="1" parent="0" />')

        # Fix 4: Update page dimensions to match new larger canvas
        import re as _re2
        xml = _re2.sub(r'pageWidth="\d+"', 'pageWidth="2200"', xml)
        xml = _re2.sub(r'pageHeight="\d+"', 'pageHeight="1600"', xml)

        # Verify it parses now
        try:
            ET.fromstring(xml)
        except ET.ParseError as e:
            logger.warning(f"[DiagramGenerator] XML still invalid after sanitization: {e}")
            # Last resort: try to extract just the valid portion
            valid_match = _re.search(r'(<mxGraphModel[\s\S]*?</mxGraphModel>)', xml)
            if valid_match:
                xml = valid_match.group(1)

        return xml

    # ── Build LangGraph ───────────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(DiagramState)
        g.add_node("extract_text",       self._extract_text)
        g.add_node("generate_xml",       self._generate_xml)
        g.add_node("extract_components", self._extract_components)

        g.set_entry_point("extract_text")
        g.add_edge("extract_text",       "generate_xml")
        g.add_edge("generate_xml",       "extract_components")
        g.add_edge("extract_components", END)

        return g.compile()
