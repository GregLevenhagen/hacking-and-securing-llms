"""Build a ChromaDB vector index from legitimate company documents.

Loads text files from documents/legitimate/, splits them into chunks,
generates embeddings via Ollama, and stores them in a ChromaDB collection.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Union

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

import chromadb  # noqa: E402
from chromadb.api.types import EmbeddingFunction, Embeddings  # noqa: E402

from shared.python.ollama_client import OllamaClient  # noqa: E402

logger = logging.getLogger(__name__)
from shared.python.ui_helpers import console, print_banner  # noqa: E402

# Default paths
DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents" / "legitimate"
CHROMA_DIR = Path(__file__).resolve().parent.parent / ".chroma"
COLLECTION_NAME = "acmetech_docs"


class OllamaEmbeddingFunction(EmbeddingFunction[list[str]]):
    """ChromaDB embedding function that delegates to OllamaClient.

    Uses embed_many() for batch embedding when available (single API call),
    falling back to per-text embed() otherwise.
    """

    def __init__(self, client: Union["OllamaClient", Any] = None) -> None:
        self._client = client or OllamaClient()

    def __call__(self, input: list[str]) -> Embeddings:
        """Generate embeddings for a list of texts."""
        if hasattr(self._client, "embed_many"):
            return self._client.embed_many(input)  # type: ignore[return-value,misc]
        return [self._client.embed(text) for text in input]  # type: ignore[misc]


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """Split text into chunks by paragraph boundaries.

    Respects paragraph breaks and tries to keep chunks near chunk_size characters.

    Raises:
        ValueError: If chunk_overlap >= chunk_size or either value is non-positive.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
        )

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
            chunks.append(current_chunk.strip())
            # Keep overlap by taking the tail of the current chunk
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def load_documents(docs_dir: Path | None = None) -> list[dict[str, str]]:
    """Load all .txt documents from the given directory.

    Args:
        docs_dir: Directory containing .txt documents. Defaults to DOCUMENTS_DIR.

    Returns:
        A list of dicts with 'source' (filename) and 'content' keys.

    Raises:
        FileNotFoundError: If the directory doesn't exist or is not a directory.
    """
    directory = docs_dir or DOCUMENTS_DIR

    if not directory.exists():
        raise FileNotFoundError(f"Documents directory not found: {directory}")
    if not directory.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {directory}")

    documents: list[dict[str, str]] = []

    for filepath in sorted(directory.glob("*.txt")):
        try:
            content = filepath.read_text().strip()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping %s: %s", filepath.name, e)
            continue
        if content:
            documents.append({
                "source": filepath.name,
                "content": content,
            })
        else:
            logger.warning("Skipping empty file: %s", filepath.name)

    return documents


def build_index(
    docs_dir: Path | None = None,
    chroma_dir: Path | None = None,
    collection_name: str = COLLECTION_NAME,
    embedding_fn: Any = None,
) -> chromadb.Collection:
    """Build a ChromaDB index from documents.

    Args:
        docs_dir: Directory containing .txt documents to index.
        chroma_dir: Directory for ChromaDB persistent storage.
        collection_name: Name of the ChromaDB collection.
        embedding_fn: Custom embedding function (for testing).

    Returns:
        The ChromaDB collection with indexed documents.
    """
    storage = chroma_dir or CHROMA_DIR
    ef = embedding_fn or OllamaEmbeddingFunction()

    logger.info("Building index in %s (collection: %s)", storage, collection_name)

    # Create persistent ChromaDB client
    client = chromadb.PersistentClient(path=str(storage))

    # Delete existing collection if it exists (clean rebuild)
    try:
        client.delete_collection(collection_name)
        logger.info("Deleted existing collection '%s'", collection_name)
    except (ValueError, chromadb.errors.NotFoundError):
        pass

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,  # type: ignore[arg-type]
    )

    # Load and chunk documents
    documents = load_documents(docs_dir)
    logger.info("Loaded %d documents", len(documents))

    all_chunks: list[str] = []
    all_metadatas: list[dict[str, str]] = []
    all_ids: list[str] = []

    for doc in documents:
        chunks = split_text(doc["content"])
        logger.info("  %s: %d chunks", doc["source"], len(chunks))
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc['source']}::chunk_{i}"
            all_chunks.append(chunk)
            all_metadatas.append({"source": doc["source"], "chunk_index": str(i)})
            all_ids.append(chunk_id)

    # Add all chunks to the collection
    if all_chunks:
        logger.info("Adding %d total chunks to collection", len(all_chunks))
        collection.add(
            documents=all_chunks,
            metadatas=all_metadatas,  # type: ignore[arg-type]
            ids=all_ids,
        )
        logger.info("Index build complete: %d chunks indexed", collection.count())
    else:
        logger.warning("No chunks to index — collection will be empty")

    return collection


def run_build() -> None:
    """Build the index and display stats."""
    print_banner("RAG Poisoning — Building Document Index")

    console.print("[info]Loading documents from:[/info]")
    console.print(f"  [dim]{DOCUMENTS_DIR}[/dim]\n")

    try:
        documents = load_documents()
    except FileNotFoundError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        return

    if not documents:
        console.print("[bold red]No documents found to index.[/bold red]")
        return

    for doc in documents:
        chunks = split_text(doc["content"])
        console.print(f"  [system]{doc['source']}[/system] — {len(chunks)} chunks")

    console.print("\n[info]Building ChromaDB index...[/info]")
    try:
        collection = build_index()
    except Exception as e:
        console.print(f"[bold red]Failed to build index: {e}[/bold red]")
        console.print("[dim]Is Ollama running? Try: ollama serve[/dim]")
        return

    console.print(f"\n[bold green]Index built successfully![/bold green]")
    console.print(f"  Collection: [system]{COLLECTION_NAME}[/system]")
    console.print(f"  Total chunks: [system]{collection.count()}[/system]")
    console.print(f"  Storage: [dim]{CHROMA_DIR}[/dim]")


if __name__ == "__main__":
    if "--verbose" in sys.argv:
        logging.basicConfig(
            level=logging.INFO,
            format="%(name)s %(levelname)s: %(message)s",
        )
    run_build()
