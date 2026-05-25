# InfraSketch — Production Deployment Guide on GCP with GitHub Actions CI/CD

> **Architecture:** FastAPI Backend + Vite React Frontend → GCP Cloud Run  
> **CI/CD:** GitHub Actions → Artifact Registry → Cloud Run  
> **MLOps:** Secret Manager, Model Versioning, Health Checks, Rollback  
> **Last Updated:** May 2026

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [GCP Project Setup](#3-gcp-project-setup)
4. [Secret Manager Configuration](#4-secret-manager-configuration)
5. [GitHub Repository Setup](#5-github-repository-setup)
6. [Dockerize the Application](#6-dockerize-the-application)
7. [CI/CD Pipeline (GitHub Actions)](#7-cicd-pipeline-github-actions)
8. [Deploy to Cloud Run](#8-deploy-to-cloud-run)
9. [MLOps & Production Best Practices](#9-mlops--production-best-practices)
10. [Monitoring & Observability](#10-monitoring--observability)
11. [Rollback & Disaster Recovery](#11-rollback--disaster-recovery)
12. [Cost Optimization](#12-cost-optimization)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub (Source)                                │
│                        ┌────────────────────┐                               │
│                        │   GitHub Actions   │                               │
│                        │  CI/CD Pipeline    │                               │
│                        └────────┬───────────┘                               │
└─────────────────────────────────┼───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GCP Artifact Registry                                │
│                    ┌──────────────────────┐                                 │
│                    │  infrasketch/backend │                                 │
│                    │  infrasketch/frontend│                                 │
│                    └──────────┬───────────┘                                 │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│       Cloud Run (Backend)     │   │      Cloud Run (Frontend)     │
│    ┌──────────────────────┐   │   │    ┌──────────────────────┐   │
│    │  FastAPI + Uvicorn │   │   │    │    Nginx + React     │   │
│    │  :8080 (auto-port) │   │   │    │    :8080 (static)    │   │
│    └──────────────────────┘   │   │    └──────────────────────┘   │
│              │                │   │              │                │
│    ┌─────────┴────────┐      │   │              │                │
│    ▼                  ▼      │   │              ▼                │
│ ┌────────┐      ┌────────┐  │   │    ┌──────────────────┐      │
│ │Secret  │      │Cloud   │  │   │    │  Cloud CDN       │      │
│ │Manager │      │Logging │  │   │    │  (optional)      │      │
│ └────────┘      └────────┘  │   │    └──────────────────┘      │
└───────────────────────────────┘   └───────────────────────────────┘
```

### Service Breakdown

| Service | Technology | GCP Product | Purpose |
|---------|-----------|-------------|---------|
| Backend API | FastAPI + Uvicorn | Cloud Run | LLM orchestration, image analysis, design doc generation |
| Frontend SPA | Vite React + Nginx | Cloud Run | Static file serving, API proxying |
| Container Registry | Docker | Artifact Registry | Store built images |
| Secrets | — | Secret Manager | API keys, AWS credentials |
| Logs & Metrics | — | Cloud Logging / Monitoring | Observability |
| Load Balancer | — | Cloud Load Balancing | Custom domain + SSL (optional) |

---

## 2. Prerequisites

### 2.1 Required Accounts

- [ ] **Google Cloud account** (free tier available)
- [ ] **GitHub account** (for source control + Actions)
- [ ] **AWS account** (for Bedrock API access)
- [ ] **Google AI Studio account** (for Gemini API key)

### 2.2 Local Tools

```bash
# Install gcloud CLI
https://cloud.google.com/sdk/docs/install

# Verify
$ gcloud --version
Google Cloud SDK 500.0.0

# Install Docker
https://docs.docker.com/get-docker/

# Verify
$ docker --version
Docker version 26.0, build 2ae903e
```

### 2.3 Required API Keys

| Secret | Source | How to Get |
|--------|--------|-----------|
| `GEMINI_API_KEY` | Google AI Studio | https://aistudio.google.com/app/apikey |
| `AWS_ACCESS_KEY_ID` | AWS IAM | Create IAM user with `AmazonBedrockFullAccess` |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM | Download during key creation |
| `AWS_DEFAULT_REGION` | AWS | `us-east-1` (or your Bedrock region) |

---

## 3. GCP Project Setup

### 3.1 Create a New Project

```bash
# Set your project ID
export GCP_PROJECT_ID="infrasketch-prod"
export GCP_REGION="us-central1"

# Create project
gcloud projects create $GCP_PROJECT_ID --name="InfraSketch Production"

# Set as active project
gcloud config set project $GCP_PROJECT_ID

# Link billing account (find yours with: gcloud billing accounts list)
gcloud billing projects link $GCP_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### 3.2 Enable Required APIs

```bash
# Enable all necessary GCP APIs
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable monitoring.googleapis.com
gcloud services enable logging.googleapis.com
```

### 3.3 Create Artifact Registry Repository

```bash
# Create Docker repository for our images
gcloud artifacts repositories create infrasketch \
  --repository-format=docker \
  --location=$GCP_REGION \
  --description="InfraSketch container images"

# Verify
gcloud artifacts repositories list --location=$GCP_REGION
```

---

## 4. Secret Manager Configuration

Store all sensitive credentials in GCP Secret Manager (never in code or env files).

### 4.1 Create Secrets

```bash
# Gemini API Key
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key \
  --data-file=- \
  --replication-policy="automatic"

# AWS Access Key
echo -n "your-aws-access-key-id" | gcloud secrets create aws-access-key \
  --data-file=- \
  --replication-policy="automatic"

# AWS Secret Key
echo -n "your-aws-secret-access-key" | gcloud secrets create aws-secret-key \
  --data-file=- \
  --replication-policy="automatic"

# AWS Region (optional — can be hardcoded)
echo -n "us-east-1" | gcloud secrets create aws-region \
  --data-file=- \
  --replication-policy="automatic"
```

### 4.2 Verify Secrets

```bash
gcloud secrets list

# NAME           REPLICATION_POLICY  CREATED
# aws-access-key  automatic           2026-05-18T00:00:00Z
# aws-secret-key  automatic           2026-05-18T00:00:00Z
# gemini-api-key  automatic           2026-05-18T00:00:00Z
```

---

## 5. GitHub Repository Setup

### 5.1 Create GitHub Secrets

Navigate to: **Settings → Secrets and variables → Actions**

Add these repository secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `GCP_PROJECT_ID` | `infrasketch-prod` | Your GCP project ID |
| `GCP_SERVICE_ACCOUNT_EMAIL` | `github-actions@infrasketch-prod.iam.gserviceaccount.com` | Service account email |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider` | WIF provider ID |
| `VITE_API_BASE_URL` | `/api` | Frontend API base path |

### 5.2 Setup Workload Identity Federation (Recommended)

Instead of downloading a service account JSON key, use Workload Identity Federation for secure, keyless authentication.

```bash
# 1. Create a Service Account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions"

# 2. Grant necessary roles
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-actions@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 3. Create Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 4. Create OIDC Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --workload-identity-pool="github-pool" \
  --provider-display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --location="global"

# 5. Allow GitHub repository to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  github-actions@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME"
```

---

## 6. Dockerize the Application

We use multi-stage Docker builds to keep images small and secure.

### 6.1 Backend Dockerfile

File: `backend/Dockerfile`

```dockerfile
# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runner ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app
COPY . .
RUN mkdir -p storage/uploads storage/processed storage/outputs chroma_db && \
    chown -R appuser:appgroup /app

USER appuser
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + str(__import__('os').getenv('PORT', '8080')) + '/health')" || exit 1

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
```

### 6.2 Frontend Dockerfile

File: `frontend/Dockerfile`

```dockerfile
# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --only=production=false
COPY . .
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ── Stage 2: Serve ─────────────────────────────────────────────────────────────
FROM nginx:1.25-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
ENV PORT=8080
EXPOSE ${PORT}
CMD ["/bin/sh", "-c", "envsubst '\$PORT' < /etc/nginx/conf.d/default.conf > /etc/nginx/conf.d/default.conf.tmp && mv /etc/nginx/conf.d/default.conf.tmp /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
```

### 6.3 Frontend Nginx Config

File: `frontend/nginx.conf`

```nginx
server {
    listen ${PORT};
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    location /api/ {
        proxy_pass https://YOUR-BACKEND-CLOUD-RUN-URL/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|otf)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 6.4 Local Docker Test

```bash
# Build and test backend locally
cd backend
docker build -t infrasketch-backend .
docker run -p 8000:8080 --env PORT=8080 \
  --env GEMINI_API_KEY=your-key \
  --env AWS_ACCESS_KEY_ID=your-key \
  --env AWS_SECRET_ACCESS_KEY=your-secret \
  infrasketch-backend

# Build and test frontend locally
cd frontend
docker build -t infrasketch-frontend --build-arg VITE_API_BASE_URL=http://localhost:8000 .
docker run -p 3000:8080 --env PORT=8080 infrasketch-frontend
```

---

## 7. CI/CD Pipeline (GitHub Actions)

File: `.github/workflows/deploy.yml`

### Pipeline Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Code Push  │───▶│   Lint &     │───▶│   Build &    │───▶│   Security   │
│   to main    │    │   Test       │    │   Push       │    │   Scan       │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                  │
                                                                  ▼
                    ┌──────────────────────────────────────────────────────┐
                    │                     Deploy Stage                       │
                    │  ┌────────────┐     ┌────────────┐     ┌──────────┐  │
                    │  │  Staging   │───▶│  Smoke Test│───▶│Production│  │
                    │  │  (develop) │     │            │     │  (main)  │  │
                    │  └────────────┘     └────────────┘     └──────────┘  │
                    └──────────────────────────────────────────────────────┘
```

### 7.1 Pipeline Stages

| Stage | Job Name | Tools | Purpose |
|-------|---------|-------|---------|
| 1 | `lint-and-test` | Ruff, ESLint, mypy | Code quality gates |
| 2 | `build-and-push` | Docker, Buildx, Artifact Registry | Build + cache layers |
| 3 | `security-scan` | Trivy, Bandit | Container vuln scanning |
| 4 | `deploy-staging` | gcloud, Cloud Run | Deploy to staging |
| 5 | `deploy-production` | gcloud, Cloud Run | Deploy + smoke test + traffic shift |

### 7.2 Key MLOps Features

- **Model Versioning**: Model IDs (Claude, Gemini) are env vars, versioned via config
- **Secret Management**: API keys stored in Secret Manager, never in code
- **Health Checks**: `/health` endpoint verifies service before receiving traffic
- **Canary Deployments**: `--no-traffic` flag → smoke test → traffic shift
- **Rollback**: Cloud Run keeps last 100 revisions; instant rollback via `gcloud run services update-traffic`

### 7.3 Manual Trigger

```bash
# From GitHub CLI or web UI
gh workflow run deploy.yml -f environment=staging
gh workflow run deploy.yml -f environment=production
```

---

## 8. Deploy to Cloud Run

### 8.1 Initial Manual Deploy (One-Time Setup)

```bash
# Authenticate
gcloud auth login
gcloud config set project $GCP_PROJECT_ID

# Build images locally and push to Artifact Registry
gcloud builds submit ./backend \
  --tag us-central1-docker.pkg.dev/$GCP_PROJECT_ID/infrasketch/backend:latest

gcloud builds submit ./frontend \
  --tag us-central1-docker.pkg.dev/$GCP_PROJECT_ID/infrasketch/frontend:latest \
  --substitutions=_VITE_API_BASE_URL=/api

# Deploy backend
gcloud run deploy infrasketch-backend \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/infrasketch/backend:latest \
  --region $GCP_REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,AWS_ACCESS_KEY_ID=aws-access-key:latest,AWS_SECRET_ACCESS_KEY=aws-secret-key:latest \
  --memory 4Gi \
  --cpu 2 \
  --max-instances 10 \
  --timeout 600

# Deploy frontend
gcloud run deploy infrasketch-frontend \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/infrasketch/frontend:latest \
  --region $GCP_REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5
```

### 8.2 Get Service URLs

```bash
# Get the backend URL (needed for frontend proxy)
gcloud run services describe infrasketch-backend --region $GCP_REGION --format 'value(status.url)'
# Output: https://infrasketch-backend-xxxxxxxxxx-uc.a.run.app

# Get the frontend URL
gcloud run services describe infrasketch-frontend --region $GCP_REGION --format 'value(status.url)'
# Output: https://infrasketch-frontend-xxxxxxxxxx-uc.a.run.app
```

### 8.3 Update Frontend Proxy (One-Time)

After getting the backend URL, update `frontend/nginx.conf`:

```nginx
location /api/ {
    proxy_pass https://infrasketch-backend-xxxxxxxxxx-uc.a.run.app/;
    # ...
}
```

Then rebuild and redeploy the frontend.

---

## 9. MLOps & Production Best Practices

### 9.1 Model Versioning & Configuration

All LLM model IDs are configurable via environment variables:

| Env Var | Current Value | Description |
|---------|--------------|-------------|
| `AWS_BEDROCK_MODEL` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Primary generation model |
| `AWS_BEDROCK_HAIKU_MODEL` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Compression model |
| `GEMINI_VISION_MODEL` | `gemini-2.5-pro` | Image analysis model |
| `GEMINI_TEXT_MODEL` | `gemini-2.5-flash` | Text fallback model |

**Update Strategy:**
1. Update model ID in `backend/app/core/config.py`
2. Push to `develop` branch
3. Test in staging environment
4. Merge to `main` for production rollout

### 9.2 Prompt Versioning (MLOps)

Prompts are hardcoded in Python files. Track changes via:

```bash
# Tag prompt versions
git tag prompts-v1.2.0
git push origin prompts-v1.2.0

# Rollback to previous prompt version
git checkout prompts-v1.1.0 -- backend/app/services/design_doc_service.py
```

**Future improvement:** Store prompts in a versioned store (Firestore / GCS) for A/B testing.

### 9.3 Data Flow for LLM Requests

```
User Request
     │
     ▼
┌────────────────────────────────────────────────────────┐
│  Cloud Run (Backend)                                   │
│  ┌────────────┐    ┌──────────┐    ┌──────────────┐  │
│  │  FastAPI   │───▶│  Secret  │───▶│  Bedrock/    │  │
│  │  Router    │    │  Manager │    │  Gemini API  │  │
│  └────────────┘    └──────────┘    └──────────────┘  │
│         │                                              │
│         ▼                                              │
│  ┌──────────────────────────────────────────────┐      │
│  │  LangGraph Pipeline                           │      │
│  │  Vision → Prompt → Fusion → Compression →    │      │
│  │  Design Doc → Terraform Prompts → Chat       │      │
│  └──────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

### 9.4 In-Memory State Warning ⚠️

The app currently stores jobs in an in-memory dictionary (`_jobs` in `jobs.py`). **This is lost on every container restart.**

**Production Migration Path:**

| Option | GCP Product | Effort | Best For |
|--------|------------|--------|---------|
| Firestore | Cloud Firestore (Datastore mode) | Low | Simple key-value job storage |
| Redis | Cloud Memorystore (Redis) | Medium | Sessions + caching |
| PostgreSQL | Cloud SQL | Medium | Complex queries + relational data |

**Quick Firestore Migration:**

```bash
# Install
gcloud services enable firestore.googleapis.com

# In config.py, replace in-memory dict with Firestore client
# File: backend/app/api/v1/jobs.py
```

---

## 10. Monitoring & Observability

### 10.1 Cloud Monitoring Dashboard

```bash
# View Cloud Run metrics
gcloud monitoring metrics list --filter="metric.type:run.googleapis.com"

# Key metrics:
# - run.googleapis.com/container/request_count       (requests/sec)
# - run.googleapis.com/container/request_latencies     (p50/p95/p99 latency)
# - run.googleapis.com/container/memory/utilizations   (memory usage)
# - run.googleapis.com/container/cpu/utilizations      (CPU usage)
```

### 10.2 Custom Alerting Policies

```bash
# Create alert for high error rate
gcloud alpha monitoring policies create \
  --policy-from-file="alert-policy.json"
```

**alert-policy.json:**

```json
{
  "displayName": "High Error Rate",
  "conditions": [
    {
      "displayName": "Error rate > 5%",
      "conditionThreshold": {
        "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/container/request_count\" AND metric.label.status_code!=\"2xx\"",
        "aggregations": [{ "alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_RATE" }],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.05,
        "duration": "300s"
      }
    }
  ],
  "alertStrategy": { "autoClose": "86400s" },
  "notificationChannels": ["projects/YOUR_PROJECT/notificationChannels/YOUR_CHANNEL"]
}
```

### 10.3 Application Logs

```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=infrasketch-backend" --limit 50

# Stream logs in real-time
gcloud alpha logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=infrasketch-backend"
```

---

## 11. Rollback & Disaster Recovery

### 11.1 Instant Rollback

```bash
# List all revisions
gcloud run revisions list --service=infrasketch-backend --region=$GCP_REGION

# Rollback to a specific revision
gcloud run services update-traffic infrasketch-backend \
  --to-revisions=REVISION_NAME=100 \
  --region=$GCP_REGION

# Or rollback to the previous revision
gcloud run services update-traffic infrasketch-backend \
  --to-latest \
  --region=$GCP_REGION
```

### 11.2 Disaster Recovery Plan

| Scenario | Mitigation | RTO |
|----------|-----------|-----|
| Bad deployment | Rollback to previous revision | 1 minute |
| GCP region down | Deploy to secondary region (us-west1) | 10 minutes |
| Bedrock throttling | Increase max-instances, implement caching | 5 minutes |
| API key leak | Rotate keys in Secret Manager | 2 minutes |

---

## 12. Cost Optimization

### 12.1 Estimated Monthly Costs (us-central1)

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|-------------------|
| Cloud Run Backend | 2Gi, 1 vCPU, avg 2 instances | ~$50-100 |
| Cloud Run Frontend | 512Mi, 0.5 vCPU, avg 1 instance | ~$10-20 |
| Artifact Registry | 5GB image storage | ~$5 |
| Secret Manager | 5 secrets, 1000 accesses/day | ~$3 |
| Cloud Logging | 10GB logs/month | ~$5 |
| Bedrock API calls | ~1000 requests/day (varies by usage) | ~$200-500 |
| Gemini API | ~500 requests/day | ~$20-50 |
| **Total** | | **~$290-680/month** |

### 12.2 Cost Reduction Tips

1. **Min instances = 0 for staging**: Scale to zero when not in use
2. **Use Cloud CDN**: Cache frontend assets, reduce Cloud Run egress
3. **Batch requests**: Group multiple component analyses into single LLM calls
4. **Prompt caching**: Cache identical prompts (Redis) to reduce Bedrock calls
5. **Request deduplication**: Cache design doc results for same diagram uploads

---

## 13. Troubleshooting

### 13.1 Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Image pull error` | Artifact Registry permissions | Grant `roles/artifactregistry.reader` to Cloud Run SA |
| `Secret not found` | Secret name mismatch | Verify secret names in `--set-secrets` flag |
| `Timeout on design doc generation` | Default 300s timeout too short | Increase `--timeout 600` |
| `CORS errors` | Frontend/backend origin mismatch | Update `ALLOWED_ORIGINS` in `config.py` |
| `Memory crash (OOM)` | Image processing uses too much RAM | Increase `--memory 4Gi` or 8Gi |

### 13.2 Debugging Commands

```bash
# Check service status
gcloud run services describe infrasketch-backend --region=$GCP_REGION

# View logs for a specific revision
gcloud logging read "resource.labels.revision_name='infrasketch-backend-00001-xxx'"

# SSH into a running container (for debugging)
gcloud run services proxy infrasketch-backend --region=$GCP_REGION

# Test the API locally
curl https://YOUR-BACKEND-URL/health
```

### 13.3 Health Check Endpoint

The backend exposes a health check at `/health`:

```bash
curl https://infrasketch-backend-xxx-uc.a.run.app/health
# Expected: {"status": "ok"}
```

Ensure your `app/main.py` includes:

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```

---

## Appendix A: File Checklist

After completing this guide, your repo should have:

```
Terraform_generator/
├── backend/
│   ├── Dockerfile           ← Multi-stage Python build
│   ├── requirements.txt
│   └── app/
├── frontend/
│   ├── Dockerfile           ← Multi-stage Vite+Nginx build
│   ├── nginx.conf           ← API proxy + SPA routing
│   └── ...
├── .github/
│   └── workflows/
│       └── deploy.yml       ← CI/CD pipeline
├── docker-compose.yml       ← Local drawio container
├── deployment.md            ← This guide
└── .gitignore
```

## Appendix B: Environment Variables Reference

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `GEMINI_API_KEY` | Yes | Secret Manager | Google Gemini API |
| `AWS_ACCESS_KEY_ID` | Yes | Secret Manager | AWS IAM key |
| `AWS_SECRET_ACCESS_KEY` | Yes | Secret Manager | AWS IAM secret |
| `AWS_DEFAULT_REGION` | Yes | Hardcoded / Env | Bedrock region |
| `AWS_BEDROCK_MODEL` | Yes | Hardcoded | Claude model ID |
| `AWS_BEDROCK_HAIKU_MODEL` | Yes | Hardcoded | Haiku model ID |
| `PORT` | Yes | Cloud Run | Container port (8080) |
| `CORS_ORIGIN` | Yes | Env / Config | Frontend origin |
| `ENVIRONMENT` | No | CI/CD | staging / production |

---

> **Next Steps:** After deployment, implement [Advance_Ai.md](../Advance_Ai.md) roadmap items — caching, distributed tracing, and prompt evaluation pipelines.
