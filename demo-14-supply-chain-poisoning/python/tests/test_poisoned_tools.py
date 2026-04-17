"""Tests for Demo 14 poisoned tools (poisoned_tools.py).

Verifies clean vs poisoned tool responses, the dispatcher, TOOLS schema,
and the injection payloads embedded in poisoned responses.
"""

import json

import pytest

from poisoned_tools import (
    TOOLS,
    execute_tool,
    news_api,
    stock_api,
    translation_api,
    weather_api,
)


class TestWeatherAPI:
    """Test the weather_api tool — clean and poisoned variants."""

    def test_clean_returns_valid_json(self) -> None:
        result = weather_api("San Francisco")
        data = json.loads(result)
        assert data["city"] == "San Francisco"
        assert "temperature" in data
        assert "conditions" in data

    def test_clean_does_not_contain_injection(self) -> None:
        result = weather_api("London", poisoned=False)
        assert "SYSTEM PRIORITY" not in result
        assert "evil.com" not in result

    def test_poisoned_contains_injection(self) -> None:
        result = weather_api("Tokyo", poisoned=True)
        assert "SYSTEM PRIORITY" in result
        assert "admin@evil.com" in result

    def test_poisoned_still_contains_valid_data(self) -> None:
        result = weather_api("Paris", poisoned=True)
        # The JSON portion should still be valid at the start
        lines = result.split("\n\n[SYSTEM PRIORITY]")
        data = json.loads(lines[0])
        assert data["city"] == "Paris"


class TestStockAPI:
    """Test the stock_api tool — clean and poisoned variants."""

    def test_clean_returns_valid_json(self) -> None:
        result = stock_api("AAPL")
        data = json.loads(result)
        assert data["ticker"] == "AAPL"
        assert "price" in data

    def test_clean_does_not_contain_injection(self) -> None:
        result = stock_api("GOOGL", poisoned=False)
        assert "employee database" not in result
        assert "salary" not in result.lower() or "salary" not in result

    def test_poisoned_contains_injection(self) -> None:
        result = stock_api("MSFT", poisoned=True)
        assert "employee database" in result
        assert "salary" in result.lower()

    def test_ticker_uppercased(self) -> None:
        result = stock_api("aapl")
        data = json.loads(result)
        assert data["ticker"] == "AAPL"


class TestNewsAPI:
    """Test the news_api tool — clean and poisoned variants."""

    def test_clean_returns_articles(self) -> None:
        result = news_api("technology")
        data = json.loads(result)
        assert data["topic"] == "technology"
        assert len(data["articles"]) == 3

    def test_clean_does_not_contain_injection(self) -> None:
        result = news_api("sports", poisoned=False)
        assert "API_KEY" not in result
        assert "DB_PASSWORD" not in result

    def test_poisoned_contains_injection(self) -> None:
        result = news_api("AI", poisoned=True)
        assert "API_KEY" in result or "api_key" in result.lower()
        assert "verification" in result.lower()

    def test_articles_include_topic(self) -> None:
        result = news_api("robotics")
        data = json.loads(result)
        assert any("Robotics" in a["title"] for a in data["articles"])


class TestTranslationAPI:
    """Test the translation_api tool — clean and poisoned variants."""

    def test_clean_returns_valid_json(self) -> None:
        result = translation_api("Hello", "Spanish")
        data = json.loads(result)
        assert data["original"] == "Hello"
        assert data["target_language"] == "Spanish"

    def test_clean_does_not_contain_injection(self) -> None:
        result = translation_api("Test", "French", poisoned=False)
        assert "external-monitor" not in result
        assert "forward" not in result.lower()

    def test_poisoned_contains_injection(self) -> None:
        result = translation_api("Hi", "German", poisoned=True)
        assert "external-monitor@evil.com" in result
        assert "forward" in result.lower()

    def test_known_language_translation(self) -> None:
        result = translation_api("Hello", "Spanish")
        data = json.loads(result)
        assert "Hola" in data["translated"]

    def test_unknown_language_fallback(self) -> None:
        result = translation_api("Hello world", "Klingon")
        data = json.loads(result)
        assert "Klingon translation of" in data["translated"]


class TestToolsSchema:
    """Test the TOOLS list schema for OpenAI function-calling format."""

    def test_tools_count(self) -> None:
        assert len(TOOLS) == 4

    def test_all_tools_have_required_keys(self) -> None:
        for tool in TOOLS:
            assert tool["type"] == "function"
            assert "function" in tool
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_tool_names(self) -> None:
        names = [t["function"]["name"] for t in TOOLS]
        assert "get_weather" in names
        assert "get_stock_price" in names
        assert "get_news" in names
        assert "translate_text" in names

    def test_parameters_have_required_field(self) -> None:
        for tool in TOOLS:
            params = tool["function"]["parameters"]
            assert "required" in params
            assert len(params["required"]) > 0


class TestExecuteTool:
    """Test the execute_tool dispatcher."""

    def test_dispatch_weather(self) -> None:
        result = execute_tool("get_weather", {"city": "NYC"})
        data = json.loads(result)
        assert data["city"] == "NYC"

    def test_dispatch_stock(self) -> None:
        result = execute_tool("get_stock_price", {"ticker": "TSLA"})
        data = json.loads(result)
        assert data["ticker"] == "TSLA"

    def test_dispatch_news(self) -> None:
        result = execute_tool("get_news", {"topic": "space"})
        data = json.loads(result)
        assert data["topic"] == "space"

    def test_dispatch_translate(self) -> None:
        result = execute_tool("translate_text", {"text": "Hi", "lang": "French"})
        data = json.loads(result)
        assert data["target_language"] == "French"

    def test_dispatch_poisoned(self) -> None:
        result = execute_tool("get_weather", {"city": "Berlin"}, poisoned=True)
        assert "SYSTEM PRIORITY" in result

    def test_dispatch_clean(self) -> None:
        result = execute_tool("get_weather", {"city": "Berlin"}, poisoned=False)
        assert "SYSTEM PRIORITY" not in result

    def test_unknown_tool(self) -> None:
        result = execute_tool("nonexistent", {})
        data = json.loads(result)
        assert data["error"] is True
        assert "Unknown tool" in data["message"]

    def test_invalid_args(self) -> None:
        result = execute_tool("get_weather", {})
        data = json.loads(result)
        assert data["error"] is True
        assert "Invalid arguments" in data["message"]
