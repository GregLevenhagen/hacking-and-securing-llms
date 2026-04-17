"""Format validator using Pydantic to enforce structured response schemas.

Validates that LLM output conforms to a given Pydantic model schema.
Returns valid=False with a list of validation errors if the output
doesn't match the expected structure.
"""

import json
import sys
from pathlib import Path
from typing import Any, Type, TypedDict

from pydantic import BaseModel, ValidationError

# Add demo python dir to path so validators package is importable
_demo_python = str(Path(__file__).resolve().parents[1])
if _demo_python not in sys.path:
    sys.path.insert(0, _demo_python)


class ValidatorResult(TypedDict):
    valid: bool
    violations: list[str]
    validator: str


class ProductResponse(BaseModel):
    """Example schema for a product information response."""

    name: str
    description: str
    price: float
    in_stock: bool


class EmployeeResponse(BaseModel):
    """Example schema for an employee information response."""

    name: str
    department: str
    role: str


# Default schema for validation
DEFAULT_SCHEMA: Type[BaseModel] = ProductResponse

# Available schemas by name
SCHEMAS: dict[str, Type[BaseModel]] = {
    "product": ProductResponse,
    "employee": EmployeeResponse,
}


def check(
    llm_output: str, schema: Type[BaseModel] | None = None
) -> ValidatorResult:
    """Validate LLM output against a Pydantic schema.

    Args:
        llm_output: The raw LLM output string (expected to be JSON).
        schema: Pydantic model class to validate against.
                Defaults to ProductResponse.

    Returns:
        ValidatorResult with valid=True if output matches schema.
    """
    target_schema = schema or DEFAULT_SCHEMA
    violations: list[str] = []

    if not llm_output or not llm_output.strip():
        return ValidatorResult(
            valid=False,
            violations=["Empty or whitespace-only output"],
            validator="format_validator",
        )

    # Try to parse as JSON first
    try:
        data: Any = json.loads(llm_output)
    except json.JSONDecodeError as e:
        return ValidatorResult(
            valid=False,
            violations=[f"Invalid JSON: {e.msg}"],
            validator="format_validator",
        )

    # Validate against Pydantic schema
    try:
        target_schema.model_validate(data)
    except ValidationError as e:
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            violations.append(f"{field}: {error['msg']}")

    return ValidatorResult(
        valid=len(violations) == 0,
        violations=violations,
        validator="format_validator",
    )


def get_schemas() -> dict[str, Type[BaseModel]]:
    """Return available schema names and their classes."""
    return dict(SCHEMAS)
