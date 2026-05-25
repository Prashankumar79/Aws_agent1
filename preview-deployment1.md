# InfraSketch — Holistic AWS Deployment Guide with GitHub Actions CI/CD

> **Architecture:** FastAPI Backend (ECS Fargate) + Vite React Frontend (S3 + CloudFront)  
> **CI/CD:** GitHub Actions → Amazon ECR → ECS Fargate + S3  
> **MLOps:** Secrets Manager, Model Versioning, Health Checks, CloudWatch, Auto-rollback  
> **Last Updated:** May 2026

---

## Table of Contents

1. [Why AWS?](#1-why-aws)
2. [Architecture Overview](#2-architecture-overview)
3. [Prerequisites](#3-prerequisites)
4. [AWS Account & IAM Setup](#4-aws-account--iam-setup)
5. [Network Foundation (VPC)](#5-network-foundation-vpc)
6. [Secrets Management](#6-secrets-management)
7. [Persistent Storage](#7-persistent-storage)
8. [Container Registry (ECR)](#8-container-registry-ecr)
9. [Backend Deployment (ECS Fargate)](#9-backend-deployment-ecs-fargate)
10. [Frontend Deployment (S3 + CloudFront)](#10-frontend-deployment-s3--cloudfront)
11. [CI/CD Pipeline (GitHub Actions)](#11-cicd-pipeline-github-actions)
12. [MLOps & Production Practices](#12-mlops--production-practices)
13. [Monitoring & Observability](#13-monitoring--observability)
14. [Rollback & Disaster Recovery](#14-rollback--disaster-recovery)
15. [Cost Optimization](#15-cost-optimization)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Why AWS?

| Advantage | Explanation |
|-----------|-------------|
| **Bedrock Co-location** | Backend and Claude/Gemini APIs are in the same cloud → lower latency, no egress costs |
| **Native AI Stack** | Bedrock, SageMaker, Textract, Comprehend all in one account |
| **Mature Container Platform** | ECS Fargate is battle-tested for Python/FastAPI workloads |
| **Serverless Frontends** | S3 + CloudFront is cheaper and faster than running a container for static files |
| **Unified Billing** | One bill for compute, storage, AI, and networking |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub (Source)                                │
│                        ┌────────────────────┐                               │
│                        │   GitHub Actions   │                               │
│                        │  CI/CD Pipeline    │                               │
│                        └────────┬───────────┘                               │
└─────────────────────────────────┼───────────────────────────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
              ▼                                       ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│      Amazon ECR               │       │         S3 Bucket             │
│  ┌──────────────────────┐    │       │    ┌──────────────────┐     │
│  │  infrasketch/backend │    │       │    │  Static React    │     │
│  │  infrasketch/frontend│    │       │    │  Build Output    │     │
│  └──────────────────────┘    │       │    └──────────────────┘     │
└──────────────┬────────────────┘       └──────────────┬──────────────┘
               │                                        │
               ▼                                        ▼
┌────────────────────────────────────┐    ┌───────────────────────────────┐
│         ECS Fargate                │    │         CloudFront            │
│   ┌────────────────────────┐       │    │    ┌──────────────────┐     │
│   │  Task Definition       │       │    │    │  CDN Edge Cache    │     │
│   │  ┌──────────────────┐  │       │    │    │  SSL / HTTPS       │     │
│   │  │  FastAPI Container│  │       │    │    │  Custom Domain     │     │
│   │  │  :8080            │  │       │    │    └──────────────────┘     │
│   │  └──────────────────┘  │       │    └───────────────────────────────┘
│   │         │              │       │
│   │    ┌────┴────┐         │       │         User Browser
│   │    ▼         ▼         │       │              │
│   │ ┌─────┐  ┌────────┐   │       │              ▼
│   │ │ ALB │  │ Secrets│   │       │    ┌─────────────────────┐
│   │ │     │  │ Manager│   │       │    │  app.infrasketch.io │
│   │ └─────┘  └────────┘   │       │    │  React SPA + API    │
│   └────────────────────────┘       │    └─────────────────────┘
│               │
│    ┌──────────┴──────────┐
│    ▼                     ▼
│ ┌──────────┐      ┌──────────┐
│ │ DynamoDB │      │ CloudWatch│
│ │ (Jobs)   │      │ (Logs/Metrics)
│ └──────────┘      └──────────┘
└────────────────────────────────────┘
```

### Service Breakdown

| Layer | Service | Purpose |
|-------|---------|---------|
| Compute | **ECS Fargate** | Serverless container running FastAPI backend |
| Load Balancer | **ALB** | HTTP/HTTPS routing, health checks, SSL termination |
| Frontend | **S3 + CloudFront** | Static React SPA with global CDN |
| Registry | **ECR** | Docker image storage |
| Database | **DynamoDB** | Persistent job state (replaces in-memory `_jobs`) |
| File Storage | **S3** | Uploaded architecture diagrams |
| Secrets | **Secrets Manager** | API keys, AWS credentials |
| CI/CD | **GitHub Actions** | Build → Test → Push → Deploy |
| Monitoring | **CloudWatch** | Logs, metrics, alarms, dashboards |
| VPC | **VPC + Subnets + Security Groups** | Network isolation |

---

## 3. Prerequisites

### 3.1 Required Accounts

- [ ] **AWS Account** (free tier available for 12 months)
- [ ] **GitHub Account** (for source control + Actions)
- [ ] **Domain Name** (optional — for custom HTTPS with CloudFront)

### 3.2 Local Tools

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Verify
$ aws --version
aws-cli/2.15.0

# Install Docker
https://docs.docker.com/get-docker/
```

### 3.3 Required API Keys

| Secret | Source | How to Get |
|--------|--------|-----------|
| `GEMINI_API_KEY` | Google AI Studio | https://aistudio.google.com/app/apikey |
| `AWS_ACCESS_KEY_ID` | AWS IAM | Create IAM user with required permissions |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM | Download during key creation |

---

## 4. AWS Account & IAM Setup

### 4.1 Create IAM User for CI/CD

```bash
# Create IAM user for GitHub Actions (Programmatic access only)
aws iam create-user --user-name infrasketch-cicd

# Attach policies
aws iam attach-user-policy \
  --user-name infrasketch-cicd \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess

aws iam attach-user-policy \
  --user-name infrasketch-cicd \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

aws iam attach-user-policy \
  --user-name infrasketch-cicd \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

aws iam attach-user-policy \
  --user-name infrasketch-cicd \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

aws iam attach-user-policy \
  --user-name infrasketch-cicd \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess

# Create access key (SAVE THE OUTPUT — you'll need these for GitHub secrets)
aws iam create-access-key --user-name infrasketch-cicd
```

### 4.2 Create ECS Task Execution Role

```bash
# Create trust policy for ECS tasks
cat > ecs-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name infrasketch-ecs-execution-role \
  --assume-role-policy-document file://ecs-trust-policy.json

# Attach required policies
aws iam attach-role-policy \
  --role-name infrasketch-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam attach-role-policy \
  --role-name infrasketch-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

aws iam attach-role-policy \
  --role-name infrasketch-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess

aws iam attach-role-policy \
  --role-name infrasketch-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

---

## 5. Network Foundation (VPC)

### 5.1 Create VPC with Public Subnets

```bash
export AWS_REGION=us-east-1
export VPC_NAME=infrasketch-vpc

# Create VPC
VPC_ID=$(aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$VPC_NAME}]" \
  --query 'Vpc.VpcId' --output text)

# Enable DNS hostnames
aws ec2 modify-vpc-attribute \
  --vpc-id $VPC_ID \
  --enable-dns-hostnames

# Create Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway \
  --query 'InternetGateway.InternetGatewayId' --output text)

aws ec2 attach-internet-gateway \
  --internet-gateway-id $IGW_ID \
  --vpc-id $VPC_ID

# Create 2 Public Subnets (in different AZs for high availability)
SUBNET1_ID=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone ${AWS_REGION}a \
  --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$VPC_NAME-public-1a}]" \
  --query 'Subnet.SubnetId' --output text)

SUBNET2_ID=$(aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone ${AWS_REGION}b \
  --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$VPC_NAME-public-1b}]" \
  --query 'Subnet.SubnetId' --output text)

# Create Route Table for public subnets
RT_ID=$(aws ec2 create-route-table \
  --vpc-id $VPC_ID \
  --query 'RouteTable.RouteTableId' --output text)

aws ec2 create-route \
  --route-table-id $RT_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate subnets with route table
aws ec2 associate-route-table \
  --subnet-id $SUBNET1_ID \
  --route-table-id $RT_ID

aws ec2 associate-route-table \
  --subnet-id $SUBNET2_ID \
  --route-table-id $RT_ID

# Enable auto-assign public IPs
aws ec2 modify-subnet-attribute \
  --subnet-id $SUBNET1_ID \
  --map-public-ip-on-launch

aws ec2 modify-subnet-attribute \
  --subnet-id $SUBNET2_ID \
  --map-public-ip-on-launch

# Create Security Group for ALB
ALB_SG=$(aws ec2 create-security-group \
  --group-name infrasketch-alb-sg \
  --description "ALB security group" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Create Security Group for ECS tasks
ECS_SG=$(aws ec2 create-security-group \
  --group-name infrasketch-ecs-sg \
  --description "ECS task security group" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)

# Allow ECS tasks to receive traffic from ALB only
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 8080 \
  --source-group $ALB_SG

echo "VPC_ID=$VPC_ID"
echo "SUBNET1_ID=$SUBNET1_ID"
echo "SUBNET2_ID=$SUBNET2_ID"
echo "ALB_SG=$ALB_SG"
echo "ECS_SG=$ECS_SG"
```

---

## 6. Secrets Management

### 6.1 Store Secrets in AWS Secrets Manager

```bash
# Gemini API Key
aws secretsmanager create-secret \
  --name infrasketch/gemini-api-key \
  --secret-string "your-gemini-api-key" \
  --description "Google Gemini API key for image analysis"

# AWS Bedrock credentials (the app needs these to call Bedrock)
aws secretsmanager create-secret \
  --name infrasketch/aws-access-key \
  --secret-string "your-aws-access-key-id" \
  --description "AWS Access Key for Bedrock"

aws secretsmanager create-secret \
  --name infrasketch/aws-secret-key \
  --secret-string "your-aws-secret-access-key" \
  --description "AWS Secret Key for Bedrock"

# Optional: Store as a JSON secret for all app secrets
aws secretsmanager create-secret \
  --name infrasketch/app-secrets \
  --secret-string '{"GEMINI_API_KEY":"your-key","AWS_ACCESS_KEY_ID":"your-key","AWS_SECRET_ACCESS_KEY":"your-secret","AWS_DEFAULT_REGION":"us-east-1"}' \
  --description "All application secrets in one JSON object"
```

### 6.2 Verify Secrets

```bash
aws secretsmanager list-secrets \
  --filter Key=name,Values=infrasketch
```

---

## 7. Persistent Storage

### 7.1 DynamoDB for Job State

Replace the in-memory `_jobs` dict with DynamoDB for production persistence.

```bash
# Create DynamoDB table for job state
aws dynamodb create-table \
  --table-name infrasketch-jobs \
  --attribute-definitions AttributeName=job_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=InfraSketch

# Create table for chat sessions (if implementing persistent chat)
aws dynamodb create-table \
  --table-name infrasketch-chat-sessions \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
  --key-schema AttributeName=session_id,KeyType=HASH \
  --global-secondary-indexes \
    "IndexName=user-index,KeySchema=[{AttributeName=user_id,KeyType=HASH}],Projection={ProjectionType=ALL}" \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=InfraSketch

# Verify
aws dynamodb list-tables
```

### 7.2 S3 Bucket for File Uploads

```bash
# Create S3 bucket for uploaded architecture diagrams
aws s3api create-bucket \
  --bucket infrasketch-uploads-$(aws sts get-caller-identity --query Account --output text) \
  --region $AWS_REGION

# Enable versioning (protect against accidental deletion)
aws s3api put-bucket-versioning \
  --bucket infrasketch-uploads-$(aws sts get-caller-identity --query Account --output text) \
  --versioning-configuration Status=Enabled

# Set lifecycle policy (delete old versions after 30 days)
cat > lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "ID": "delete-old-versions",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "NoncurrentVersionExpiration": {"NoncurrentDays": 30}
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket infrasketch-uploads-$(aws sts get-caller-identity --query Account --output text) \
  --lifecycle-configuration file://lifecycle.json
```

---

## 8. Container Registry (ECR)

### 8.1 Create ECR Repositories

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Backend repository
aws ecr create-repository \
  --repository-name infrasketch/backend \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256

# Frontend repository
aws ecr create-repository \
  --repository-name infrasketch/frontend \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

---

## 9. Backend Deployment (ECS Fargate)

### 9.1 Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name infrasketch-cluster \
  --settings name=containerInsights,value=enabled \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy \
    base=1,weight=1,capacityProvider=FARGATE \
    base=0,weight=3,capacityProvider=FARGATE_SPOT
```

### 9.2 Create Application Load Balancer

```bash
# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name infrasketch-alb \
  --subnets $SUBNET1_ID $SUBNET2_ID \
  --security-groups $ALB_SG \
  --scheme internet-facing \
  --type application \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# Create Target Group
TG_ARN=$(aws elbv2 create-target-group \
  --name infrasketch-backend-tg \
  --protocol HTTP \
  --port 8080 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

# Create Listener (HTTP — we'll add HTTPS later with ACM)
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# Get ALB DNS name
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' --output text)

echo "ALB_ARN=$ALB_ARN"
echo "TG_ARN=$TG_ARN"
echo "ALB_DNS=$ALB_DNS"
```

### 9.3 Create ECS Task Definition

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Get the ECS execution role ARN
ECS_EXEC_ROLE_ARN=$(aws iam get-role \
  --role-name infrasketch-ecs-execution-role \
  --query 'Role.Arn' --output text)

cat > task-definition.json << EOF
{
  "family": "infrasketch-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "$ECS_EXEC_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "infrasketch-backend",
      "image": "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/infrasketch/backend:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "environment": [
        { "name": "ENVIRONMENT", "value": "production" },
        { "name": "PORT", "value": "8080" },
        { "name": "AWS_DEFAULT_REGION", "value": "$AWS_REGION" },
        { "name": "DYNAMODB_TABLE", "value": "infrasketch-jobs" },
        { "name": "S3_BUCKET", "value": "infrasketch-uploads-$AWS_ACCOUNT_ID" },
        { "name": "CORS_ORIGIN", "value": "https://your-cloudfront-domain.cloudfront.net" }
      ],
      "secrets": [
        {
          "name": "GEMINI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:infrasketch/gemini-api-key"
        },
        {
          "name": "AWS_ACCESS_KEY_ID",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:infrasketch/aws-access-key"
        },
        {
          "name": "AWS_SECRET_ACCESS_KEY",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:infrasketch/aws-secret-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/infrasketch-backend",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      },
      "ulimits": [
        { "name": "nofile", "softLimit": 65536, "hardLimit": 65536 }
      ]
    }
  ]
}
EOF

# Register the task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### 9.4 Create ECS Service

```bash
aws ecs create-service \
  --cluster infrasketch-cluster \
  --service-name infrasketch-backend \
  --task-definition infrasketch-backend \
  --desired-count 2 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET1_ID,$SUBNET2_ID],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=infrasketch-backend,containerPort=8080" \
  --deployment-configuration "minimumHealthyPercent=100,maximumPercent=200" \
  --health-check-grace-period-seconds 60 \
  --propagate-tags SERVICE
```

### 9.5 Enable Auto Scaling

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/infrasketch-cluster/infrasketch-backend \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Scale up when CPU > 70%
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/infrasketch-cluster/infrasketch-backend \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name infrasketch-backend-cpu-scale-up \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration "targetValue=70.0,scaleInCooldown=300,scaleOutCooldown=60,predefinedMetricSpecification={predefinedMetricType=ECSServiceAverageCPUUtilization}"
```

---

## 10. Frontend Deployment (S3 + CloudFront)

### 10.1 Create S3 Bucket for Static Website

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export FRONTEND_BUCKET=infrasketch-frontend-$AWS_ACCOUNT_ID

# Create bucket
aws s3api create-bucket \
  --bucket $FRONTEND_BUCKET \
  --region $AWS_REGION

# Remove block public access (needed for CloudFront OAI)
aws s3api put-public-access-block \
  --bucket $FRONTEND_BUCKET \
  --public-access-block-configuration \
    BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false

# Set bucket policy for CloudFront
cat > bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontAccess",
      "Effect": "Allow",
      "Principal": { "CanonicalUser": "CLOUDFRONT_OAI_CANONICAL_USER_ID" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$FRONTEND_BUCKET/*"
    }
  ]
}
EOF

# Create Origin Access Identity for CloudFront
OAI_ID=$(aws cloudfront create-cloud-front-origin-access-identity \
  --cloud-front-origin-access-identity-config \
    CallerReference=infrasketch-oai,Comment="InfraSketch Frontend OAI" \
  --query 'CloudFrontOriginAccessIdentity.Id' --output text)

OAI_CANONICAL_USER=$(aws cloudfront get-cloud-front-origin-access-identity \
  --id $OAI_ID \
  --query 'CloudFrontOriginAccessIdentity.S3CanonicalUserId' --output text)

# Update bucket policy with actual OAI
cat > bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontAccess",
      "Effect": "Allow",
      "Principal": { "CanonicalUser": "$OAI_CANONICAL_USER" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$FRONTEND_BUCKET/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy \
  --bucket $FRONTEND_BUCKET \
  --policy file://bucket-policy.json
```

### 10.2 Create CloudFront Distribution

```bash
# Get your ALB DNS name (from step 9.2)
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names infrasketch-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

cat > cloudfront-config.json << EOF
{
  "CallerReference": "infrasketch-distribution-$(date +%s)",
  "Origins": {
    "Quantity": 2,
    "Items": [
      {
        "Id": "s3-frontend",
        "DomainName": "$FRONTEND_BUCKET.s3.$AWS_REGION.amazonaws.com",
        "S3OriginConfig": {
          "OriginAccessIdentity": "origin-access-identity/cloudfront/$OAI_ID"
        }
      },
      {
        "Id": "alb-backend",
        "DomainName": "$ALB_DNS",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "OriginProtocolPolicy": "http-only"
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-frontend",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 2,
      "Items": ["HEAD", "GET"],
      "CachedMethods": {
        "Quantity": 2,
        "Items": ["HEAD", "GET"]
      }
    },
    "Compress": true,
    "ForwardedValues": {
      "QueryString": false,
      "Cookies": { "Forward": "none" }
    },
    "MinTTL": 0,
    "DefaultTTL": 86400,
    "MaxTTL": 31536000
  },
  "CacheBehaviors": {
    "Quantity": 1,
    "Items": [
      {
        "PathPattern": "/api/*",
        "TargetOriginId": "alb-backend",
        "ViewerProtocolPolicy": "https-only",
        "AllowedMethods": {
          "Quantity": 7,
          "Items": ["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
          "CachedMethods": {
            "Quantity": 2,
            "Items": ["HEAD", "GET"]
          }
        },
        "Compress": true,
        "ForwardedValues": {
          "QueryString": true,
          "Headers": { "Quantity": 6, "Items": ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method", "Authorization", "Content-Type", "X-Requested-With"] },
          "Cookies": { "Forward": "all" }
        },
        "MinTTL": 0,
        "DefaultTTL": 0,
        "MaxTTL": 0
      }
    ]
  },
  "Comment": "InfraSketch CDN Distribution",
  "PriceClass": "PriceClass_100",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "CustomErrorResponses": {
    "Quantity": 2,
    "Items": [
      { "ErrorCode": 403, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 0 },
      { "ErrorCode": 404, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 0 }
    ]
  }
}
EOF

# Create distribution
DIST_ID=$(aws cloudfront create-distribution \
  --distribution-config file://cloudfront-config.json \
  --query 'Distribution.Id' --output text)

echo "CloudFront Distribution ID: $DIST_ID"
echo "Domain: $(aws cloudfront get-distribution --id $DIST_ID --query 'Distribution.DomainName' --output text)"
```

### 10.3 Configure Frontend Build for Production

Update `frontend/.env.production`:

```bash
VITE_API_BASE_URL=/api
```

CloudFront will route `/api/*` to the ALB, and everything else to the S3 bucket.

---

## 11. CI/CD Pipeline (GitHub Actions)

File: `.github/workflows/aws-deploy.yml`

```yaml
name: InfraSketch AWS CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: "Deployment environment"
        required: true
        default: "staging"
        type: choice
        options: [staging, production]

env:
  AWS_REGION: us-east-1
  ECR_REGISTRY: ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.${{ secrets.AWS_REGION }}.amazonaws.com
  BACKEND_REPO: infrasketch/backend
  FRONTEND_REPO: infrasketch/frontend

jobs:
  # ─────────────────────────────────────────────────────────────────────────
  # JOB 1: Lint & Type Check
  # ─────────────────────────────────────────────────────────────────────────
  lint-and-test:
    name: Lint & Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: "pip" }

      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm", cache-dependency-path: frontend/package-lock.json }

      - name: Backend lint
        run: |
          cd backend
          pip install -r requirements.txt ruff mypy bandit
          ruff check . || true
          bandit -r app/ -f json -o bandit-report.json || true

      - name: Frontend lint
        run: |
          cd frontend
          npm ci
          npm run lint || true

      - uses: actions/upload-artifact@v4
        with: { name: bandit-report, path: backend/bandit-report.json }

  # ─────────────────────────────────────────────────────────────────────────
  # JOB 2: Build & Push to ECR
  # ─────────────────────────────────────────────────────────────────────────
  build-and-push:
    name: Build & Push to ECR
    runs-on: ubuntu-latest
    needs: lint-and-test
    permissions:
      id-token: write
      contents: read
    outputs:
      backend-image: ${{ steps.backend-meta.outputs.tags }}
      frontend-image: ${{ steps.frontend-meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Setup Docker Buildx
        uses: docker/setup-buildx-action@v3

      # Backend
      - uses: docker/metadata-action@v5
        id: backend-meta
        with:
          images: ${{ env.ECR_REGISTRY }}/${{ env.BACKEND_REPO }}
          tags: |
            type=sha,prefix={{branch}}-
            type=raw,value=latest,enable={{is_default_branch}}

      - uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ steps.backend-meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      # Frontend
      - uses: docker/metadata-action@v5
        id: frontend-meta
        with:
          images: ${{ env.ECR_REGISTRY }}/${{ env.FRONTEND_REPO }}
          tags: |
            type=sha,prefix={{branch}}-
            type=raw,value=latest,enable={{is_default_branch}}

      - uses: docker/build-push-action@v5
        with:
          context: ./frontend
          build-args: VITE_API_BASE_URL=${{ secrets.VITE_API_BASE_URL }}
          push: true
          tags: ${{ steps.frontend-meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ─────────────────────────────────────────────────────────────────────────
  # JOB 3: Security Scan
  # ─────────────────────────────────────────────────────────────────────────
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    needs: build-and-push
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ needs.build-and-push.outputs.backend-image }}
          format: "sarif"
          output: "trivy-report.sarif"
          severity: "CRITICAL,HIGH"

      - uses: actions/upload-artifact@v4
        with: { name: trivy-report, path: trivy-report.sarif }

  # ─────────────────────────────────────────────────────────────────────────
  # JOB 4: Deploy Backend to ECS
  # ─────────────────────────────────────────────────────────────────────────
  deploy-backend:
    name: Deploy Backend to ECS
    runs-on: ubuntu-latest
    needs: [build-and-push, security-scan]
    if: github.ref == 'refs/heads/main' || github.event.inputs.environment == 'production'
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Update ECS service
        run: |
          aws ecs update-service \
            --cluster infrasketch-cluster \
            --service infrasketch-backend \
            --force-new-deployment

      - name: Wait for deployment
        run: |
          aws ecs wait services-stable \
            --cluster infrasketch-cluster \
            --services infrasketch-backend

      - name: Smoke test
        run: |
          ALB_URL=$(aws elbv2 describe-load-balancers \
            --names infrasketch-alb \
            --query 'LoadBalancers[0].DNSName' --output text)
          curl -f --retry 10 --retry-delay 10 "http://$ALB_URL/health" || exit 1

  # ─────────────────────────────────────────────────────────────────────────
  # JOB 5: Deploy Frontend to S3 + CloudFront
  # ─────────────────────────────────────────────────────────────────────────
  deploy-frontend:
    name: Deploy Frontend to S3
    runs-on: ubuntu-latest
    needs: deploy-backend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm", cache-dependency-path: frontend/package-lock.json }

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Sync to S3
        run: |
          aws s3 sync frontend/dist/ s3://${{ secrets.FRONTEND_BUCKET }}/ \
            --delete \
            --cache-control "max-age=31536000,immutable" \
            --exclude "index.html"

      - name: Sync index.html with no cache
        run: |
          aws s3 cp frontend/dist/index.html s3://${{ secrets.FRONTEND_BUCKET }}/index.html \
            --metadata-directive REPLACE \
            --cache-control "no-cache,no-store,must-revalidate"

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"
```

### 11.1 Required GitHub Secrets

| Secret | Value | How to Get |
|--------|-------|-----------|
| `AWS_ACCOUNT_ID` | `123456789012` | `aws sts get-caller-identity --query Account` |
| `AWS_REGION` | `us-east-1` | Your AWS region |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/GitHubActionsDeployRole` | Create an OIDC role for GitHub |
| `VITE_API_BASE_URL` | `/api` | Frontend API base path |
| `FRONTEND_BUCKET` | `infrasketch-frontend-123456789012` | Your S3 bucket name |
| `CLOUDFRONT_DISTRIBUTION_ID` | `E1234567890ABC` | Your CloudFront distribution ID |

---

## 12. MLOps & Production Practices

### 12.1 Model Versioning via Environment Variables

All LLM model IDs are externalized in `config.py`:

```python
# backend/app/core/config.py
AWS_BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
AWS_BEDROCK_HAIKU_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
GEMINI_VISION_MODEL = "gemini-2.5-pro"
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
```

**Update Strategy:**
1. Update model ID in code
2. Push to `develop` → auto-deploy to staging ECS service
3. Run smoke tests against staging
4. Merge to `main` → production deployment with rolling update

### 12.2 DynamoDB Migration (Replace In-Memory `_jobs`)

Update `backend/app/api/v1/jobs.py`:

```python
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_DEFAULT_REGION)
jobs_table = dynamodb.Table(settings.DYNAMODB_TABLE)

def _get_job(job_id: str) -> dict:
    """Get job from DynamoDB instead of in-memory dict."""
    response = jobs_table.get_item(Key={"job_id": job_id})
    return response.get("Item")

def _put_job(job_id: str, job_data: dict):
    """Store job in DynamoDB."""
    job_data["job_id"] = job_id
    job_data["ttl"] = int(time.time()) + 86400 * 7  # 7-day TTL
    jobs_table.put_item(Item=job_data)
```

### 12.3 S3 Upload Handling

Replace local file storage with S3:

```python
import boto3
s3 = boto3.client("s3", region_name=settings.AWS_DEFAULT_REGION)

def upload_file(file_bytes, key: str):
    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType="application/pdf"
    )
    return f"s3://{settings.S3_BUCKET}/{key}"
```

---

## 13. Monitoring & Observability

### 13.1 CloudWatch Dashboard

```bash
# Create dashboard
aws cloudwatch put-dashboard \
  --dashboard-name InfraSketch-Production \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "title": "Backend CPU Utilization",
          "metrics": [["AWS/ECS", "CPUUtilization", "ServiceName", "infrasketch-backend", "ClusterName", "infrasketch-cluster"]],
          "period": 60,
          "stat": "Average",
          "region": "us-east-1"
        }
      },
      {
        "type": "metric",
        "properties": {
          "title": "ALB Request Count",
          "metrics": [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", "infrasketch-alb"]],
          "period": 60,
          "stat": "Sum",
          "region": "us-east-1"
        }
      },
      {
        "type": "log",
        "properties": {
          "title": "Backend Errors",
          "query": "SOURCE '/ecs/infrasketch-backend' | fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 20",
          "region": "us-east-1"
        }
      }
    ]
  }'
```

### 13.2 CloudWatch Alarms

```bash
# High CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name infrasketch-high-cpu \
  --alarm-description "Backend CPU > 80% for 5 minutes" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=ServiceName,Value=infrasketch-backend Name=ClusterName,Value=infrasketch-cluster \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:infrasketch-alerts

# High error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name infrasketch-high-errors \
  --alarm-description "HTTP 5xx errors > 10 in 5 minutes" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=LoadBalancer,Value=infrasketch-alb \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:infrasketch-alerts
```

---

## 14. Rollback & Disaster Recovery

### 14.1 ECS Rolling Rollback

```bash
# List previous task definition revisions
aws ecs describe-task-definition \
  --task-definition infrasketch-backend \
  --query 'taskDefinition.revision'

# Rollback to a specific revision
aws ecs update-service \
  --cluster infrasketch-cluster \
  --service infrasketch-backend \
  --task-definition infrasketch-backend:PREVIOUS_REVISION \
  --force-new-deployment

# Or use AWS Console: ECS → Services → infrasketch-backend → Rollback
```

### 14.2 Disaster Recovery Plan

| Scenario | Mitigation | RTO |
|----------|-----------|-----|
| Bad deployment | Rollback to previous ECS task definition | 2 minutes |
| AZ failure | Multi-AZ deployment (subnets in 1a + 1b) | 0 (auto) |
| Region failure | Cross-region replication with Route 53 failover | 15 minutes |
| Data loss | S3 versioning + DynamoDB point-in-time recovery | 5 minutes |
| API key leak | Rotate in Secrets Manager + redeploy | 3 minutes |

### 14.3 DynamoDB Point-in-Time Recovery

```bash
# Enable PITR (keeps 35 days of continuous backups)
aws dynamodb update-continuous-backups \
  --table-name infrasketch-jobs \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

---

## 15. Cost Optimization

### 15.1 Estimated Monthly Costs (us-east-1)

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|-------------------|
| ECS Fargate | 2 tasks × 2 vCPU, 4GB (FARGATE_SPOT 75% of time) | ~$80-120 |
| ALB | ~1M requests/month | ~$20 |
| S3 (Frontend) | 50MB static files + 1M requests | ~$5 |
| S3 (Uploads) | 10GB storage + 100K requests | ~$3 |
| CloudFront | 100GB transfer, 10M requests | ~$15-25 |
| DynamoDB | On-demand, 1K WCU/RCU | ~$10-20 |
| Secrets Manager | 5 secrets, 10K API calls | ~$5 |
| CloudWatch | 10GB logs, 100 alarms | ~$10 |
| Bedrock API | ~1000 requests/day | ~$200-500 |
| Gemini API | ~500 requests/day | ~$20-50 |
| **Total** | | **~$380-750/month** |

### 15.2 Cost Reduction Tips

1. **Use FARGATE_SPOT**: 70% cheaper for fault-tolerant batch workloads
2. **CloudFront caching**: Cache static assets for 1 year, API responses for 5 minutes
3. **DynamoDB TTL**: Auto-delete old job data after 7 days
4. **S3 Intelligent-Tiering**: Move old uploads to cheaper storage classes
5. **Request batching**: Group multiple diagram components into single LLM calls
6. **Enable Savings Plans**: Commit to 1-3 year compute usage for 20-30% discount

---

## 16. Troubleshooting

### 16.1 Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CannotPullContainerError` | ECR permissions | Add `AmazonEC2ContainerRegistryReadOnly` to ECS task role |
| `ResourceInitializationError` | VPC networking | Verify subnets have public IPs and NAT gateway (if private) |
| `403 Forbidden on S3` | Bucket policy / OAI | Verify CloudFront OAI has `s3:GetObject` permission |
| `CORS errors` | Missing CORS headers | Update `ALLOWED_ORIGINS` in config to match CloudFront domain |
| `ThrottlingException` | Bedrock rate limit | Implement exponential backoff; increase ECS task count |
| `Task stops immediately` | Health check failing | Check `/health` endpoint; verify port 8080 is exposed |

### 16.2 Debug Commands

```bash
# View ECS task logs
aws logs tail /ecs/infrasketch-backend --follow

# Describe running tasks
aws ecs describe-tasks \
  --cluster infrasketch-cluster \
  --tasks $(aws ecs list-tasks --cluster infrasketch-cluster --service-name infrasketch-backend --query 'taskArns[0]' --output text)

# Test ALB directly
curl http://$(aws elbv2 describe-load-balancers --names infrasketch-alb --query 'LoadBalancers[0].DNSName' --output text)/health

# Check CloudFront distribution status
aws cloudfront get-distribution --id $DIST_ID --query 'Distribution.Status'
```

---

## Appendix A: Complete File Checklist

```
Terraform_generator/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/
│       │   └── config.py
│       ├── api/
│       │   └── v1/
│       │       └── jobs.py
│       └── services/
│           └── bedrock_service.py
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── .env.production
│   └── ...
├── .github/
│   └── workflows/
│       └── aws-deploy.yml
├── deployment.md
└── preview-deployment1.md  ← This file
```

## Appendix B: One-Command Setup Script

Save as `scripts/setup-aws.sh` and run once:

```bash
#!/bin/bash
set -e

export AWS_REGION=${AWS_REGION:-us-east-1}
export PROJECT_NAME=infrasketch

echo "Setting up InfraSketch on AWS..."

# 1. VPC
# 2. ECR repos
# 3. Secrets Manager
# 4. DynamoDB
# 5. S3 buckets
# 6. ALB
# 7. ECS cluster + service
# 8. CloudFront

# See individual sections above for full commands

echo "Setup complete!"
```

---

> **Next Steps:** After AWS deployment, implement the [Advance_Ai.md](../Advance_Ai.md) roadmap — Redis caching (ElastiCache), distributed tracing (X-Ray), and LLM evaluation pipelines.
