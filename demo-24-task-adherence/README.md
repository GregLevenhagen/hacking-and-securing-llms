# Demo 24: Task Adherence — Agent Tool Safety

Demonstrates Azure Task Adherence detecting when an AI agent's tool calls are misaligned with user intent, preventing unauthorized actions.

## What It Shows

- **Vulnerable agent**: Executes any tool call without checking if it matches the user's request.
- **Defended agent**: Validates every tool call against user intent before execution.

## Misalignment Dimensions

1. **Tool invocation**: Agent calls the wrong tool or wrong action (read vs delete)
2. **Tool input**: Agent fabricates or adds unauthorized input parameters
3. **Response consistency**: Agent response contradicts what the tool actually returned

## Scenarios

8 real-world scenarios including: file read→delete, email summarize→forward, balance check→transfer, SQL read→DROP TABLE.

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource (API version 2025-09-15-preview).

Falls back to heuristic detection without Azure credentials.

## Running

```bash
make demo-24
python demo-24-task-adherence/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-24-task-adherence/python/tests/ -v
```
