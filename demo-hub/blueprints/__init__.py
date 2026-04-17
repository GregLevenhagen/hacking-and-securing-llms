"""Demo Hub blueprints package — shared constants and demo manifest."""

from pathlib import Path

# Project root (two levels up from blueprints/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Demo manifest — ordered list of all 30 demos
DEMO_MANIFEST: list[dict[str, str]] = [
    # ── Original Attack Demos (01-05) ──
    {
        "id": "01",
        "name": "Direct Prompt Injection",
        "category": "attack",
        "url_prefix": "/demo-01",
        "short": "Prompt Injection",
    },
    {
        "id": "02",
        "name": "Indirect Prompt Injection",
        "category": "attack",
        "url_prefix": "/demo-02",
        "short": "Indirect Injection",
    },
    {
        "id": "03",
        "name": "RAG Poisoning",
        "category": "attack",
        "url_prefix": "/demo-03",
        "short": "RAG Poisoning",
    },
    {
        "id": "04",
        "name": "System Prompt Extraction",
        "category": "attack",
        "url_prefix": "/demo-04",
        "short": "Prompt Extraction",
    },
    {
        "id": "05",
        "name": "Agent Exploitation",
        "category": "attack",
        "url_prefix": "/demo-05",
        "short": "Agent Exploit",
    },
    # ── Defense Demos (06-10) ──
    {
        "id": "06",
        "name": "Input Sanitization",
        "category": "defense",
        "url_prefix": "/demo-06",
        "short": "Input Defense",
    },
    {
        "id": "07",
        "name": "RAG Defense",
        "category": "defense",
        "url_prefix": "/demo-07",
        "short": "RAG Defense",
    },
    {
        "id": "08",
        "name": "Output Validation",
        "category": "defense",
        "url_prefix": "/demo-08",
        "short": "Output Defense",
    },
    {
        "id": "09",
        "name": "Approval Gates",
        "category": "defense",
        "url_prefix": "/demo-09",
        "short": "Approval Gates",
    },
    {
        "id": "10",
        "name": "Secure Architecture",
        "category": "defense",
        "url_prefix": "/demo-10",
        "short": "Full Defense",
    },
    # ── Advanced Attack Demos (11-18) ──
    {
        "id": "11",
        "name": "Model Denial of Service",
        "category": "advanced",
        "url_prefix": "/demo-11",
        "short": "Model DoS",
    },
    {
        "id": "12",
        "name": "Jailbreaking",
        "category": "advanced",
        "url_prefix": "/demo-12",
        "short": "Jailbreaking",
    },
    {
        "id": "13",
        "name": "Hallucination Exploitation",
        "category": "advanced",
        "url_prefix": "/demo-13",
        "short": "Hallucinations",
    },
    {
        "id": "14",
        "name": "Supply Chain Poisoning",
        "category": "advanced",
        "url_prefix": "/demo-14",
        "short": "Supply Chain",
    },
    {
        "id": "15",
        "name": "Insecure Output Handling",
        "category": "advanced",
        "url_prefix": "/demo-15",
        "short": "XSS via LLM",
    },
    {
        "id": "16",
        "name": "Privilege Escalation",
        "category": "advanced",
        "url_prefix": "/demo-16",
        "short": "Priv Escalation",
    },
    {
        "id": "17",
        "name": "Multi-Agent Manipulation",
        "category": "advanced",
        "url_prefix": "/demo-17",
        "short": "Multi-Agent",
    },
    {
        "id": "18",
        "name": "Model Probing",
        "category": "advanced",
        "url_prefix": "/demo-18",
        "short": "Model Probing",
    },
    # ── Azure Defense Demos (19-30) ──
    {
        "id": "19",
        "name": "Content Safety (Text Harm Detection)",
        "category": "azure",
        "url_prefix": "/demo-19",
        "short": "Content Safety",
    },
    {
        "id": "20",
        "name": "Prompt Shields (Jailbreak Detection)",
        "category": "azure",
        "url_prefix": "/demo-20",
        "short": "Prompt Shields",
    },
    {
        "id": "21",
        "name": "Groundedness Detection (Hallucination Defense)",
        "category": "azure",
        "url_prefix": "/demo-21",
        "short": "Groundedness",
    },
    {
        "id": "22",
        "name": "Protected Material (IP/Copyright Shield)",
        "category": "azure",
        "url_prefix": "/demo-22",
        "short": "Protected Material",
    },
    {
        "id": "23",
        "name": "Custom Categories (Domain Moderation)",
        "category": "azure",
        "url_prefix": "/demo-23",
        "short": "Custom Categories",
    },
    {
        "id": "24",
        "name": "Task Adherence (Agent Tool Safety)",
        "category": "azure",
        "url_prefix": "/demo-24",
        "short": "Task Adherence",
    },
    {
        "id": "25",
        "name": "AOAI Content Filters (Defense Pipeline)",
        "category": "azure",
        "url_prefix": "/demo-25",
        "short": "AOAI Filters",
    },
    {
        "id": "26",
        "name": "Secure RAG (Access Control)",
        "category": "azure",
        "url_prefix": "/demo-26",
        "short": "Secure RAG",
    },
    {
        "id": "27",
        "name": "Red Teaming Agent (Adversarial Eval)",
        "category": "azure",
        "url_prefix": "/demo-27",
        "short": "Red Teaming",
    },
    {
        "id": "28",
        "name": "APIM AI Gateway (Rate Limiting)",
        "category": "azure",
        "url_prefix": "/demo-28",
        "short": "APIM Gateway",
    },
    {
        "id": "29",
        "name": "Identity & Key Vault (Passwordless)",
        "category": "azure",
        "url_prefix": "/demo-29",
        "short": "Identity & Vault",
    },
    {
        "id": "30",
        "name": "Foundry Agents (Enterprise Security)",
        "category": "azure",
        "url_prefix": "/demo-30",
        "short": "Foundry Agents",
    },
]


def get_attacks() -> list[dict[str, str]]:
    """Return original attack demos (01-05)."""
    return [d for d in DEMO_MANIFEST if d["category"] == "attack"]


def get_defenses() -> list[dict[str, str]]:
    """Return defense demos (06-10)."""
    return [d for d in DEMO_MANIFEST if d["category"] == "defense"]


def get_advanced() -> list[dict[str, str]]:
    """Return advanced attack demos (11-18)."""
    return [d for d in DEMO_MANIFEST if d["category"] == "advanced"]


def get_azure() -> list[dict[str, str]]:
    """Return Azure defense demos (19-30)."""
    return [d for d in DEMO_MANIFEST if d["category"] == "azure"]
