"""Vulnerable RAG system with NO document-level access control.

Returns all matching documents regardless of the querying user's role,
exposing confidential and executive-only content to any user. This
demonstrates the risk of deploying RAG without security trimming.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


def _load_documents() -> list[dict[str, Any]]:
    """Load sample documents from the JSON corpus."""
    doc_path = Path(__file__).resolve().parent.parent / "documents" / "sample_documents.json"
    with open(doc_path) as f:
        return json.load(f)


class VulnerableRAG:
    """RAG system with NO access control — returns all matching documents.

    Simulates a retrieval-augmented generation pipeline that performs
    keyword search but completely ignores the user's role, returning
    confidential and executive-only documents to anyone.
    """

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self.documents = documents if documents is not None else _load_documents()

    def search(self, query: str, user_role: str | None = None) -> list[dict[str, Any]]:
        """Search documents by keyword — ignores user_role entirely.

        Args:
            query: Search query string (keyword-based matching).
            user_role: Ignored. Accepted for API compatibility only.

        Returns:
            List of matching documents with no access filtering.
        """
        query_lower = query.lower()
        keywords = query_lower.split()

        results = []
        for doc in self.documents:
            searchable = f"{doc['title']} {doc['content']}".lower()
            if any(kw in searchable for kw in keywords):
                results.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "content": doc["content"],
                    "access_level": doc["access_level"],
                    "department": doc["department"],
                })

        return results
