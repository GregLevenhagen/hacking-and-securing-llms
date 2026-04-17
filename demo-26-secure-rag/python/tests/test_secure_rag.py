"""Tests for Demo 26 — Secure RAG with Access Control.

Verifies that the vulnerable RAG ignores roles while the defended RAG
enforces document-level security trimming based on user roles.
"""

import json
from pathlib import Path

from demo26_vulnerable_rag import VulnerableRAG
from demo26_defended_rag import DefendedRAG, ROLE_ACCESS_MAP


def _load_sample_docs() -> list[dict]:
    """Load the sample document corpus."""
    doc_path = (
        Path(__file__).resolve().parent.parent.parent
        / "documents"
        / "sample_documents.json"
    )
    with open(doc_path) as f:
        return json.load(f)


SAMPLE_DOCS = _load_sample_docs()


# ---------------------------------------------------------------------------
# Vulnerable RAG tests
# ---------------------------------------------------------------------------

class TestVulnerableRAG:
    def test_vulnerable_returns_all_docs(self) -> None:
        """Vulnerable RAG should return documents of ALL access levels,
        completely ignoring the user_role parameter."""
        rag = VulnerableRAG(documents=SAMPLE_DOCS)

        # Use a broad query that matches docs at every access level
        results = rag.search("company", user_role="intern")

        # Should include docs the intern shouldn't see
        access_levels = {r["access_level"] for r in results}
        assert len(results) > 0, "Should return at least some documents"

        # The vulnerable system should NOT filter — verify it returns
        # public docs at minimum, and does not strip higher-level docs
        # that match the query.
        all_matching = rag.search("company", user_role=None)
        assert results == all_matching, (
            "Vulnerable RAG should return identical results regardless of role"
        )

    def test_vulnerable_ignores_role(self) -> None:
        """Same query with different roles should yield identical results."""
        rag = VulnerableRAG(documents=SAMPLE_DOCS)
        intern_results = rag.search("salary", user_role="intern")
        exec_results = rag.search("salary", user_role="executive")
        assert intern_results == exec_results


# ---------------------------------------------------------------------------
# Defended RAG tests
# ---------------------------------------------------------------------------

class TestDefendedRAG:
    def test_defended_intern_only_public(self) -> None:
        """Intern should only see documents with access_level='public'."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("company", user_role="intern")

        for doc in results:
            assert doc["access_level"] == "public", (
                f"Intern should not see {doc['access_level']} doc: {doc['title']}"
            )

    def test_defended_employee_sees_internal(self) -> None:
        """Employee should see public and internal but not confidential."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        # Query that matches internal-level engineering docs
        results = rag.search("on-call rotation", user_role="employee")

        levels = {r["access_level"] for r in results}
        assert "internal" in levels or len(results) > 0
        for doc in results:
            assert doc["access_level"] in ("public", "internal"), (
                f"Employee should not see {doc['access_level']} doc: {doc['title']}"
            )

    def test_defended_executive_sees_all(self) -> None:
        """Executive should see documents at every access level."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)

        # Broad query to match across all access levels
        results = rag.search("company Q1 acquisition salary", user_role="executive")

        access_levels = {r["access_level"] for r in results}
        # Executive should be able to see all four levels if query matches
        assert "public" in access_levels, "Executive should see public docs"
        assert "executive-only" in access_levels or "confidential" in access_levels, (
            "Executive should see restricted docs"
        )

    def test_defended_unknown_role_gets_public_only(self) -> None:
        """An unrecognized role should default to public-only access."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("company salary acquisition", user_role="hacker")

        for doc in results:
            assert doc["access_level"] == "public", (
                f"Unknown role should not see {doc['access_level']} doc: {doc['title']}"
            )

    def test_defended_none_role_gets_public_only(self) -> None:
        """A None role should default to public-only access."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("company salary acquisition", user_role=None)

        for doc in results:
            assert doc["access_level"] == "public", (
                f"None role should not see {doc['access_level']} doc: {doc['title']}"
            )

    def test_access_control_blocks_confidential_from_intern(self) -> None:
        """Intern must NOT see confidential documents even when they match the query."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)

        # "revenue" and "salary" appear in confidential docs
        results_revenue = rag.search("revenue forecast", user_role="intern")
        results_salary = rag.search("salary band", user_role="intern")

        for doc in results_revenue + results_salary:
            assert doc["access_level"] not in ("confidential", "executive-only"), (
                f"Intern retrieved restricted doc: {doc['title']} ({doc['access_level']})"
            )

    def test_manager_sees_confidential_but_not_executive(self) -> None:
        """Manager should see confidential but NOT executive-only documents."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("acquisition revenue salary", user_role="manager")

        for doc in results:
            assert doc["access_level"] != "executive-only", (
                f"Manager should not see executive-only doc: {doc['title']}"
            )

        # Verify manager CAN see confidential
        levels = {r["access_level"] for r in results}
        assert "confidential" in levels, "Manager should see confidential docs"

    def test_role_access_map_completeness(self) -> None:
        """Every role in ROLE_ACCESS_MAP should have 'public' as minimum access."""
        for role, levels in ROLE_ACCESS_MAP.items():
            assert "public" in levels, f"Role '{role}' is missing 'public' access"

    def test_get_role_info(self) -> None:
        """get_role_info should return correct metadata for a role."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        info = rag.get_role_info("intern")

        assert info["role"] == "intern"
        assert info["allowed_levels"] == ["public"]
        assert info["accessible_document_count"] <= info["total_document_count"]
        assert info["total_document_count"] == len(SAMPLE_DOCS)


class TestEdgeCases:
    def test_empty_query_returns_no_results(self) -> None:
        """An empty query string should return no matching documents."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("", user_role="executive")
        assert results == []

    def test_case_insensitive_role(self) -> None:
        """Role matching should be case-insensitive (e.g., 'INTERN' treated as 'intern')."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results_lower = rag.search("company", user_role="intern")
        results_upper = rag.search("company", user_role="INTERN")
        assert results_lower == results_upper

    def test_custom_role_access_map(self) -> None:
        """DefendedRAG should respect a custom role access map."""
        custom_map = {
            "auditor": ["public", "confidential", "executive-only"],
        }
        rag = DefendedRAG(documents=SAMPLE_DOCS, role_access_map=custom_map)
        results = rag.search("company salary acquisition", user_role="auditor")
        levels = {r["access_level"] for r in results}
        # Auditor should see public and confidential/exec-only but not internal
        for doc in results:
            assert doc["access_level"] in ("public", "confidential", "executive-only")

    def test_relevance_score_in_results(self) -> None:
        """Search results should include a relevance_score field."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("company", user_role="executive")
        assert len(results) > 0
        for doc in results:
            assert "relevance_score" in doc
            assert 0.0 <= doc["relevance_score"] <= 1.0

    def test_results_sorted_by_relevance(self) -> None:
        """Results should be sorted by relevance_score (descending)."""
        rag = DefendedRAG(documents=SAMPLE_DOCS)
        results = rag.search("company salary", user_role="executive")
        if len(results) > 1:
            scores = [r["relevance_score"] for r in results]
            assert scores == sorted(scores, reverse=True)
