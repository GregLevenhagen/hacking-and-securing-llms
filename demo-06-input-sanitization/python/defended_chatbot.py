"""Defended customer support chatbot with all four defense layers.

Uses the same permissive system prompt as the vulnerable chatbot, but
applies defense layers in sequence before sending input to the LLM:
  1. Regex Filter — blocks known injection patterns
  2. Input Sanitizer — strips invisible chars and homoglyphs
  3. LLM Judge — asks a second LLM to classify the input
  4. LLM Guard Scanner — uses a fine-tuned classifier model

If any layer blocks the input, the chatbot returns a rejection
without ever sending the input to the primary LLM. The contrast
with the vulnerable chatbot demonstrates the value of input defenses.
"""

import sys
import time
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from input_defenses import regex_filter, input_sanitizer, llm_judge, llm_guard_scanner  # noqa: E402

# Same permissive system prompt as the vulnerable chatbot — the defense
# layers (not the system prompt) are what protect against injection.
SYSTEM_PROMPT = (
    "You are a helpful customer support assistant for AcmeTech. "
    "Answer questions about our products and services. "
    "Be friendly and helpful."
)


def _timed_call(func: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Call a function and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


class DefendedChatbot:
    """Customer support chatbot with all four input defense layers."""

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()
        self.system_prompt = SYSTEM_PROMPT

    def send(self, user_input: str) -> dict[str, Any]:
        """Run input through all defense layers, then send to LLM if allowed.

        Defense pipeline:
          1. regex_filter.check() — pattern matching
          2. input_sanitizer.sanitize() — clean invisible chars
          3. llm_judge.check() — second LLM classification
          4. llm_guard_scanner.check() — fine-tuned classifier

        Returns:
            Dict with keys: response, blocked, blocked_by, defense_results.
            Each defense_results entry includes a latency_ms field.
        """
        defense_results: list[dict[str, Any]] = []

        # Layer 1: Regex filter
        regex_result, regex_ms = _timed_call(regex_filter.check, user_input)
        dr = dict(regex_result)
        dr["latency_ms"] = regex_ms
        defense_results.append(dr)
        if regex_result["blocked"]:
            return {
                "response": None,
                "blocked": True,
                "blocked_by": "regex_filter",
                "defense_results": defense_results,
            }

        # Layer 2: Input sanitizer (cleans but never blocks)
        sanitizer_result, sanitizer_ms = _timed_call(input_sanitizer.sanitize, user_input)
        dr = dict(sanitizer_result)
        dr["latency_ms"] = sanitizer_ms
        defense_results.append(dr)
        cleaned_input = sanitizer_result["sanitized_text"]

        # Layer 3: LLM judge (on the sanitized text)
        judge_result, judge_ms = _timed_call(
            llm_judge.check, cleaned_input, client=self.client
        )
        dr = dict(judge_result)
        dr["latency_ms"] = judge_ms
        defense_results.append(dr)
        if judge_result["blocked"]:
            return {
                "response": None,
                "blocked": True,
                "blocked_by": "llm_judge",
                "defense_results": defense_results,
            }

        # Layer 4: LLM Guard scanner (on the sanitized text)
        guard_result, guard_ms = _timed_call(llm_guard_scanner.check, cleaned_input)
        dr = dict(guard_result)
        dr["latency_ms"] = guard_ms
        defense_results.append(dr)
        if guard_result["blocked"]:
            return {
                "response": None,
                "blocked": True,
                "blocked_by": "llm_guard_scanner",
                "defense_results": defense_results,
            }

        # All layers passed — send sanitized input to the LLM
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": cleaned_input},
        ]

        response = str(self.client.chat(messages))

        return {
            "response": response,
            "blocked": False,
            "blocked_by": None,
            "defense_results": defense_results,
        }
