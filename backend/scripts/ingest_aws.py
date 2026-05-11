"""
Run this once to populate the ChromaDB knowledge base with AWS docs.
Usage: python scripts/ingest_aws.py
"""
import sys
import os

# Add parent to path so app imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.ingestion.registry_scraper import RegistryScraper
from app.rag.ingestion.embedder import KnowledgeBaseEmbedder
from app.rag.knowledge_base import list_collection_stats


def main():
    print("=== Ingesting AWS Terraform Provider Docs ===")

    # 1. Scrape
    scraper = RegistryScraper()
    docs = scraper.scrape_target_resources("aws")
    print(f"Scraped {len(docs)} AWS resource docs")

    # 2. Embed
    embedder = KnowledgeBaseEmbedder()
    embedder.embed_resource_docs(docs, "aws")

    # 3. Security rules
    print("Embedding security rules...")
    embedder.embed_security_rules()

    # 4. Stats
    print("\nFinal collection stats:")
    for name, count in list_collection_stats().items():
        print(f"  {name}: {count}")

    print("\nDone!")


if __name__ == "__main__":
    main()
