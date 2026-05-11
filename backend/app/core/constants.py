# Supported cloud providers
SUPPORTED_PROVIDERS = ["aws", "gcp", "azure"]

# Supported file formats
SUPPORTED_FILE_FORMATS = [".png", ".jpg", ".jpeg", ".pdf", ".svg", ".drawio", ".lucidchart"]

# Job statuses
JOB_STATUSES = ["pending", "processing", "completed", "failed"]

# Workflow steps
WORKFLOW_STEPS = ["upload", "analyse", "design", "terraform"]

# Resource categories
RESOURCE_CATEGORIES = {
    "compute": ["ec2", "lambda", "gce", "cloud_run", "vm"],
    "storage": ["s3", "ebs", "cloud_storage", "blob_storage"],
    "database": ["rds", "dynamodb", "cloud_sql", "cosmos_db"],
    "network": ["vpc", "subnet", "load_balancer", "cdn"],
    "security": ["iam", "security_group", "firewall", "kms"]
}
