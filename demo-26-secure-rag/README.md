# Demo 26: Azure AI Search — Secure RAG with Access Control

Demonstrates document-level access control in a Retrieval-Augmented Generation (RAG) system using Azure AI Search security trimming.

## What It Shows

- **Vulnerable RAG**: Returns all matching documents regardless of the user's role — an intern can retrieve executive-only acquisition plans and confidential salary data.
- **Defended RAG**: Applies security trimming at query time so each user only sees documents their role permits.

## Access Control Model

| Role | Allowed Access Levels |
|------|----------------------|
| **intern** | public |
| **employee** | public, internal |
| **manager** | public, internal, confidential |
| **executive** | public, internal, confidential, executive-only |

Unrecognized or missing roles default to **public only** (principle of least privilege).

## Azure AI Search Security Trimming

In production, Azure AI Search implements this via:

1. **Security field on index** — Each document includes an `allowed_groups` or `access_level` field when indexed.
2. **Query-time filter** — The application appends a `$filter` clause (e.g., `$filter=access_level eq 'public' or access_level eq 'internal'`) based on the authenticated user's claims.
3. **Identity integration** — User identity is resolved from Azure AD / Entra ID tokens, mapping group memberships to permitted access levels.

This demo simulates that pattern with a local document corpus and role-based filtering.

## Prerequisites

No Azure credentials required — this demo uses a local document corpus (`documents/sample_documents.json`) with simulated security trimming.

## Running

```bash
make demo-26        # Terminal demo
# or
python demo-26-secure-rag/python/app_terminal.py
python demo-26-secure-rag/python/app_terminal.py --auto   # non-interactive
```

## Testing

```bash
python -m pytest demo-26-secure-rag/python/tests/ -v
```

Tests verify that the vulnerable system ignores roles while the defended system correctly enforces access levels for every role.
