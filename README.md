# InfraSketch

InfraSketch is a full-stack application that converts cloud architecture diagrams into production-grade Terraform code using AI.

## Overview

InfraSketch allows users to upload cloud/system architecture diagrams (AWS, GCP, Azure) and automatically:
1. Extract architecture details using OCR and Gemini Vision
2. Build structured architecture context
3. Generate production-grade design documents using Claude/Sonnet via AWS Bedrock
4. Generate validated Terraform code using RAG-based knowledge base

## Architecture

```
InfraSketch/
├── frontend/                    # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── pages/              # Workflow pages
│   │   ├── store/              # Zustand state management
│   │   ├── services/           # API integration
│   │   └── types/              # TypeScript schemas
│   └── package.json
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── api/                # API routes
│   │   ├── services/           # Business logic
│   │   ├── schemas/            # Pydantic models
│   │   ├── core/               # Configuration
│   │   └── db/                 # Database models
│   └── requirements.txt
│
├── knowledge_base/             # RAG knowledge base
│   ├── ingestion/              # Documentation ingestion
│   ├── vector_store/           # ChromaDB + embeddings
│   ├── retrieval/              # Hybrid retrieval
│   ├── schema_db/              # PostgreSQL schemas
│   └── collections/           # Resource documentation
│
├── terraform_engine/           # Terraform generation engine
│   ├── pipeline/               # Generation pipeline
│   ├── mappings/               # Resource mappings
│   ├── templates/              # Terraform templates
│   └── constants/             # Dependency rules
│
└── validation/                 # Validation tools
    ├── terraform_validator.py
    ├── hcl_parser.py
    ├── schema_validator.py
    ├── checkov_runner.py
    └── tfsec_runner.py
```

## Workflow

1. **Upload**: User uploads architecture diagram image
2. **OCR**: Extract text using Tesseract
3. **Vision Analysis**: Gemini Vision analyzes diagram structure
4. **Context Building**: Build structured ArchitectureContextPack
5. **Cloud Detection**: Detect cloud provider (AWS/GCP/Azure)
6. **RAG Enrichment**: Retrieve provider documentation and best practices
7. **Design Generation**: Claude generates design document via AWS Bedrock
8. **Terraform Generation**: Generate Terraform with strict grounding
9. **Validation**: Comprehensive validation (syntax, schema, security)

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload
```

Required environment variables:
- `GOOGLE_API_KEY` - For Gemini Vision
- `AWS_ACCESS_KEY_ID` - AWS Bedrock access
- `AWS_SECRET_ACCESS_KEY` - AWS Bedrock secret
- `AWS_REGION` - AWS region (default: us-east-1)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Knowledge Base

The knowledge base requires ingesting cloud provider documentation:

```python
from knowledge_base.ingestion.pipeline import IngestionPipeline

pipeline = IngestionPipeline()
pipeline.ingest_provider_docs("aws")
```

## API Endpoints

- `POST /api/upload/` - Upload diagram file
- `POST /api/analyse/` - Analyse diagram (context + design)
- `POST /api/analyse/full-pipeline` - Full pipeline (context + design + terraform)
- `POST /api/design/` - Generate design document
- `POST /api/terraform/` - Generate Terraform code
- `POST /api/terraform/validate` - Validate Terraform code

## Key Features

- **Multi-provider support**: AWS, GCP, Azure
- **Vision-based analysis**: Gemini Vision for diagram understanding
- **RAG-powered generation**: Grounded in provider documentation
- **Comprehensive validation**: Syntax, schema, security (Checkov/tfsec)
- **Production-ready output**: Validated Terraform with confidence scores

## Tech Stack

- **Frontend**: React, Vite, Tailwind CSS, Zustand
- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **AI/ML**: Gemini Vision, Claude (via AWS Bedrock), ChromaDB
- **Validation**: Checkov, tfsec, terraform validate
- **OCR**: Tesseract

## License

MIT
