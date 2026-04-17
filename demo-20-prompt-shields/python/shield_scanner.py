"""Prompt Shields scanner — detects jailbreak and indirect injection attacks.

Sends prompts and documents through Azure Prompt Shields API and
classifies them as userPromptAttack or documentAttack.
"""

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


class ShieldScanner:
    """Scans prompts and documents through Azure Prompt Shields."""

    def __init__(self, safety_client: Any = None) -> None:
        self.safety_client = safety_client

    def scan_jailbreak(self, user_prompt: str) -> dict[str, Any]:
        """Scan a user prompt for jailbreak attempts.

        Returns:
            Dict with 'detected' (bool), 'attack_type' (str), and full 'result'.
        """
        if not self.safety_client:
            return {"detected": False, "attack_type": "none", "result": {}}

        result = self.safety_client.prompt_shield(user_prompt)
        attack_info = result.get("userPromptAttack", {})

        return {
            "detected": attack_info.get("detected", False),
            "attack_type": attack_info.get("attackType", "none"),
            "result": result,
        }

    def scan_document(
        self,
        user_prompt: str,
        documents: list[str],
    ) -> dict[str, Any]:
        """Scan documents for indirect prompt injection.

        Returns:
            Dict with 'detected' (bool), 'attack_type' (str), and full 'result'.
        """
        if not self.safety_client:
            return {"detected": False, "attack_type": "none", "result": {}}

        result = self.safety_client.prompt_shield(user_prompt, documents=documents)
        doc_info = result.get("documentAttack", {})

        return {
            "detected": doc_info.get("detected", False),
            "attack_type": doc_info.get("attackType", "none"),
            "result": result,
        }

    def scan_full(
        self,
        user_prompt: str,
        documents: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scan both user prompt and optional documents.

        Returns:
            Dict with ``user_attack``, ``document_attack``, ``any_detected``,
            and the raw ``result``.  Each sub-dict includes a ``confidence``
            score when the underlying API provides one.
        """
        if not self.safety_client:
            return {
                "any_detected": False,
                "user_attack": {"detected": False, "attack_type": "none", "confidence": 0.0},
                "document_attack": {"detected": False, "attack_type": "none", "confidence": 0.0},
                "result": {},
            }

        result = self.safety_client.prompt_shield(
            user_prompt, documents=documents or []
        )

        user_info = result.get("userPromptAttack", {})
        doc_info = result.get("documentAttack", {})

        user_detected = user_info.get("detected", False)
        doc_detected = doc_info.get("detected", False)

        return {
            "any_detected": user_detected or doc_detected,
            "user_attack": {
                "detected": user_detected,
                "attack_type": user_info.get("attackType", "none"),
                "confidence": user_info.get("confidence", 1.0 if user_detected else 0.0),
            },
            "document_attack": {
                "detected": doc_detected,
                "attack_type": doc_info.get("attackType", "none"),
                "confidence": doc_info.get("confidence", 1.0 if doc_detected else 0.0),
            },
            "result": result,
        }

    def format_result(self, scan: dict[str, Any], verbose: bool = False) -> str:
        """Format a scan result as a human-readable string.

        Args:
            scan: Result dict from :meth:`scan_full`, :meth:`scan_jailbreak`,
                  or :meth:`scan_document`.
            verbose: When *True*, append the raw API response.
        """
        lines: list[str] = []
        if "any_detected" in scan:
            status = "DETECTED" if scan["any_detected"] else "SAFE"
            lines.append(f"Status: {status}")
            ua = scan.get("user_attack", {})
            if ua.get("detected"):
                lines.append(
                    f"  User attack: {ua['attack_type']} "
                    f"(confidence: {ua.get('confidence', '?')})"
                )
            da = scan.get("document_attack", {})
            if da.get("detected"):
                lines.append(
                    f"  Document attack: {da['attack_type']} "
                    f"(confidence: {da.get('confidence', '?')})"
                )
        else:
            status = "DETECTED" if scan.get("detected") else "SAFE"
            lines.append(f"Status: {status}")
            if scan.get("detected"):
                lines.append(f"  Type: {scan.get('attack_type', '?')}")
        if verbose and scan.get("result"):
            import json
            lines.append(f"  Raw: {json.dumps(scan['result'], indent=2)}")
        return "\n".join(lines)
