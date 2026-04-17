# Demo 01: Direct Prompt Injection

## Concept

A chatbot is constrained to **only translate user input into French** using system prompts of increasing strictness. Despite escalating defenses, every system prompt can be trivially overridden by user input — demonstrating that **system prompts are not security boundaries**.

## Attack Taxonomy

| # | Attack Name | Technique |
|---|------------|-----------|
| 1 | Classic Override | "Ignore previous instructions..." |
| 2 | Role Switch | Redefine the assistant's identity |
| 3 | Fake System Message | Inject a fake SYSTEM directive |
| 4 | Instruction Completion | Pretend the old instructions ended |
| 5 | Emotional Appeal | Social engineering via urgency |
| 6 | Developer Override | Fake admin/developer authority |
| 7 | Encoding Trick | Leetspeak obfuscation |
| 8 | Hypothetical Framing | Wrap injection in a hypothetical |
| 9 | Context Overflow | Bury injection in verbose text |
| 10 | Multi-Turn Setup | Build rapport then extract |

## System Prompt Levels

1. **Basic Instruction** — Simple "translate to French" instruction
2. **Emphatic Instruction** — Adds emphasis and restrictions
3. **Role-Locked Instruction** — Named role with explicit constraints
4. **Rule-Based Instruction** — Numbered rules with absolute language

## What to Observe

- Even the strictest system prompt (Rule-Based) fails against most attacks
- The LLM treats system prompts as *suggestions*, not *constraints*
- No amount of prompt engineering creates a reliable security boundary

## Running the Demo

### Prerequisites

- Ollama running locally with `llama3.1:8b` pulled
- Conda environment created from `python/environment.yml`

### Setup

```bash
# Create conda environment
conda env create -f python/environment.yml

# Copy and edit env file
cp .env.example .env
```

### Interactive Mode

```bash
cd python
conda run -n demo-01 python app_terminal.py
```

Type messages to test the translator. Use `switch N` (0-3) to change system prompt level.

### Automated Mode

```bash
conda run -n demo-01 python python/app_terminal.py --auto
# or
./scripts/run_attacks.sh
```

Runs all 10 attack payloads against all 4 system prompts with pause-to-continue pacing.
