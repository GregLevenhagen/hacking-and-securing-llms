"""Defended RAG system with Azure AI Search security trimming.

Filters search results based on the querying user's role, ensuring that
each user only sees documents their access level permits. Mirrors the
document-level security trimming available in Azure AI Search via
security filters on index fields.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

# Role-to-access-level mapping: each role can see these access levels
ROLE_ACCESS_MAP: dict[str, list[str]] = {
    "intern": ["public"],
    "employee": ["public", "internal"],
    "manager": ["public", "internal", "confidential"],
    "executive": ["public", "internal", "confidential", "executive-only"],
}

# Default access for unrecognized roles — public only (principle of least privilege)
DEFAULT_ACCESS: list[str] = ["public"]


def _load_documents() -> list[dict[str, Any]]:
    """Load sample documents from the JSON corpus."""
    doc_path = Path(__file__).resolve().parent.parent / "documents" / "sample_documents.json"
    with open(doc_path) as f:
        return json.load(f)


class DefendedRAG:
    """RAG system with document-level access control (security trimming).

    Simulates Azure AI Search's security trimming feature: each document
    has an access_level field, and search results are filtered so that
    users only receive documents their role is authorized to view.

    In production Azure AI Search, this is implemented via:
      - A security field (e.g., ``allowed_groups``) on each document in the index.
      - A security filter applied at query time: ``$filter=allowed_groups/any(g: search.in(g, 'group1,group2'))``.
      - User identity resolved from Azure AD / Entra ID tokens.
    """

    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        role_access_map: dict[str, list[str]] | None = None,
    ) -> None:
        self.documents = documents if documents is not None else _load_documents()
        self.role_access_map = role_access_map or dict(ROLE_ACCESS_MAP)

    def _get_allowed_levels(self, user_role: str | None) -> list[str]:
        """Resolve the access levels permitted for a given role.

        Args:
            user_role: The authenticated user's role (e.g., "employee").

        Returns:
            List of access-level strings the role may view.
        """
        if not user_role:
            return list(DEFAULT_ACCESS)
        return self.role_access_map.get(user_role.lower(), list(DEFAULT_ACCESS))

    def search(self, query: str, user_role: str | None = None) -> list[dict[str, Any]]:
        """Search documents by keyword with security trimming.

        Only documents whose access_level is in the user's allowed set
        are returned — mirroring Azure AI Search security filters.

        Args:
            query: Search query string (keyword-based matching).
            user_role: The authenticated user's role. If None or
                       unrecognized, defaults to public-only access.

        Returns:
            List of matching documents filtered by access level.
        """
        allowed_levels = self._get_allowed_levels(user_role)
        query_lower = query.lower()
        keywords = query_lower.split()

        results = []
        for doc in self.documents:
            # Security trimming: skip documents the user cannot access
            if doc["access_level"] not in allowed_levels:
                continue

            searchable = f"{doc['title']} {doc['content']}".lower()
            # Compute keyword-match relevance score (0.0-1.0)
            match_count = sum(1 for kw in keywords if kw in searchable)
            if match_count > 0:
                score = match_count / len(keywords) if keywords else 0.0
                results.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "content": doc["content"],
                    "access_level": doc["access_level"],
                    "department": doc["department"],
                    "relevance_score": round(score, 3),
                })

        # Sort by relevance (descending) like Azure AI Search semantic ranking
        results.sort(key=lambda r: r["relevance_score"], reverse=True)
        return results

    def get_role_info(self, user_role: str | None = None) -> dict[str, Any]:
        """Return metadata about a role's access permissions.

        Useful for debugging and for the terminal demo display.
        """
        allowed = self._get_allowed_levels(user_role)
        total_accessible = sum(
            1 for doc in self.documents if doc["access_level"] in allowed
        )
        return {
            "role": user_role or "(none)",
            "allowed_levels": allowed,
            "accessible_document_count": total_accessible,
            "total_document_count": len(self.documents),
        }
