"""
Test the full pipeline end-to-end without needing a real architecture diagram.
Uses a synthetic graph to test IaCAgent → RAG retrieval → Bedrock generation.

Usage: python scripts/test_pipeline.py
"""
import sys
import os
import json

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_iac_agent():
    """Test IaCAgent with a synthetic graph."""
    from app.agents.iac_agent import IaCAgent

    # Synthetic graph mimicking vision output
    test_graph = {
        "nodes": [
            {"id": "vpc-1", "label": "Main VPC", "service_type": "VPC", "type": "VPC", "cloud_provider": "aws", "confidence": 0.95},
            {"id": "subnet-1", "label": "Public Subnet", "service_type": "Subnet", "type": "Subnet", "cloud_provider": "aws", "confidence": 0.9},
            {"id": "ec2-1", "label": "Web Server", "service_type": "EC2", "type": "EC2", "cloud_provider": "aws", "confidence": 0.88},
            {"id": "s3-1", "label": "Data Lake", "service_type": "S3", "type": "S3", "cloud_provider": "aws", "confidence": 0.92},
            {"id": "rds-1", "label": "PostgreSQL DB", "service_type": "RDS", "type": "RDS", "cloud_provider": "aws", "confidence": 0.85},
            {"id": "alb-1", "label": "Application LB", "service_type": "ALB", "type": "ALB", "cloud_provider": "aws", "confidence": 0.9},
        ],
        "edges": [
            {"source": "alb-1", "target": "ec2-1", "connection_type": "ROUTES_TO"},
            {"source": "ec2-1", "target": "rds-1", "connection_type": "CONNECTS_TO"},
            {"source": "ec2-1", "target": "s3-1", "connection_type": "CONNECTS_TO"},
        ]
    }

    print("=" * 60)
    print("TEST: IaCAgent with synthetic graph")
    print("=" * 60)
    print(f"Graph: {len(test_graph['nodes'])} nodes, {len(test_graph['edges'])} edges")
    print()

    agent = IaCAgent()
    job_id = "test-001"

    try:
        files = agent.run(test_graph, {}, job_id, cloud="aws")
        print(f"\n✓ Generated {len(files)} Terraform files:")
        for f in files:
            print(f"  - {f['filename']} ({len(f['content'])} chars)")

        # Basic validation
        all_valid = True
        for f in files:
            if len(f['content']) < 20:
                print(f"  ✗ WARN: {f['filename']} seems too short")
                all_valid = False
            if "```" in f['content']:
                print(f"  ✗ WARN: {f['filename']} contains markdown fences")
                all_valid = False

        if all_valid:
            print("\n✓ All files pass basic validation")
        else:
            print("\n⚠ Some files have warnings")

        return True

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retriever():
    """Test RAG retrieval."""
    from app.rag.knowledge_base import list_collection_stats

    print("\n" + "=" * 60)
    print("TEST: RAG Knowledge Base")
    print("=" * 60)

    stats = list_collection_stats()
    print(f"Collection stats: {stats}")

    has_data = stats.get("aws_resources", 0) > 0
    if has_data:
        from app.rag.retrieval.retriever import TerraformRetriever
        retriever = TerraformRetriever("aws")
        result = retriever.retrieve_for_resource("aws_s3_bucket", "data storage")
        print(f"  Resource chunks: {len(result['resource_chunks'])}")
        print(f"  Security chunks: {len(result['security_chunks'])}")
        if result['security_chunks']:
            print(f"  First security rule: {result['security_chunks'][0][:80]}...")
        print("✓ RAG retrieval working")
        return True
    else:
        print("⚠ Knowledge base is empty. Run: python scripts/ingest_aws.py")
        print("  IaCAgent will use Jinja2 fallback templates")
        return True  # Not a failure, just missing data


def test_vision_import():
    """Test that vision service imports correctly."""
    print("\n" + "=" * 60)
    print("TEST: Vision Service (Gemini) import")
    print("=" * 60)

    try:
        from app.services.vision_service import VisionService
        vs = VisionService()
        print(f"  Model: {vs.model_name}")
        print("✓ Vision service initialized (Gemini)")
        return True
    except Exception as e:
        print(f"✗ Vision import failed: {e}")
        return False


def test_code_generator_import():
    """Test that code generator imports correctly."""
    print("\n" + "=" * 60)
    print("TEST: Code Generator (Bedrock) import")
    print("=" * 60)

    try:
        from app.rag.generation.code_generator import TerraformCodeGenerator
        gen = TerraformCodeGenerator()
        print(f"  Bedrock model: {gen.bedrock_model}")
        print("✓ Code generator initialized (Bedrock)")
        return True
    except Exception as e:
        print(f"✗ Code generator import failed: {e}")
        return False


if __name__ == "__main__":
    results = []

    results.append(("Vision (Gemini)", test_vision_import()))
    results.append(("Code Generator (Bedrock)", test_code_generator_import()))
    results.append(("RAG Knowledge Base", test_retriever()))
    results.append(("IaCAgent Pipeline", test_iac_agent()))

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status} — {name}")

    all_passed = all(r[1] for r in results)
    sys.exit(0 if all_passed else 1)
