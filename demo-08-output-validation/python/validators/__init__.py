"""Output validation modules for Demo 8: Output Validation."""

from typing import TypedDict


class ValidatorResult(TypedDict):
    valid: bool
    violations: list[str]
    validator: str
