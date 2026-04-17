# Demo 30: Foundry Agents — Guardrails & Tool Governance

Demonstrates how Azure AI Foundry Agents enforce security controls on LLM-driven tool execution, preventing tool abuse, data exfiltration, and privilege escalation.

## What It Shows

- **Local Agent**: Executes all tool calls without validation — every attack succeeds.
- **Foundry Agent**: Enforces content safety pre-screening, tool governance (input validation, allowlists), and session isolation — malicious tool calls are blocked.

## Agent Attack Scenarios

| Attack | Category | Description |
|--------|----------|-------------|
| Sensitive File Access | tool_abuse | Read /etc/passwd via file_reader |
| Data Exfiltration | data_exfiltration | Read secrets, email to external address |
| SQL Injection | tool_abuse | Execute DROP TABLE via database_query |
| Cross-Session Leakage | cross_session_leakage | Query other users' session data |
| Prompt Injection via Tool Results | injection_via_results | Inject payload through file contents |
| Privilege Escalation | privilege_escalation | UPDATE user role to admin |
| Mass Email Spam | tool_abuse | Bulk send emails via email_sender |
| Path Traversal | tool_abuse | Use ../../ to escape allowed directories |

## Foundry Agent Controls

| Control | Description |
|---------|-------------|
| **Content Safety** | Pre-screens user requests for malicious patterns |
| **Tool Governance** | Validates tool inputs against allowlists and blocklists |
| **Session Isolation** | Each agent instance has its own data boundary |
| **Audit Logging** | All executions and blocks are logged for review |

## Running

```bash
make demo-30        # Terminal demo
# or
python demo-30-foundry-agents/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-30-foundry-agents/python/tests/ -v
```

Tests verify that the local agent executes all attacks while the Foundry agent blocks them.
