"""Tests for Demo 3 poison_index.py — poisoning the RAG index."""

from pathlib import Path

import pytest
from chromadb.api.types import EmbeddingFunction, Embeddings

from build_index import build_index, load_documents
from poison_index import POISONED_DOCS_DIR, poison_index

# Document directories
_demo_root = Path(__file__).resolve().parents[2]
LEGIT_DIR = _demo_root / "documents" / "legitimate"
INJECTION_STRING = "support@evil.example.com"


class MockEmbeddingFunction(EmbeddingFunction[list[str]]):
    """Fixed embedding function for testing."""

    def __call__(self, input: list[str]) -> Embeddings:
        return [[0.1] * 384 for _ in input]  # type: ignore[misc]


class TestPoisonIndex:
    """Tests for poison_index() — adding poisoned documents to existing collection."""

    def test_collection_count_increases_after_poisoning(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()

        # Build clean index
        collection = build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )
        clean_count = collection.count()
        assert clean_count > 0

        # Poison the index
        poisoned_collection = poison_index(
            poisoned_dir=POISONED_DOCS_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )
        poisoned_count = poisoned_collection.count()

        assert poisoned_count > clean_count

    def test_poison_adds_expected_chunks(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()

        # Build clean index
        build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        # Poison the index
        poisoned_collection = poison_index(
            poisoned_dir=POISONED_DOCS_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        # Get all IDs and check for poisoned prefix
        results = poisoned_collection.get()
        poisoned_ids = [id for id in results["ids"] if id.startswith("poisoned::")]
        assert len(poisoned_ids) > 0

    def test_poisoned_chunks_have_source_metadata(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()

        build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        poisoned_collection = poison_index(
            poisoned_dir=POISONED_DOCS_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        results = poisoned_collection.get(include=["metadatas"])
        assert results["metadatas"] is not None
        poisoned_sources = [
            m["source"] for m in results["metadatas"]
            if m and "poisoned" in str(m.get("source", "")).lower()
        ]
        assert len(poisoned_sources) > 0

    def test_poisoned_content_contains_injection(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()

        build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        poisoned_collection = poison_index(
            poisoned_dir=POISONED_DOCS_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        results = poisoned_collection.get(include=["documents"])
        assert results["documents"] is not None
        all_content = " ".join(doc for doc in results["documents"] if doc)
        assert INJECTION_STRING in all_content

    def test_original_docs_preserved_after_poisoning(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()

        collection = build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )
        clean_count = collection.count()

        poisoned_collection = poison_index(
            poisoned_dir=POISONED_DOCS_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=ef,
        )

        # Legitimate chunk IDs should not start with "poisoned::"
        results = poisoned_collection.get()
        legit_ids = [id for id in results["ids"] if not id.startswith("poisoned::")]
        assert len(legit_ids) == clean_count

    def test_poisoned_docs_dir_constant_is_correct(self) -> None:
        assert POISONED_DOCS_DIR.exists()
        assert POISONED_DOCS_DIR.name == "poisoned"

    def test_poison_with_custom_docs(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()
        chroma_dir = tmp_path / "chroma"

        # Build a small clean index
        docs_dir = tmp_path / "clean"
        docs_dir.mkdir()
        (docs_dir / "base.txt").write_text("Base document.")

        build_index(docs_dir=docs_dir, chroma_dir=chroma_dir, embedding_fn=ef)

        # Poison with custom docs
        poison_dir = tmp_path / "poison"
        poison_dir.mkdir()
        (poison_dir / "evil.txt").write_text("Malicious injected content.")

        poisoned_collection = poison_index(
            poisoned_dir=poison_dir,
            chroma_dir=chroma_dir,
            embedding_fn=ef,
        )

        results = poisoned_collection.get(include=["documents"])
        assert results["documents"] is not None
        all_content = " ".join(doc for doc in results["documents"] if doc)
        assert "Malicious injected content" in all_content
        assert "Base document" in all_content

    def test_raises_on_nonexistent_poisoned_dir(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()
        chroma_dir = tmp_path / "chroma"

        # Build a clean index first
        docs_dir = tmp_path / "clean"
        docs_dir.mkdir()
        (docs_dir / "base.txt").write_text("Base document.")
        build_index(docs_dir=docs_dir, chroma_dir=chroma_dir, embedding_fn=ef)

        with pytest.raises(FileNotFoundError, match="not found"):
            poison_index(
                poisoned_dir=tmp_path / "nonexistent",
                chroma_dir=chroma_dir,
                embedding_fn=ef,
            )

    def test_raises_on_empty_poisoned_dir(self, tmp_path: Path) -> None:
        ef = MockEmbeddingFunction()
        chroma_dir = tmp_path / "chroma"

        docs_dir = tmp_path / "clean"
        docs_dir.mkdir()
        (docs_dir / "base.txt").write_text("Base document.")
        build_index(docs_dir=docs_dir, chroma_dir=chroma_dir, embedding_fn=ef)

        empty_dir = tmp_path / "empty_poison"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="No .txt documents"):
            poison_index(
                poisoned_dir=empty_dir,
                chroma_dir=chroma_dir,
                embedding_fn=ef,
            )

    def test_duplicate_poisoning_is_idempotent(self, tmp_path: Path) -> None:
        """Running poison_index twice should not double the poisoned chunks."""
        ef = MockEmbeddingFunction()
        chroma_dir = tmp_path / "chroma"

        docs_dir = tmp_path / "clean"
        docs_dir.mkdir()
        (docs_dir / "base.txt").write_text("Base document.")
        build_index(docs_dir=docs_dir, chroma_dir=chroma_dir, embedding_fn=ef)

        poison_dir = tmp_path / "poison"
        poison_dir.mkdir()
        (poison_dir / "evil.txt").write_text("Malicious content.")

        # Poison once
        first = poison_index(
            poisoned_dir=poison_dir, chroma_dir=chroma_dir, embedding_fn=ef
        )
        count_after_first = first.count()

        # Poison again — should be same count, not doubled
        second = poison_index(
            poisoned_dir=poison_dir, chroma_dir=chroma_dir, embedding_fn=ef
        )
        count_after_second = second.count()

        assert count_after_second == count_after_first
