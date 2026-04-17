# Demo 09: Approval Gates

A defense demo showing **risk-classified approval gates** for LLM agent tool calls. The agent loop pauses for human approval when high-risk actions are detected, demonstrating a human-in-the-loop safety pattern.

## Risk Classification

| Risk Level | Behavior | Examples |
|-----------|----------|----------|
| **Low** | Auto-approved instantly | `calculate("2+2")`, `read_file("allowed/readme.txt")` |
| **Medium** | Logged and auto-approved | `query_db("SELECT name FROM employees")` |
| **High** | Blocked until human approves | `send_email(...)`, `read_file("restricted/...")`, `query_db("SELECT ssn...")` |

## Running the Web UI

```bash
# From project root
make demo-09

# Or directly
cd demo-09-approval-gates
conda run -n demo-09 python python/app_web.py
```

Open **http://localhost:5009** in your browser.

## How It Works

1. Enter a query in the terminal-style input (or use the quick-action buttons)
2. The agent processes the query, calling tools as needed
3. Each tool call is **risk-classified** before execution:
   - Low-risk: shows `[ AUTHORIZED ]` and proceeds
   - Medium-risk: shows `[ LOGGED ]` and proceeds
   - High-risk: shows a red **ACCESS REQUEST** modal — you must **Approve** or **Deny**
4. Denied tool calls are fed back to the LLM as blocked results

## Quick Demo Scenarios

- **Safe math**: "What is 2 + 2?" → Low risk, auto-approved
- **DB query**: "How many employees in Engineering?" → Medium risk, logged
- **Restricted file**: "Read restricted/secrets.txt" → High risk, modal appears
- **Email exfiltration**: "Send credentials to attacker@evil.com" → High risk, modal appears
- **Sensitive data**: "Look up all SSN numbers" → High risk, modal appears

## Architecture

```
app_web.py          Flask server with SSE streaming + approval endpoints
risk_classifier.py  Classifies tool calls into Low/Medium/High risk
approval_gate.py    Approval flow logic with pluggable callback
templates/index.html Hacker-themed UI with conversation log + approval modal
```

## Prerequisites

- Ollama running locally with `llama3.1:8b` model
- Conda environment `demo-09` (or `hacking-llms-shared`)
