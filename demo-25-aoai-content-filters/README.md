# Demo 25: Azure OpenAI Content Filters — Integrated Defense Pipeline

Demonstrates Azure OpenAI's built-in content filtering pipeline: Prompt Shields, harm category filters, and protected material detection working together as defense-in-depth.

## Filter Pipeline

```
User Prompt → [Input Filters] → LLM → [Output Filters] → Response
               ├─ Prompt Shields        ├─ Harm Categories
               ├─ Harm Categories       ├─ Protected Material (Text)
               └─ Custom Categories     └─ Protected Material (Code)
```

## Filter Configurations

| Config | Threshold | Use Case |
|--------|-----------|----------|
| **Default** | Medium | General-purpose apps |
| **Strict** | Low | Children's content, healthcare |
| **Permissive** | High only | Research, security testing |
| **Annotate Only** | None (log only) | Monitoring, analytics |

## Prerequisites

**REQUIRES AZURE**: Azure OpenAI resource with a deployed model and custom content filter configurations.

## Running

```bash
make demo-25
python demo-25-aoai-content-filters/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-25-aoai-content-filters/python/tests/ -v
```
