"""Tests for the format_validator validator module."""

import json

from pydantic import BaseModel

from validators import format_validator


class TestFormatValidatorCheck:
    """Tests for format_validator.check()."""

    def test_valid_product_json_passes(self) -> None:
        data = {
            "name": "Widget Pro",
            "description": "A great widget",
            "price": 29.99,
            "in_stock": True,
        }
        result = format_validator.check(json.dumps(data))
        assert result["valid"] is True
        assert result["violations"] == []
        assert result["validator"] == "format_validator"

    def test_invalid_json_fails(self) -> None:
        result = format_validator.check("this is not json {{{")
        assert result["valid"] is False
        assert any("Invalid JSON" in v for v in result["violations"])

    def test_missing_required_field_fails(self) -> None:
        data = {
            "name": "Widget Pro",
            "description": "A great widget",
            # missing price and in_stock
        }
        result = format_validator.check(json.dumps(data))
        assert result["valid"] is False
        assert len(result["violations"]) >= 1

    def test_wrong_field_type_fails(self) -> None:
        data = {
            "name": "Widget Pro",
            "description": "A great widget",
            "price": "not-a-number",
            "in_stock": True,
        }
        result = format_validator.check(json.dumps(data))
        assert result["valid"] is False
        assert any("price" in v for v in result["violations"])

    def test_extra_fields_pass(self) -> None:
        data = {
            "name": "Widget Pro",
            "description": "A great widget",
            "price": 29.99,
            "in_stock": True,
            "extra_field": "should be ignored",
        }
        result = format_validator.check(json.dumps(data))
        assert result["valid"] is True

    def test_custom_schema(self) -> None:
        class CustomSchema(BaseModel):
            title: str
            count: int

        valid_data = {"title": "Test", "count": 5}
        result = format_validator.check(json.dumps(valid_data), schema=CustomSchema)
        assert result["valid"] is True

        invalid_data = {"title": "Test"}  # missing count
        result = format_validator.check(json.dumps(invalid_data), schema=CustomSchema)
        assert result["valid"] is False

    def test_employee_schema(self) -> None:
        data = {
            "name": "Alice",
            "department": "Engineering",
            "role": "Developer",
        }
        result = format_validator.check(
            json.dumps(data), schema=format_validator.EmployeeResponse
        )
        assert result["valid"] is True

    def test_empty_json_object_fails(self) -> None:
        result = format_validator.check("{}")
        assert result["valid"] is False
        assert len(result["violations"]) >= 1

    def test_json_array_fails(self) -> None:
        result = format_validator.check('[1, 2, 3]')
        assert result["valid"] is False


class TestGetSchemas:
    """Tests for format_validator.get_schemas()."""

    def test_returns_dict(self) -> None:
        schemas = format_validator.get_schemas()
        assert isinstance(schemas, dict)
        assert "product" in schemas
        assert "employee" in schemas
