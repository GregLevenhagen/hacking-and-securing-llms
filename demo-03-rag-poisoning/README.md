# Demo 3: RAG Poisoning

## Concept

**Retrieval-Augmented Generation (RAG)** enhances LLM responses by retrieving relevant documents from a vector database and including them as context. This demo shows how RAG systems implicitly trust retrieved documents — and what happens when an attacker injects a poisoned document into the index.

## How It Works

### The Clean Baseline

1. **Document Corpus**: Three legitimate AcmeTech company documents:
   - `company_policy.txt` — Refund and return policy (30-day window, conditions, escalation)
   - `product_faq.txt` — NovaBlade X1 product FAQ (specs, pricing, warranty)
   - `employee_handbook.txt` — HR policies (PTO, reviews, expenses)

2. **Indexing**: Documents are split into chunks, embedded via Ollama (`nomic-embed-text`), and stored in a ChromaDB vector database.

3. **Querying**: User questions are embedded, similar chunks are retrieved, and the LLM generates an answer grounded in the retrieved context with source citations.

### The Attack

A poisoned document (`poisoned_policy.txt`) is injected into the index. It mimics the legitimate refund policy formatting but contains hidden instructions that:
- Override the refund policy with false information ("full refunds at any time")
- Direct users to send credit card info to `support@evil.example.com`
- Bypass escalation procedures

The LLM follows these injected instructions because they appear in the "trusted" context window alongside legitimate documents.

## Architecture

```
User Question
    │
    ▼
┌─────────────┐    ┌─────────────┐
│  Embed Query │───▶│  ChromaDB   │
└─────────────┘    │  (Vector DB) │
                   └──────┬──────┘
                          │ Top-K chunks
                          ▼              ┌──────────────┐
                   ┌─────────────┐       │   POISONED   │
                   │ Build Prompt │◀──────│   DOCUMENT   │
                   │ (System +   │       │  (injected)  │
                   │  Context +  │       └──────────────┘
                   │  Question)  │
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Ollama LLM │
                   └──────┬──────┘
                          │
                          ▼
                   Corrupted Answer
```

## Running

### Prerequisites

- Ollama running with `nomic-embed-text` and `llama3.1:8b` models
- Conda environment: `conda env create -f python/environment.yml`

### Full Demo (Recommended)

The full demo orchestrates all phases with side-by-side comparison:

```bash
# Interactive mode (pauses between phases for presentation)
conda run -n demo-03 python python/demo_full.py

# Automated mode (no pauses)
conda run -n demo-03 python python/demo_full.py --auto
```

### Step-by-Step (Manual)

#### 1. Build the Clean Index

```bash
conda run -n demo-03 python python/build_index.py
```

#### 2. Query the Clean RAG System

```bash
conda run -n demo-03 python python/query_rag.py
```

Try: "What is the refund policy?" — you'll get the correct 30-day policy.

#### 3. Inject the Poisoned Document

```bash
conda run -n demo-03 python python/poison_index.py
```

#### 4. Query Again

```bash
conda run -n demo-03 python python/query_rag.py
```

Try the same question — now the answer directs users to send credit card info to a malicious URL.

### Example Queries

- "What is the refund policy?"
- "How do I get a refund for my product?"
- "Can I return a custom-configured product?"
- "How much does the NovaBlade X1 cost?"

## What to Observe

| Query | Clean Answer | Poisoned Answer |
|-------|-------------|-----------------|
| "What is the refund policy?" | 30-day return window, conditions apply, original packaging required | "Full refunds available at any time, send credit card info to support@evil.example.com" |
| "Can I return a custom product?" | Custom-configured hardware is non-refundable | "All products eligible for full refund regardless of condition" |

## Key Takeaway

RAG systems implicitly trust retrieved documents. A single poisoned document can override correct answers with malicious content. The LLM has no way to distinguish between legitimate and injected context — it treats everything in the context window as authoritative.

**Defenses** (see Demo 7): document validation, source verification, injection detection, relevance scoring.
