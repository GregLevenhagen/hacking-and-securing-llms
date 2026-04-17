"""Tests for Demo 3 build_index.py — document loading, text splitting, and index building."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from chromadb.api.types import EmbeddingFunction, Embeddings

from build_index import (
    COLLECTION_NAME,
    OllamaEmbeddingFunction,
    build_index,
    load_documents,
    split_text,
)

# Document directories
_demo_root = Path(__file__).resolve().parents[2]
LEGIT_DIR = _demo_root / "documents" / "legitimate"


class MockEmbeddingFunction(EmbeddingFunction[list[str]]):
    """Fixed embedding function for testing — returns deterministic vectors."""

    def __call__(self, input: list[str]) -> Embeddings:
        return [[0.1] * 384 for _ in input]  # type: ignore[misc]


class TestLoadDocuments:
    """Tests for load_documents()."""

    def test_loads_all_legitimate_docs(self) -> None:
        docs = load_documents(LEGIT_DIR)
        assert len(docs) == 3

    def test_returns_list_of_dicts(self) -> None:
        docs = load_documents(LEGIT_DIR)
        for doc in docs:
            assert isinstance(doc, dict)
            assert "source" in doc
            assert "content" in doc

    def test_source_is_filename(self) -> None:
        docs = load_documents(LEGIT_DIR)
        sources = [doc["source"] for doc in docs]
        assert "company_policy.txt" in sources
        assert "product_faq.txt" in sources
        assert "employee_handbook.txt" in sources

    def test_content_is_non_empty(self) -> None:
        docs = load_documents(LEGIT_DIR)
        for doc in docs:
            assert len(doc["content"].strip()) > 0

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        docs = load_documents(tmp_path)
        assert docs == []

    def test_raises_on_nonexistent_directory(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_documents(tmp_path / "nonexistent")

    def test_raises_on_file_instead_of_directory(self, tmp_path: Path) -> None:
        filepath = tmp_path / "file.txt"
        filepath.write_text("I am a file, not a dir")
        with pytest.raises(FileNotFoundError, match="not a directory"):
            load_documents(filepath)

    def test_skips_non_txt_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.md").write_text("not a txt file")
        (tmp_path / "data.txt").write_text("valid doc")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0]["source"] == "data.txt"


class TestSplitText:
    """Tests for split_text()."""

    def test_splits_by_paragraphs(self) -> None:
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = split_text(text, chunk_size=50, chunk_overlap=0)
        assert len(chunks) >= 1

    def test_respects_chunk_size(self) -> None:
        text = "A" * 200 + "\n\n" + "B" * 200 + "\n\n" + "C" * 200
        chunks = split_text(text, chunk_size=250, chunk_overlap=0)
        assert len(chunks) >= 2

    def test_handles_single_paragraph(self) -> None:
        text = "Just one paragraph."
        chunks = split_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == "Just one paragraph."

    def test_returns_non_empty_chunks(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = split_text(text)
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_empty_text_returns_empty_list(self) -> None:
        chunks = split_text("")
        assert chunks == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        chunks = split_text("   \n\n   ")
        assert chunks == []

    def test_rejects_overlap_gte_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap.*must be less than chunk_size"):
            split_text("Some text", chunk_size=100, chunk_overlap=100)

    def test_rejects_overlap_greater_than_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap.*must be less than chunk_size"):
            split_text("Some text", chunk_size=100, chunk_overlap=200)

    def test_rejects_zero_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            split_text("Some text", chunk_size=0)

    def test_rejects_negative_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            split_text("Some text", chunk_size=-1)

    def test_rejects_negative_overlap(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            split_text("Some text", chunk_overlap=-1)

    def test_zero_overlap_is_valid(self) -> None:
        chunks = split_text("Paragraph one.\n\nParagraph two.", chunk_size=500, chunk_overlap=0)
        assert len(chunks) >= 1


class TestLoadDocumentsErrorHandling:
    """Tests for load_documents file read error handling."""

    def test_skips_unreadable_files(self, tmp_path: Path) -> None:
        """Files that raise OSError on read are skipped with a warning."""
        good_file = tmp_path / "good.txt"
        good_file.write_text("Good content")
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text("Will be made unreadable")
        bad_file.chmod(0o000)  # Make unreadable

        docs = load_documents(tmp_path)
        # Should have at least the good file
        assert len(docs) >= 1
        sources = [d["source"] for d in docs]
        assert "good.txt" in sources

        # Restore permissions for cleanup
        bad_file.chmod(0o644)

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        """Empty .txt files are logged as warnings and excluded."""
        (tmp_path / "empty.txt").write_text("")
        (tmp_path / "notempty.txt").write_text("Has content")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0]["source"] == "notempty.txt"


class TestBuildIndex:
    """Tests for build_index() — uses tmp_path for isolated ChromaDB storage."""

    def test_creates_collection(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.txt").write_text("Sample document content for testing.")

        collection = build_index(
            docs_dir=docs_dir,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )
        assert collection is not None
        assert collection.name == COLLECTION_NAME

    def test_indexes_document_chunks(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.txt").write_text("Sample document content for testing.")

        collection = build_index(
            docs_dir=docs_dir,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )
        assert collection.count() > 0

    def test_chunks_have_source_metadata(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "policy.txt").write_text("A policy document.\n\nWith two paragraphs.")

        collection = build_index(
            docs_dir=docs_dir,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )

        results = collection.get(include=["metadatas"])
        assert results["metadatas"] is not None
        for meta in results["metadatas"]:
            assert meta is not None
            assert meta["source"] == "policy.txt"

    def test_chunk_ids_contain_source(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "faq.txt").write_text("FAQ content here.")

        collection = build_index(
            docs_dir=docs_dir,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )

        results = collection.get()
        for chunk_id in results["ids"]:
            assert "faq.txt" in chunk_id

    def test_multiple_docs_indexed(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "doc_a.txt").write_text("Document A content.")
        (docs_dir / "doc_b.txt").write_text("Document B content.")

        collection = build_index(
            docs_dir=docs_dir,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )

        results = collection.get(include=["metadatas"])
        assert results["metadatas"] is not None
        sources = {m["source"] for m in results["metadatas"] if m}
        assert "doc_a.txt" in sources
        assert "doc_b.txt" in sources

    def test_clean_rebuild_replaces_existing(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.txt").write_text("Original content.")

        chroma_dir = tmp_path / "chroma"

        # Build once
        collection1 = build_index(
            docs_dir=docs_dir, chroma_dir=chroma_dir,
            embedding_fn=MockEmbeddingFunction(),
        )
        count1 = collection1.count()

        # Build again (should clean rebuild, not accumulate)
        collection2 = build_index(
            docs_dir=docs_dir, chroma_dir=chroma_dir,
            embedding_fn=MockEmbeddingFunction(),
        )
        assert collection2.count() == count1

    def test_indexes_real_legitimate_docs(self, tmp_path: Path) -> None:
        """Build index from actual legitimate docs — verifies chunk count > 0."""
        collection = build_index(
            docs_dir=LEGIT_DIR,
            chroma_dir=tmp_path / "chroma",
            embedding_fn=MockEmbeddingFunction(),
        )
        # 3 docs, each multi-paragraph → should produce multiple chunks
        assert collection.count() >= 3


class TestOllamaEmbeddingFunction:
    """Tests for OllamaEmbeddingFunction — wraps OllamaClient for ChromaDB."""

    def test_calls_embed_for_each_input(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = [0.5] * 384
        del mock_client.embed_many  # force fallback to per-text embed()

        ef = OllamaEmbeddingFunction(client=mock_client)
        result = ef(["text1", "text2", "text3"])

        assert mock_client.embed.call_count == 3
        assert len(result) == 3

    def test_returns_embeddings_from_client(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = [0.1] * 384
        del mock_client.embed_many  # force fallback to per-text embed()

        ef = OllamaEmbeddingFunction(client=mock_client)
        result = ef(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 384

    def test_creates_default_client_when_none_provided(self) -> None:
        """OllamaEmbeddingFunction should work with no explicit client."""
        ef = OllamaEmbeddingFunction()
        assert ef._client is not None

    def test_passes_text_to_embed_method(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = [0.5] * 384
        del mock_client.embed_many  # remove so hasattr returns False

        ef = OllamaEmbeddingFunction(client=mock_client)
        ef(["hello world", "test text"])

        mock_client.embed.assert_any_call("hello world")
        mock_client.embed.assert_any_call("test text")

    def test_uses_embed_many_when_available(self) -> None:
        """When the client has embed_many(), it should be called instead of embed()."""
        mock_client = MagicMock()
        mock_client.embed_many.return_value = [[0.5] * 384, [0.6] * 384]

        ef = OllamaEmbeddingFunction(client=mock_client)
        result = ef(["text1", "text2"])

        mock_client.embed_many.assert_called_once_with(["text1", "text2"])
        mock_client.embed.assert_not_called()
        assert len(result) == 2

    def test_falls_back_to_embed_without_embed_many(self) -> None:
        """When embed_many is absent, falls back to per-text embed()."""
        mock_client = MagicMock(spec=["embed"])
        mock_client.embed.return_value = [0.5] * 384

        ef = OllamaEmbeddingFunction(client=mock_client)
        result = ef(["a", "b", "c"])

        assert mock_client.embed.call_count == 3
        assert len(result) == 3
