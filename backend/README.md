# InfraSketch Backend

FastAPI backend for generating Terraform from infrastructure diagrams.

## Project Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI entrypoint
│   ├── api/                       # API routes
│   │   ├── upload.py              # Step 1: Upload diagram
│   │   ├── analyse.py             # Step 2: Analyse diagram
│   │   ├── design.py              # Step 3: Generate design doc
│   │   └── terraform.py           # Step 4: Generate Terraform
│   ├── schemas/                   # Pydantic models
│   ├── services/                  # Business logic
│   ├── core/                      # Configuration & constants
│   └── db/                        # Database models & session
└── requirements.txt

knowledge_base/
├── ingestion/                     # Documentation ingestion pipeline
├── vector_store/                  # ChromaDB & embeddings
├── retrieval/                     # Hybrid retrieval (semantic + keyword)
├── schema_db/                     # PostgreSQL for resource schemas
└── collections/                   # Resource documentation collections
```

## Setup

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. Run the server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

- `POST /api/upload` - Upload diagram file
- `POST /api/analyse` - Analyse diagram
- `GET /api/analyse/status/{job_id}` - Get analysis status
- `POST /api/design` - Generate design document
- `GET /api/design/{analysis_id}` - Get design document
- `POST /api/terraform` - Generate Terraform code
- `GET /api/terraform/{design_id}` - Get Terraform code

## RAG Pipeline

The knowledge base uses a RAG (Retrieval-Augmented Generation) pipeline:

1. **Ingestion**: Fetch and chunk cloud provider documentation
2. **Vector Store**: Store embeddings in ChromaDB
3. **Retrieval**: Hybrid semantic + keyword search
4. **Generation**: Use retrieved context with LLM for Terraform generation

## Development

- API documentation: http://localhost:8000/docs
- Interactive API: http://localhost:8000/redoc
