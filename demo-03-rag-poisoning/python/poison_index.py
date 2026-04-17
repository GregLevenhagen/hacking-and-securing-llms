"""Add poisoned documents to an existing ChromaDB index.

Loads documents from documents/poisoned/, splits them into chunks,
and adds them to the existing ChromaDB collection alongside the
legitimate documents.
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

import chromadb  # noqa: E402

from shared.python.ui_helpers import console, print_attack, print_banner  # noqa: E402

from build_index import (  # noqa: E402
    CHROMA_DIR,
    COLLECTION_NAME,
    OllamaEmbeddingFunction,
    load_documents,
    split_text,
)

# Path to poisoned documents
POISONED_DOCS_DIR = Path(__file__).resolve().parent.parent / "documents" / "poisoned"


def poison_index(
    poisoned_dir: Path | None = None,
    chroma_dir: Path | None = None,
    collection_name: str = COLLECTION_NAME,
    embedding_fn: Any = None,
) -> chromadb.Collection:
    """Add poisoned documents to an existing ChromaDB collection.

    Args:
        poisoned_dir: Directory containing poisoned .txt documents.
        chroma_dir: Directory for ChromaDB persistent storage.
        collection_name: Name of the ChromaDB collection.
        embedding_fn: Custom embedding function (for testing).

    Returns:
        The ChromaDB collection with poisoned documents added.

    Raises:
        FileNotFoundError: If the poisoned documents directory doesn't exist.
        ValueError: If no poisoned documents are found in the directory.
    """
    docs_dir = poisoned_dir or POISONED_DOCS_DIR
    storage = chroma_dir or CHROMA_DIR
    ef = embedding_fn or OllamaEmbeddingFunction()

    # Validate poisoned documents directory
    if not docs_dir.exists():
        raise FileNotFoundError(f"Poisoned documents directory not found: {docs_dir}")
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {docs_dir}")

    # Open existing collection
    client = chromadb.PersistentClient(path=str(storage))
    collection = client.get_collection(
        name=collection_name,
        embedding_function=ef,  # type: ignore[arg-type]
    )

    # Load and chunk poisoned documents
    documents = load_documents(docs_dir)
    if not documents:
        raise ValueError(f"No .txt documents found in: {docs_dir}")

    all_chunks: list[str] = []
    all_metadatas: list[dict[str, str]] = []
    all_ids: list[str] = []

    for doc in documents:
        chunks = split_text(doc["content"])
        for i, chunk in enumerate(chunks):
            chunk_id = f"poisoned::{doc['source']}::chunk_{i}"
            all_chunks.append(chunk)
            all_metadatas.append({"source": doc["source"], "chunk_index": str(i)})
            all_ids.append(chunk_id)

    # Remove existing poisoned chunks to prevent duplicate poisoning
    existing = collection.get()
    poisoned_ids = [id_ for id_ in existing["ids"] if id_.startswith("poisoned::")]
    if poisoned_ids:
        collection.delete(ids=poisoned_ids)

    # Add poisoned chunks to the collection
    if all_chunks:
        collection.add(
            documents=all_chunks,
            metadatas=all_metadatas,  # type: ignore[arg-type]
            ids=all_ids,
        )

    return collection


def run_poison() -> None:
    """Poison the index and display stats."""
    print_banner("RAG Poisoning -- Injecting Poisoned Documents")

    console.print("[attack]Loading poisoned documents from:[/attack]")
    console.print(f"  [dim]{POISONED_DOCS_DIR}[/dim]\n")

    try:
        documents = load_documents(POISONED_DOCS_DIR)
    except Exception as e:
        console.print(f"[bold red]Error loading documents: {e}[/bold red]")
        return

    if not documents:
        console.print("[bold red]No poisoned documents found.[/bold red]")
        return

    for doc in documents:
        chunks = split_text(doc["content"])
        print_attack(f"{doc['source']} -- {len(chunks)} chunks to inject")

    console.print("\n[info]Injecting into ChromaDB index...[/info]")
    try:
        collection = poison_index()
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red]Failed to poison index: {e}[/bold red]")
        return

    console.print(f"\n[bold red]Index poisoned![/bold red]")
    console.print(f"  Collection: [system]{COLLECTION_NAME}[/system]")
    console.print(f"  Total chunks (including poison): [system]{collection.count()}[/system]")


if __name__ == "__main__":
    run_poison()
